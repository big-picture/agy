"""Action execution engine and registry."""

# agy/action_executor.py

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

from agy.action_call import ActionCall
from agy.action_type import ActionType
from agy.ast_parser import SAFE_BUILTINS

# Import FlowTerminationError for handling end() action
try:
    from agy.contrib.action_type_functions import FlowTerminationError
except ImportError:
    # If contrib is not available, define a placeholder
    class FlowTerminationError(Exception):  # type: ignore[no-redef]
        """Exception to signal flow termination from end() action"""

        def __init__(self, context_updates: dict[str, Any]):
            """Initialize a flow-termination signal.

            Args:
                context_updates: Context values written before termination.
            """
            self.context_updates = context_updates
            super().__init__("Flow terminated by end() action")


# Logger für Agy
_agy_logger = logging.getLogger("agy")


class ActionRegistry:
    """
    Registry for global_function action types.
    Only global_function actions are stored (object_name == "global_function").
    Object methods are called directly from context, not stored here.
    """

    def __init__(self):
        """Initialize an empty action registry."""
        self.action_types: dict[str, ActionType] = {}  # method_name -> ActionType

    def register(self, action_type: ActionType) -> None:
        """Register one `global_function` action type."""
        if action_type.object_name != "global_function":
            raise ValueError(
                f"Only global_function action types can be registered. Got object_name='{action_type.object_name}'"
            )
        self.action_types[action_type.method_name] = action_type

    def register_function(self, func: Callable, name: str | None = None) -> None:
        """
        Convenience method to register a function directly.

        Args:
            func: The function to register
            name: Optional custom name (defaults to function's __name__)

        Example:
            registry.register_function(add)
            registry.register_function(my_func, name="custom_name")
        """
        method_name = name or func.__name__
        action_type = ActionType(
            object_name="global_function", method_name=method_name, callable=func
        )
        self.register(action_type)

    def get_action_type(self, method_name: str) -> ActionType | None:
        """Return a registered `global_function` action type by method name."""
        return self.action_types.get(method_name)


class ActionExecutor:
    """
    Executes ActionCall objects.
    - global_function actions: Gets ActionType from registry and calls callable
    - Object methods: Gets object from context and calls method directly
    """

    def __init__(self, registry: ActionRegistry):
        """Initialize the action executor.

        Args:
            registry: Registered global function actions.
        """
        self.registry = registry

    async def evaluate_expression(
        self, expr_str: str, context: dict[str, Any]
    ) -> Any:
        """Evaluate a Python expression with the same context as __eval__ actions."""
        eval_context = context.copy()
        for method_name, action_type in self.registry.action_types.items():
            if action_type.callable:
                eval_context[method_name] = action_type.callable

        try:
            result = eval(
                expr_str,
                {"__builtins__": SAFE_BUILTINS},
                eval_context,
            )
            if inspect.iscoroutine(result):
                result = await result
            return result
        except Exception as e:
            raise ValueError(
                f"Error evaluating expression: {expr_str}\nError: {e}"
            ) from e

    async def execute(self, action_call: ActionCall, context: dict[str, Any]) -> None:
        """
        Execute an ActionCall and write result to context.

        Args:
            action_call: The ActionCall to execute
            context: The flow context (will be modified)
        """
        try:
            # Case 1: global_function action - get ActionType from registry
            if action_call.object_name == "global_function":
                # Special case: __exec__ for assignment statements (complex targets)
                if action_call.method_name == "__exec__":
                    if not action_call.args:
                        raise ValueError(
                            "__exec__ requires at least one argument (the assignment statement)"
                        )

                    assignment_str, is_literal = action_call.args[0]

                    if is_literal:
                        raise ValueError(
                            "__exec__ assignment statement must be code, not literal"
                        )

                    # Prepare execution context (same as eval context)
                    exec_context = context.copy()
                    for method_name, action_type in self.registry.action_types.items():
                        if action_type.callable:
                            exec_context[method_name] = action_type.callable

                    try:
                        # Execute assignment statement (e.g., "invoice.invoice_number = value")
                        # exec() executes statements (assignments), eval() only evaluates expressions
                        exec(
                            assignment_str,
                            {"__builtins__": SAFE_BUILTINS},  # Only safe built-ins
                            exec_context,  # Flow context + registered functions
                        )
                        # Note: exec() doesn't return a value, it modifies objects in context
                        result = None
                    except Exception as e:
                        raise ValueError(
                            f"Error executing assignment: {assignment_str}\nError: {e}"
                        ) from e

                    # Set success (assignments don't return results)
                    context["success"] = True
                    context["error_msg"] = ""
                    context["result"] = None

                    # Logging
                    _agy_logger.info(f"SUCCESS: {assignment_str}")
                    return

                # Special case: __eval__ for generic expression evaluation
                # Skip argument resolution for __eval__ - we evaluate the expression directly
                if action_call.method_name == "__eval__":
                    if not action_call.args:
                        raise ValueError(
                            "__eval__ requires at least one argument (the expression)"
                        )

                    expr_str, is_literal = action_call.args[0]

                    if is_literal:
                        # Should not happen, but handle it
                        result = expr_str
                    else:
                        result = await self.evaluate_expression(expr_str, context)

                    # Write result to context
                    # Preserve exception from failed action when merging end() so API gets real error (only on failure path)
                    saved_error_msg = ""
                    if (
                        isinstance(result, dict)
                        and "context" in result
                        and context.get("success") is False
                    ):
                        saved_error_msg = context.get("error_msg") or ""
                    # 1. success = True setzen (vor context.update, damit überschreibbar)
                    context["success"] = True
                    context["error_msg"] = ""

                    # 2. Format erkennen und verarbeiten
                    if isinstance(result, dict) and (
                        "context" in result or "flow_control" in result
                    ):
                        # Neues Format: {"result": ..., "context": {...}}
                        if "result" in result:
                            if action_call.output:
                                context[action_call.output] = result["result"]
                            context["result"] = result["result"]

                        # context.update() nur wenn "context" vorhanden
                        if "context" in result:
                            context.update(result["context"])
                            # Prefer preserved exception over end()'s error_msg so API gets the real error
                            if saved_error_msg:
                                context["error_msg"] = saved_error_msg

                        # flow_control prüfen
                        if result.get("flow_control") == "TERMINATE":
                            raise FlowTerminationError(result.get("context", {}))
                    else:
                        # Normales Ergebnis (kein Dict oder kein "context"/"flow_control" Key)
                        if action_call.output:
                            context[action_call.output] = result
                        context["result"] = result

                    # Logging
                    output_str = (
                        f"{action_call.output}="
                        if action_call.output != "result"
                        else ""
                    )
                    action_str = f"{output_str}__eval__({expr_str})"
                    _agy_logger.info(f"SUCCESS: {action_str}")
                    return

            # ═══════════════════════════════════════════════════════════════════════════
            # NOTE: Direct Action Execution (Non-__eval__ format) is NOT supported
            # ═══════════════════════════════════════════════════════════════════════════
            #
            # All actions are now executed via __eval__ (AST-based parsing).
            # This applies to:
            #   - Actions from FLOWSY files (parsed with ast_parser)
            #   - Actions from tests (must use __eval__ format)
            #   - Programmatically created actions (must use __eval__ format)
            #
            # Example __eval__ format:
            #   ActionCall(
            #       object_name="",
            #       method_name="__eval__",
            #       args=[("add(5, 3)", False)],  # (expression, is_literal)
            #       kwargs={},
            #       output="result"
            #   )
            #
            # If you need to support direct action execution (old format), you need to:
            #   1. Get the action_type from registry
            #   2. Resolve args/kwargs (eval non-literal values)
            #   3. Call action_type.callable(*args, **kwargs)
            #   4. Handle async results (await if coroutine)
            #   5. Write result to context
            #   6. Handle success/error logging
            #
            # This was removed to simplify the codebase (~67 lines of code).
            # See git history (commit before FLOWSY integration) for reference implementation.
            # ═══════════════════════════════════════════════════════════════════════════

            raise ValueError(
                f"Unexpected action format: object_name='{action_call.object_name}', "
                f"method_name='{action_call.method_name}'. "
                f"All actions must use __eval__ format. "
                f"See comment above for migration guide."
            )

        except FlowTerminationError:
            # FlowTerminationError from end() action - re-raise it
            # Context was already updated in the end() function
            raise
        except Exception as e:
            # Any error during execution
            context["success"] = False
            context["error_msg"] = str(e)

        # Logging: only for error cases (success cases are logged in __eval__ block)
        if not context["success"]:
            output_str = (
                f"{action_call.output}=" if action_call.output != "result" else ""
            )
            if action_call.method_name == "__eval__":
                expr_str = action_call.args[0][0] if action_call.args else "?"
                action_str = f"{output_str}__eval__({expr_str})"
            else:
                action_str = f"{output_str}{action_call.object_name}.{action_call.method_name}(...)"
            _agy_logger.error(f"FAIL: {action_str} - {context['error_msg']}")
