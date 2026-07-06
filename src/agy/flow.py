"""Flow model and parsing helpers."""

# agy/flow.py

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from agy.action_type import ActionType
    from agy.node import Node
    from agy.source_span import SourceSpan
    from agy.validation import ValidationResult


class Flow:
    """Represents a parsed flow definition and its runtime context schema."""

    def __init__(
        self,
        *,
        name: str,
        description: str = "",
        nodes: list[Node],
        context_in: dict[str, str] | None = None,
        context: dict[str, str] | None = None,
        source_span: SourceSpan | None = None,
    ) -> None:
        """Initialize a flow object.

        Args:
            name: Flow name.
            description: Optional flow description.
            nodes: Ordered flow nodes.
            context_in: Declared required input objects and their type names.
            context: Optional additional context keys and type names.
            source_span: Source location for error reporting.
        """
        self.name = name
        self.description = description
        self.nodes = nodes
        self.context_in = context_in or {}  # Required context objects at instantiation
        self.source_span = source_span

        # Initialize context with all allowed keys
        # Allowed keys = context_in keys + context keys + defaults
        context = context or {}
        allowed_keys = (
            set(self.context_in.keys())
            | set(context.keys())
            | {"result", "success", "error_msg", "confidence"}
        )

        # Initialize all keys to None
        self.context: dict[str, Any] = {key: None for key in allowed_keys}

        # Set default values
        self.context.update(
            {
                "result": None,
                "success": False,
                "error_msg": "",
                "confidence": None,
            }
        )

        self.status: str = "created"
        self.current_node_id: str | None = None

    @classmethod
    def from_flowsy(cls, flowsy_path: str) -> Flow:
        """Load a flow from a `.flowsy` file."""
        path = Path(flowsy_path)
        if not path.exists():
            raise FileNotFoundError(f"FLOWSY file not found: {flowsy_path}")

        with open(path, encoding="utf-8") as f:
            content = f.read()

        return cls.from_flowsy_string(content)

    @classmethod
    def from_flowsy_string(cls, flowsy_content: str) -> Flow:
        """
        Load a Flow from a FLOWSY string using schema-driven parsing.

        Args:
            flowsy_content: The .flowsy content as a string

        Returns:
            A Flow object
        """
        from agy.config import get_flowsy_grammar_path
        from agy.node import Node
        from agy.source_span import SourceSpan
        from flowsy.flowsy_parser import parse_flowsy

        # Write content to temp file (flowsy_parser expects file path)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".flowsy", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(flowsy_content)
            tmp_path = Path(tmp.name)

        try:
            # Parse with schema-driven FLOWSY parser
            grammar_path = get_flowsy_grammar_path()
            parsed, source_spans_dict = parse_flowsy(grammar_path, tmp_path)

            # Convert source_spans from TypedDict to SourceSpan dataclass
            source_spans: dict[str, SourceSpan] = {}
            for span_path, span_value in source_spans_dict.items():
                span_value_any = cast(Any, span_value)
                if isinstance(span_value_any, dict):
                    source_spans[span_path] = SourceSpan.from_parser_dict(
                        span_value_any
                    )
                elif isinstance(span_value_any, SourceSpan):
                    source_spans[span_path] = span_value_any

            # Extract flow metadata
            flow_name = parsed.get("name", "")
            flow_description = parsed.get("description", "")
            context_in = parsed.get("context_in", {})

            # Parse nodes (delegated to Node.from_flowsy_data)
            nodes = [
                Node.from_flowsy_data(
                    node_name=node_name,
                    node_data=node_data,
                    source_spans=source_spans,
                    node_path=f"nodes.{node_name}",
                )
                for node_name, node_data in parsed.get("nodes", {}).items()
            ]
        finally:
            tmp_path.unlink(missing_ok=True)

        # Second pass: resolve edge targets
        def _is_end_target(target: str) -> bool:
            target_stripped = target.strip()
            if target_stripped == "end":
                return True
            if not target_stripped.startswith("end") or not target_stripped.endswith(
                ")"
            ):
                return False
            # Allow whitespace between function name and parenthesis: "end (...)"
            return target_stripped[3:].lstrip().startswith("(")

        for node in nodes:
            if node.edges:
                for edge in node.edges:
                    if isinstance(edge.target, str):
                        # Handle special "end" target
                        if _is_end_target(edge.target):
                            # Keep as string for end() function
                            continue

                        # Find target node
                        target_node = None
                        for n in nodes:
                            if n.name == edge.target:
                                target_node = n
                                break

                        if not target_node:
                            raise ValueError(
                                f"Edge target node '{edge.target}' not found "
                                f"(referenced from node '{node.name}')"
                            )

                        edge.target = target_node

        # Flow span (use 'name' span if available)
        flow_source_span = source_spans.get("name")

        return cls(
            name=flow_name,
            description=flow_description,
            nodes=nodes,
            context_in=context_in,
            source_span=flow_source_span,
        )

    @classmethod
    def validate(
        cls,
        flowsy_path: str | Path,
        context_in: dict[str, Any] | None = None,
        action_types: list[ActionType] | None = None,
        project_root: Path | None = None,
    ) -> ValidationResult:
        """
        Validate a FLOWSY flow without executing it.

        Args:
            flowsy_path: Path to .flowsy file
            context_in: Optional context objects for type checking
            action_types: Optional custom action types for validation
            project_root: Optional project root for file path resolution (auto-detect if None)

        Returns:
            ValidationResult with errors and warnings
        """
        from agy.validation import (
            ValidationIssue,
            ValidationResult,
            _build_registry,
            _check_context_in_types,
            _check_llm_env_vars,
            _check_node_connections,
            _extract_providers_from_flow,
            validate_flow_actions,
        )

        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        flowsy_path_obj = Path(flowsy_path)

        # 1. Parse FLOWSY and create Flow object
        try:
            flow = cls.from_flowsy(str(flowsy_path_obj))
        except Exception as e:
            errors.append(
                ValidationIssue(
                    level="error",
                    message=f"Failed to parse FLOWSY file: {e}",
                    location="flowsy_file",
                )
            )
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # 2. Structural checks
        errors.extend(_check_node_connections(flow))

        # 3. Type checks
        if context_in is not None:
            errors.extend(_check_context_in_types(flow.context_in, context_in))

        # 4. Build registry
        registry_dict = _build_registry(action_types)

        # 5. Action validation
        errors.extend(
            validate_flow_actions(
                flow, registry_dict, context_in, flowsy_path_obj, project_root
            )
        )

        # 6. LLM checks (only for providers used in flow or default)
        providers_used = _extract_providers_from_flow(flow)
        warnings.extend(_check_llm_env_vars(providers_used))

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings
        )

    async def run(
        self,
        context_in: dict[str, Any] | None = None,
        action_types: list[ActionType] | None = None,
        node: str | None = None,
    ) -> dict[str, Any]:
        """Execute this flow with runtime context and optional start node."""
        from agy.flow_executor import FlowExecutor

        executor = FlowExecutor(action_types=action_types, context_in=context_in)
        return await executor.execute(self, node=node)

    def __str__(self) -> str:
        """Return a human-readable flow summary."""
        lines = [
            f"Flow: {self.name}",
        ]
        if self.description:
            lines.append(f"  Description: {self.description}")
        lines.append(f"  Status: {self.status}")

        if self.context_in:
            lines.append(f"  Context In: {', '.join(self.context_in.keys())}")
        # Show additional context keys (excluding context_in and defaults)
        default_keys = {"result", "success", "error_msg", "confidence"}
        additional_keys = (
            set(self.context.keys()) - set(self.context_in.keys()) - default_keys
        )
        if additional_keys:
            lines.append(f"  Additional Context: {', '.join(sorted(additional_keys))}")

        lines.append(f"\n  Nodes ({len(self.nodes)}):")
        for node in self.nodes:
            node_type = (
                "stochastic" if node.control_type == "stochastic" else "deterministic"
            )
            lines.append(f"    - {node.name} ({node_type})")

            if node.instruction:
                # Truncate long instructions
                instruction = (
                    node.instruction[:60] + "..."
                    if len(node.instruction) > 60
                    else node.instruction
                )
                lines.append(f"      Instruction: {instruction}")

            if node.actions:
                lines.append(f"      Actions ({len(node.actions)}):")
                for action_call in node.actions[:3]:  # Show first 3 actions
                    # For __eval__ actions, show the expression string
                    if action_call.method_name == "__eval__" and action_call.args:
                        expr_str = action_call.args[0][0]
                        output_str = (
                            f"{action_call.output} = "
                            if action_call.output != "result"
                            else ""
                        )
                        action_str = f"{output_str}{expr_str}"
                    else:
                        # Fallback for other action types
                        action_str = (
                            f"{action_call.object_name}.{action_call.method_name}(...)"
                        )
                    lines.append(f"        - {action_str}")
                if len(node.actions) > 3:
                    lines.append(f"        ... and {len(node.actions) - 3} more")

            if node.edges:
                for edge in node.edges:
                    condition = f" [{edge.condition}]" if edge.condition else ""
                    # Handle both Node objects and string targets (e.g., "end" or "end(...)")
                    if isinstance(edge.target, str):
                        target_str = edge.target
                    else:
                        target_str = edge.target.name
                    lines.append(f"      → {target_str}{condition}")
            elif len(self.nodes) > 1:
                # Show implicit edge
                current_idx = self.nodes.index(node)
                if current_idx < len(self.nodes) - 1:
                    lines.append(
                        f"      → {self.nodes[current_idx + 1].name} (implicit)"
                    )

        return "\n".join(lines)
