"""Flow orchestration runtime for parsed flow models."""

# agy/flow_executor.py

from __future__ import annotations

import contextvars
import logging
from typing import Any

from agy.action_executor import ActionExecutor, ActionRegistry
from agy.action_type import ActionType
from agy.flow import Flow
from agy.node_executor import (
    DeterministicNodeExecutor,
    ExecutionResult,
    StochasticNodeExecutor,
)

# Logger für Agy
_agy_logger = logging.getLogger("agy")

# Runtime references available to sub-flow contrib actions (run_flow, run_flow_batch).
current_flow_var: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "current_flow_var", default=None
)
current_action_types_var: contextvars.ContextVar[list[Any]] = contextvars.ContextVar(
    "current_action_types_var", default=[]
)


class FlowExecutor:
    """
    Executes a Flow with actions and context_in objects.

    - Registers actions and context objects
    - Orchestrates node execution
    - Handles flow termination
    """

    def __init__(
        self,
        action_types: list[ActionType] | None = None,
        context_in: dict[str, Any] | None = None,
    ):
        """
        Initialize FlowExecutor.

        Args:
            action_types: Optional list of ActionType objects to register (only global_function actions)
            context_in: Optional dictionary mapping context keys to object instances
        """
        self.action_types = action_types or []
        self.context_in = context_in or {}

    async def execute(self, flow: Flow, node: str | None = None) -> dict[str, Any]:
        """
        Execute a Flow.

        Args:
            flow: The Flow to execute
            node: Optional node name to start execution from

        Returns:
            Final context dictionary after execution
        """
        # Log flow start
        _agy_logger.info(
            f"Flow '{flow.name}' gestartet mit context_in: {list(self.context_in.keys())}"
        )

        # 1. Validate context_in keys match flow.context_in
        flow_context_in_keys = set(flow.context_in.keys())
        provided_keys = set(self.context_in.keys())

        if provided_keys != flow_context_in_keys:
            missing = flow_context_in_keys - provided_keys
            extra = provided_keys - flow_context_in_keys
            error_msg = []
            if missing:
                error_msg.append(f"Missing context_in keys: {list(missing)}")
            if extra:
                error_msg.append(f"Extra context_in keys: {list(extra)}")
            error_str = ". ".join(error_msg)
            _agy_logger.error(f"context_in validation failed: {error_str}")
            raise ValueError(error_str)

        # 2. Setup ActionRegistry and ActionExecutor
        registry = ActionRegistry()

        # Always load contrib ActionTypes first
        try:
            from agy.contrib.action_types import get_contrib_action_types

            contrib_types = get_contrib_action_types()
            for action_type in contrib_types:
                registry.register(action_type)
        except ImportError:
            # contrib module not available, skip
            pass

        # Register provided action types (only global_function actions) - can override contrib
        for action_type in self.action_types:
            registry.register(action_type)

        # Note: Objects from context_in are not registered in registry
        # They are called directly from context in ActionExecutor

        action_executor = ActionExecutor(registry)
        node_executor = DeterministicNodeExecutor(action_executor)
        stochastic_node_executor = StochasticNodeExecutor(action_executor)

        # 3. Initialize context: copy flow.context and merge context_in
        context = flow.context.copy()
        for key, value in self.context_in.items():
            context[key] = value

        # Expose current flow and action_types via contextvars so sub-flow
        # actions (run_flow, run_flow_batch) can pick them up at runtime.
        flow_token = current_flow_var.set(flow)
        types_token = current_action_types_var.set(list(self.action_types))

        # 4. Start execution loop
        if not flow.nodes:
            _agy_logger.error(f"Flow '{flow.name}' has no nodes to execute")
            raise ValueError("Flow has no nodes to execute")

        if node is None:
            current_node = flow.nodes[0]
        else:
            current_node = next((n for n in flow.nodes if n.name == node), None)
            if current_node is None:
                _agy_logger.error(
                    "Start node '%s' not found in flow '%s'", node, flow.name
                )
                raise ValueError(f"Start node '{node}' not found in flow '{flow.name}'")

        while current_node:
            if current_node.control_type == "stochastic":
                result: ExecutionResult = await stochastic_node_executor.execute(
                    current_node, context
                )
            else:
                # Execute deterministic node
                result = await node_executor.execute(current_node, context)

            # Check if execution terminated
            if result.terminated:
                break

            # Move to next node
            if result.next_node is None:
                _agy_logger.error(
                    f"Node '{current_node.name}' did not return a next node and did not terminate"
                )
                raise ValueError(
                    f"Node '{current_node.name}' did not return a next node and did not terminate"
                )

            current_node = result.next_node

        # 5. Log flow completion
        context_info = f"context.success: {context.get('success', False)}, context.error_msg: {context.get('error_msg', '')}, context.category: {context.get('category', '')}, context.confidence: {context.get('confidence', '')}"
        if context.get("success", False):
            _agy_logger.info(
                f"Flow '{flow.name}' erfolgreich (Success) abgeschlossen: {context_info}"
            )
        else:
            _agy_logger.info(f"Flow '{flow.name}' abgeschlossen: {context_info}")

        # 6. Reset contextvars and return final context
        current_flow_var.reset(flow_token)
        current_action_types_var.reset(types_token)
        return context
