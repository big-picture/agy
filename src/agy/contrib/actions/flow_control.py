"""Contrib flow-control actions."""

from __future__ import annotations

from typing import Any

from agy.action_type import ActionType


class FlowTerminationError(Exception):
    """Exception to signal flow termination from end() action."""

    def __init__(self, context_updates: dict[str, Any]):
        """Initialize the object.

        Args:
            context_updates: context updates.
        """
        self.context_updates = context_updates
        super().__init__("Flow terminated by end() action")


def end(**kwargs: Any) -> dict[str, Any]:
    """Terminate flow and update context with provided kwargs."""
    return {
        "result": None,
        "context": kwargs,
        "flow_control": "TERMINATE",
    }


ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="end",
    kwargs={},
    callable=end,
    description="Terminate flow and update context with provided kwargs",
)
