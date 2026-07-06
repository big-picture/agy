"""Node model used by parsed flows."""

# agy/node.py

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from agy.action_call import ActionCall
    from agy.edge import Edge
    from agy.source_span import SourceSpan

ControlType = Literal["deterministic", "stochastic"]


def _parse_request_scalar(value: str) -> str:
    """Return quoted FLOWSY request scalars as plain strings."""
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return value
    return parsed if isinstance(parsed, str) else value


class Node:
    """Represents one executable flow node."""

    def __init__(
        self,
        *,
        name: str,
        control_type: ControlType,
        outputs: dict[str, str]
        | None = None,  # z.B. {"carrier":"str","tracking_id":"str"}
        actions: list[ActionCall] | None = None,  # nur bei deterministisch
        instruction: str | None = None,  # nur bei stochastisch
        agent: str | None = None,
        requests: list[str] | None = None,
        options: dict[str, Any] | None = None,
        output: str | None = None,
        message: str | None = None,
        edges: list[Edge] | None = None,  # Routing
        source_span: SourceSpan | None = None,
    ) -> None:
        """Initialize a flow node.

        Args:
            name: Node identifier.
            control_type: Execution strategy (`deterministic` or `stochastic`).
            outputs: Declared output names and type names.
            actions: Action calls for deterministic nodes.
            instruction: Prompt/instruction text for stochastic nodes.
            agent: Context key of the agent object for stochastic nodes.
            requests: Natural-language requests for stochastic nodes.
            options: Optional request options for stochastic nodes.
            output: Context key receiving the final agent output.
            message: Context key receiving the final agent message.
            edges: Outgoing routing edges.
            source_span: Source location for error reporting.
        """
        self.name = name
        self.control_type = control_type
        self.outputs = outputs or {}
        self.actions = actions or []
        self.instruction = instruction
        self.agent = agent
        self.requests = requests or []
        self.options = options or {}
        self.output = output
        self.message = message
        self.edges = edges or []
        self.source_span = source_span

    @classmethod
    def from_flowsy_data(
        cls,
        node_name: str,
        node_data: dict[str, Any],
        source_spans: dict[str, SourceSpan],
        node_path: str,
    ) -> Node:
        """Parse node from FLOWSY data.

        Args:
            node_name: Name of the node
            node_data: Dict with 'actions' and 'edges' from FLOWSY parser
            source_spans: Dict mapping paths to SourceSpan objects
            node_path: Path prefix for this node (e.g., "nodes.classify_email")

        Returns:
            Node object (edge targets are strings, resolved later in Flow)
        """
        from agy.action_call import ActionCall
        from agy.edge import Edge

        control_type_raw = node_data.get("type", "deterministic")
        if control_type_raw not in ("deterministic", "stochastic"):
            raise ValueError(
                f"Invalid node type '{control_type_raw}' in node '{node_name}'. "
                "Expected 'deterministic' or 'stochastic'."
            )
        control_type = control_type_raw

        # Parse actions
        actions = []
        for idx, action_str in enumerate(node_data.get("actions", [])):
            action_path = f"{node_path}.actions[{idx}]"
            span = source_spans.get(action_path)
            actions.append(ActionCall.from_flowsy_string(action_str, span, node_name))

        # Parse edges
        edges = []
        raw_edges = node_data.get("edges", [])
        for idx, edge_item in enumerate(raw_edges):
            edge_path = f"{node_path}.edges[{idx}]"
            span = source_spans.get(edge_path)
            if isinstance(edge_item, str) and idx != len(raw_edges) - 1:
                location = f"{span}\n" if span else ""
                raise ValueError(
                    f"{location}Fallback edge without condition must be the last "
                    f"edge in node '{node_name}': {edge_item}"
                )
            edges.append(Edge.from_flowsy_item(edge_item, span, node_name))

        requests = [
            _parse_request_scalar(request)
            for request in node_data.get("requests", [])
        ]

        # Node span
        node_span = source_spans.get(node_path)

        return cls(
            name=node_name,
            control_type=control_type,
            outputs={},
            actions=actions if actions else None,
            instruction=None,
            agent=node_data.get("agent"),
            requests=requests,
            options=node_data.get("options", {}),
            output=node_data.get("output"),
            message=node_data.get("message"),
            edges=edges if edges else None,
            source_span=node_span,
        )
