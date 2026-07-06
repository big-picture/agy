"""Node execution orchestration for deterministic nodes."""

# agy/node_executor.py

from __future__ import annotations

import ast
import inspect
import logging
from dataclasses import dataclass
from typing import Any

from agy.action_call import ActionCall
from agy.action_executor import ActionExecutor
from agy.node import Node

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


class ExecutionResult:
    """Execution outcome for one node run."""

    def __init__(self, next_node: Node | None = None, terminated: bool = False):
        """Initialize a node execution result.

        Args:
            next_node: Next node to execute, if any.
            terminated: Whether flow execution ended.
        """
        self.next_node = next_node
        self.terminated = terminated


@dataclass
class AgentRequestResult:
    """Normalized result returned by stochastic agent requests."""

    outputs: list[Any]
    output: Any | None
    message: str
    success: bool
    error_msg: str = ""
    raw: dict[str, Any] | None = None


def normalize_agent_request_result(result: Any) -> AgentRequestResult:
    """Normalize agent return values to the stochastic node result contract."""
    if isinstance(result, AgentRequestResult):
        return result

    if isinstance(result, dict):
        output = result.get("output")
        outputs = result.get("outputs")
        if outputs is None:
            outputs = [output] if output is not None else []
        return AgentRequestResult(
            outputs=list(outputs),
            output=output,
            message=str(result.get("message", "")),
            success=bool(result.get("success", True)),
            error_msg=str(result.get("error_msg", "")),
            raw=result,
        )

    return AgentRequestResult(
        outputs=[result],
        output=result,
        message="",
        success=True,
        error_msg="",
        raw=None,
    )


class DeterministicNodeExecutor:
    """Execute deterministic nodes by running actions then evaluating edges."""

    def __init__(self, action_executor: ActionExecutor):
        """Initialize the deterministic node executor.

        Args:
            action_executor: Action executor used for node action calls.
        """
        self.action_executor = action_executor

    def _parse_end_action_from_edge(self, end_str: str) -> ActionCall:
        """
        Parse end(...) string from edge target into ActionCall using __eval__.

        This converts end(...) to an __eval__ action, so it runs through the
        normal __eval__ path in ActionExecutor, where end() is available in
        the eval context.

        Examples:
        - "end" -> ActionCall for __eval__("end()")
        - "end(success=True)" -> ActionCall for __eval__("end(success=True)")
        - "end(success=True, error_msg=\"test\")" -> ActionCall for __eval__("end(...)")
        """
        end_str = end_str.strip()
        # Convert to __eval__ action - end() will be available in eval context
        return ActionCall(
            object_name="global_function",
            method_name="__eval__",
            args=[(end_str, False)],  # False = not literal, it's code to eval
            kwargs={},
            output="result",
        )

    async def _evaluate_edges(
        self, node: Node, context: dict[str, Any]
    ) -> ExecutionResult:
        """Evaluate node edges using the shared deterministic routing semantics."""
        # If no edges, terminate automatically
        if not node.edges:
            return ExecutionResult(next_node=None, terminated=True)

        # Evaluate edges to find next node
        # Edges are evaluated in order, first matching edge wins
        next_node: Node | None = None

        for edge in node.edges:
            if edge.evaluate(context):
                # Check if target is "end" keyword (string) or "end(...)" pattern
                if isinstance(edge.target, str):
                    target_stripped = edge.target.strip()
                    is_end_target = target_stripped == "end" or (
                        target_stripped.startswith("end")
                        and target_stripped.endswith(")")
                        and target_stripped[3:].lstrip().startswith("(")
                    )
                    if is_end_target:
                        # Execute end() action if it has arguments
                        if "(" in target_stripped:
                            try:
                                end_action_call = self._parse_end_action_from_edge(
                                    target_stripped
                                )
                                await self.action_executor.execute(
                                    end_action_call, context
                                )
                            except FlowTerminationError:
                                # end() action terminates - context already updated
                                pass
                        # Terminate flow
                        return ExecutionResult(next_node=None, terminated=True)
                # Otherwise, target is a Node
                if isinstance(edge.target, Node):
                    next_node = edge.target
                    break

        if next_node is None:
            msg = (
                context.get("error_msg")
                if context.get("success") is False
                else f"No edge condition matched for node '{node.name}'"
            )
            raise ValueError(msg)

        return ExecutionResult(next_node=next_node, terminated=False)

    async def execute(self, node: Node, context: dict[str, Any]) -> ExecutionResult:
        """
        Execute a deterministic node:
        1. Run all actions in sequence
        2. Evaluate edges to determine next node
        """
        # Log node start
        _agy_logger.info(f"Node '{node.name}' gestartet")

        # Execute all action calls in sequence
        for action_call in node.actions:
            try:
                # Execute action call directly - ActionExecutor handles all resolution
                await self.action_executor.execute(action_call, context)
            except FlowTerminationError:
                # end() action was called - terminate flow
                # Context was already updated in the end() function
                return ExecutionResult(next_node=None, terminated=True)

            # If action failed (success set to False by ActionExecutor), stop execution and go to edges
            if context.get("success") is False:
                _agy_logger.info(
                    f"Action '{action_call.method_name}' failed in node '{node.name}'. Stopping action execution and evaluating edges."
                )
                break

        # Debug: Log context after actions
        _agy_logger.debug(
            f"Context after node '{node.name}': category={context.get('category')}, confidence={context.get('confidence')}, success={context.get('success')}, error_msg={context.get('error_msg')}"
        )

        return await self._evaluate_edges(node, context)


class StochasticNodeExecutor(DeterministicNodeExecutor):
    """Execute stochastic nodes by delegating natural-language requests to an agent."""

    async def _resolve_request(self, request: str, context: dict[str, Any]) -> str:
        """Evaluate request expressions while preserving plain natural language."""
        try:
            ast.parse(request, mode="eval")
        except SyntaxError:
            return request

        result = await self.action_executor.evaluate_expression(request, context)
        if not isinstance(result, str):
            raise ValueError("Stochastic request expression must evaluate to str")
        return result

    def _build_run_kwargs(
        self,
        run_callable: Any,
        *,
        options: dict[str, Any],
        context: dict[str, Any],
        previous_output: Any,
    ) -> dict[str, Any]:
        """Pass optional run metadata only when the agent accepts it."""
        try:
            signature = inspect.signature(run_callable)
        except (TypeError, ValueError):
            return {"options": options} if options else {}

        accepts_var_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        kwargs: dict[str, Any] = {}

        if options or "options" in signature.parameters or accepts_var_kwargs:
            kwargs["options"] = options
        if previous_output is not None and (
            "previous_output" in signature.parameters or accepts_var_kwargs
        ):
            kwargs["previous_output"] = previous_output
        if "context" in signature.parameters or accepts_var_kwargs:
            kwargs["context"] = context

        return kwargs

    async def _call_agent_run(
        self,
        agent: Any,
        request: str,
        *,
        options: dict[str, Any],
        context: dict[str, Any],
        previous_output: Any,
    ) -> AgentRequestResult:
        """Call an agent run method and normalize its result."""
        if not hasattr(agent, "run") or not callable(agent.run):
            raise ValueError("Stochastic agent must provide a callable run(...) method")

        kwargs = self._build_run_kwargs(
            agent.run,
            options=options,
            context=context,
            previous_output=previous_output,
        )
        result = agent.run(request, **kwargs)
        if inspect.iscoroutine(result):
            result = await result
        return normalize_agent_request_result(result)

    async def execute(self, node: Node, context: dict[str, Any]) -> ExecutionResult:
        """Run all stochastic requests and then evaluate edges."""
        _agy_logger.info(f"Stochastic node '{node.name}' gestartet")

        try:
            if not node.agent:
                raise ValueError(f"Stochastic node '{node.name}' is missing agent")
            if node.agent not in context:
                raise ValueError(
                    f"Stochastic agent '{node.agent}' not found in context"
                )
            if not node.requests:
                raise ValueError(f"Stochastic node '{node.name}' has no requests")

            agent = context[node.agent]
            all_outputs: list[Any] = []
            final_result: AgentRequestResult | None = None
            previous_output: Any = None

            for request in node.requests:
                resolved_request = await self._resolve_request(request, context)
                final_result = await self._call_agent_run(
                    agent,
                    resolved_request,
                    options=node.options,
                    context=context,
                    previous_output=previous_output,
                )
                all_outputs.extend(final_result.outputs)
                previous_output = final_result.output
                if not final_result.success:
                    break

            if final_result is None:
                raise ValueError(f"Stochastic node '{node.name}' produced no result")

            output_key = node.output or "output"
            message_key = node.message or "message"

            context[output_key] = final_result.output
            context[message_key] = final_result.message
            context["agent_outputs"] = all_outputs
            context["result"] = final_result.output
            context["success"] = final_result.success
            context["error_msg"] = final_result.error_msg

            _agy_logger.info(
                "SUCCESS: stochastic node '%s' completed with agent '%s'",
                node.name,
                node.agent,
            )
        except Exception as e:
            output_key = node.output or "output"
            message_key = node.message or "message"
            context[output_key] = None
            context[message_key] = ""
            context["agent_outputs"] = []
            context["result"] = None
            context["success"] = False
            context["error_msg"] = str(e)
            _agy_logger.error(
                "FAIL: stochastic node '%s' - %s", node.name, context["error_msg"]
            )

        return await self._evaluate_edges(node, context)
