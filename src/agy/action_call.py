"""Concrete action invocation model parsed from FLOWSY."""

# agy/action_call.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agy.source_span import SourceSpan


class ActionCall:
    """
    Represents a concrete call to an action in a node.
    Contains concrete values/variables, not types.

    - object_name: e.g., "shipment", "email", or "global_function"
    - method_name: name of the method/function to call
    - args: list of (value, is_literal) tuples
            - value: concrete value OR context variable name (string)
            - is_literal: True if value is a literal, False if it's a context var name
    - kwargs: dict mapping parameter names to (value, is_literal) tuples
              - value: concrete value OR context variable name (string)
              - is_literal: True if value is a literal, False if it's a context var name
    - output: name of the context variable to store the result (default: "result")

    Example:
        ActionCall(
            object_name="email",
            method_name="reply",
            args=[("Hallo", True), ("recipient", False)],  # (value, is_literal)
            kwargs={"attach": ("filepath", False)},
            output="result"
        )
    """

    def __init__(
        self,
        object_name: str,
        method_name: str,
        args: list[tuple[Any, bool]] | None = None,
        kwargs: dict[str, tuple[Any, bool]] | None = None,
        output: str | None = "result",
        source_span: SourceSpan | None = None,
    ) -> None:
        """Initialize a concrete action invocation.

        Args:
            object_name: Object name or `global_function`.
            method_name: Function or method name.
            args: Positional arguments as `(value, is_literal)` tuples.
            kwargs: Keyword arguments as `(value, is_literal)` tuples.
            output: Context key receiving the action result.
            source_span: Source location for error reporting.
        """
        self.object_name = object_name
        self.method_name = method_name
        self.args = args or []
        self.kwargs = kwargs or {}
        self.output = output
        self.source_span = source_span

    def get_args_values(self) -> list[Any]:
        """Return raw positional argument values without literal flags."""
        return [value for value, _ in self.args]

    def get_kwargs_values(self) -> dict[str, Any]:
        """Return raw keyword argument values without literal flags."""
        return {k: v for k, (v, _) in self.kwargs.items()}

    @classmethod
    def from_flowsy_string(
        cls,
        action_str: str,
        source_span: SourceSpan | None = None,
        node_name: str = "",
    ) -> ActionCall:
        """Parse action from FLOWSY action string.

        Args:
            action_str: The action string from the FLOWSY file (e.g., "result = func(arg)")
            source_span: Optional SourceSpan for error reporting
            node_name: Optional node name for error messages

        Returns:
            ActionCall object

        Raises:
            ValueError: If the action string cannot be parsed
        """
        from agy.ast_parser import parse_action_with_ast

        try:
            action_call = parse_action_with_ast(action_str)
            action_call.source_span = source_span
            return action_call
        except Exception as e:
            if source_span:
                raise ValueError(
                    f"{source_span}\n"
                    f"Error parsing action in node '{node_name}': {action_str}\n"
                    f"Error: {e}"
                ) from e
            else:
                raise ValueError(
                    f"Error parsing action in node '{node_name}': {action_str}\n"
                    f"Error: {e}"
                ) from e
