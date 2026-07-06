"""Edge model and condition evaluation for flow routing."""

# agy/edge.py

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agy.ast_parser import SAFE_BUILTINS

if TYPE_CHECKING:
    from agy.node import Node
    from agy.source_span import SourceSpan

# Logger für Agy
_agy_logger = logging.getLogger("agy")


class Edge:
    """
    Routing edge to a target node.
    - target: target node object or "end" (string) for termination
    - condition:   guard/condition (e.g., "success" or "else")
    """

    def __init__(
        self,
        *,
        target: Node | str,
        condition: str | bool | None = None,
        source_span: SourceSpan | None = None,
    ) -> None:
        """Initialize a routing edge.

        Args:
            target: Target node or `end` expression.
            condition: Guard expression or boolean fallback.
            source_span: Source location for error reporting.
        """
        self.target = target
        self.condition = condition
        self.source_span = source_span

    def evaluate(self, context: dict[str, Any]) -> bool:
        """
        Evaluate this edge's condition against the provided context.
        - True/False (bool) => return directly
        - "success" => context["success"]
        - "x > y" => evaluates the expression with context values

        Args:
            context: Context dictionary to evaluate against

        Returns:
            True if condition matches, False otherwise
        """
        if self.condition is None:
            # Should not happen in practice (YAML parser sets "True" as default)
            return False

        # Handle boolean values directly
        if isinstance(self.condition, bool):
            return self.condition

        # Commented it out ... should work without it
        # Handle literal boolean strings first (before simple_eval tries to interpret them as variable names)
        # if isinstance(self.condition, str):
        #    condition_stripped = self.condition.strip()
        #    if condition_stripped.lower() == "true":
        #        return True
        #    if condition_stripped.lower() == "false":
        #        return False

        # For all other cases, try to evaluate as expression using eval()
        try:
            result = eval(
                self.condition,
                {"__builtins__": SAFE_BUILTINS},  # Only safe built-ins
                context,  # Flow context as local namespace
            )
            # Debug: Log edge evaluation
            _agy_logger.debug(
                f"Edge condition '{self.condition}' evaluated to {result} (context keys: {list(context.keys())})"
            )
            return bool(result)
        except (NameError, KeyError) as e:
            _agy_logger.debug(
                f"Edge condition '{self.condition}' failed: {e} (context keys: {list(context.keys())})"
            )
            return False
        except Exception as e:
            _agy_logger.debug(
                f"Edge condition '{self.condition}' error: {e} (context keys: {list(context.keys())})"
            )
            return False

    @classmethod
    def from_flowsy_item(
        cls,
        edge_item: dict[str, str] | str,
        source_span: SourceSpan | None = None,
        node_name: str = "",
    ) -> Edge:
        """Parse edge from FLOWSY edge item.

        Args:
            edge_item: Either {"condition": "target"} or fallback target string.
            source_span: Optional SourceSpan for error reporting
            node_name: Optional node name for error messages

        Returns:
            Edge object (target is string, resolved later in Flow)

        Raises:
            ValueError: If the edge cannot be parsed
        """
        from agy.ast_parser import parse_edge_with_ast

        if isinstance(edge_item, str):
            target = edge_item.strip()
            if not target:
                raise ValueError(f"Error parsing edge in node '{node_name}': empty target")
            return cls(target=target, condition="True", source_span=source_span)

        # edge_item is {"condition": "target"}
        ((condition, target),) = edge_item.items()
        edge_str = f"{condition}: {target}"

        try:
            validated_cond, validated_target = parse_edge_with_ast(edge_str)
            return cls(
                target=validated_target,
                condition=validated_cond,
                source_span=source_span,
            )
        except Exception as e:
            if source_span:
                raise ValueError(
                    f"{source_span}\n"
                    f"Error parsing edge in node '{node_name}': {condition}: {target}\n"
                    f"Error: {e}"
                ) from e
            else:
                raise ValueError(
                    f"Error parsing edge in node '{node_name}': {condition}: {target}\n"
                    f"Error: {e}"
                ) from e

    @classmethod
    def from_flowsy_dict(
        cls,
        edge_dict: dict[str, str],
        source_span: SourceSpan | None = None,
        node_name: str = "",
    ) -> Edge:
        """Parse edge from a legacy FLOWSY edge dict."""
        return cls.from_flowsy_item(edge_dict, source_span, node_name)
