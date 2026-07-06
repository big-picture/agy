"""Action type metadata used by the action registry."""

# agy/action_type.py
from __future__ import annotations

from collections.abc import Callable
from typing import Any

ActionParamType = Any


class ActionType:
    """
    Defines the signature/type of an action (like a function header).
    Stored in ActionRegistry.

    - object_name: e.g., "shipment", "email", or "global_function"
    - method_name: name of the method/function
    - args: list of types for positional parameters (in order)
    - kwargs: dict mapping parameter names to their types for keyword parameters
    - callable: actual callable function (only for global_function actions)
    - description: human-readable description
    """

    def __init__(
        self,
        object_name: str,
        method_name: str,
        args: list[ActionParamType] | None = None,
        kwargs: dict[str, ActionParamType] | None = None,
        callable: Callable | None = None,
        description: str | None = None,
    ) -> None:
        """Initialize action type metadata.

        Args:
            object_name: Owner object name (for example `global_function`).
            method_name: Function or method name.
            args: Positional parameter types in order.
            kwargs: Keyword parameter types by name.
            callable: Callable to execute for global functions.
            description: Optional human-readable description.
        """
        self.object_name = object_name
        self.method_name = method_name
        self.args = args or []
        self.kwargs = kwargs or {}
        self.callable = callable  # Only for "global_function" actions
        self.description = description
