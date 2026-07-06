"""Additional coverage tests for Flow parsing and rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from agy.flow import Flow
from agy.node import Node


def test_from_flowsy_raises_for_missing_file(tmp_path: Path) -> None:
    """Missing flowsy file should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        Flow.from_flowsy(str(tmp_path / "missing.flowsy"))


def test_flow_str_includes_additional_context_and_nodes() -> None:
    """String representation should contain context and node summaries."""
    nodes = [Node(name="start", control_type="deterministic")]
    flow = Flow(
        name="A",
        description="B",
        nodes=nodes,
        context_in={"email": "Email"},
        context={"invoice": "Invoice"},
    )
    as_text = str(flow)
    assert "Flow: A" in as_text
    assert "Context In: email" in as_text
    assert "Additional Context: invoice" in as_text
    assert "start (deterministic)" in as_text


def test_validate_returns_error_when_parse_fails(tmp_path: Path) -> None:
    """Validation should return structured parse errors."""
    bad = tmp_path / "broken.flowsy"
    bad.write_text("this is not valid flowsy", encoding="utf-8")
    result = Flow.validate(bad)
    assert result.is_valid is False
    assert result.errors
    assert "Failed to parse FLOWSY file" in result.errors[0].message
