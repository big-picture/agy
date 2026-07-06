from __future__ import annotations

import json
from pathlib import Path

from flowsy.flowsy_parser import (
    parse_flowsy,
    split_colon_left_quote_aware,
    split_colon_right_quote_aware,
)


def test_parse_reference_flow_matches_reference_json() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    grammar = repo_root / "src" / "flowsy" / "flowsy_grammar.v0.1.yaml"
    flow = repo_root / "src" / "flowsy" / "reference_flow.flowsy"
    expected_json = repo_root / "src" / "flowsy" / "reference_flow_parsed.json"

    expected = json.loads(expected_json.read_text(encoding="utf-8"))
    got, spans = parse_flowsy(grammar, flow)

    assert got == expected


def test_parse_edges_accept_final_fallback_without_condition(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    grammar = repo_root / "src" / "flowsy" / "flowsy_grammar.v0.1.yaml"
    flow_file = tmp_path / "flow.flowsy"
    flow_file.write_text(
        """name: Fallback Edge Shorthand
nodes:
  start:
    edges:
      - confidence < 0.5: manual_review
      - finalize
  manual_review:
  finalize:
""",
        encoding="utf-8",
    )

    got, spans = parse_flowsy(grammar, flow_file)

    assert got["nodes"]["start"]["edges"] == [
        {"confidence < 0.5": "manual_review"},
        "finalize",
    ]
    assert "nodes.start.edges[1]" in spans


def test_schema_change_rename_key_description_to_explanation(tmp_path: Path) -> None:
    """
    The parser must not hardcode top-level keys. If the schema changes, parsing behavior changes
    without code changes.
    """

    schema_text = """
flowsy_version: 0.2
meta:
  indentation: 2
  dict_separator: ":"
  list_bullet: "-"

flow:
  content_type: dict
  fix_name_entries:
    - name:
      occurrence: "?"
      content_type: scalar
    - explanation:
      occurrence: "?"
      content_type: scalar
    - nodes:
      occurrence: "1"
      content_type: dict node

node:
  content_type: dict
  fix_name_entries:
    - actions:
      occurrence: "?"
      content_type: list action

action:
  content_type: scalar
"""
    flow_text = """
explanation: hello
nodes:
  n1:
    actions:
      - show("x")
"""
    schema_file = tmp_path / "flowsy.v0.2.YAML"
    flow_file = tmp_path / "flow.flowsy"
    schema_file.write_text(schema_text.strip() + "\n", encoding="utf-8")
    flow_file.write_text(flow_text.strip() + "\n", encoding="utf-8")

    out, spans = parse_flowsy(schema_file, flow_file)
    assert out["explanation"] == "hello"
    assert out["nodes"]["n1"]["actions"] == ['show("x")']


def test_parse_flowsy_returns_source_spans() -> None:
    """Test that parse_flowsy returns SourceSpan for all objects."""
    repo_root = Path(__file__).resolve().parents[1]
    grammar = repo_root / "src" / "flowsy" / "flowsy_grammar.v0.1.yaml"
    flow = repo_root / "src" / "flowsy" / "reference_flow.flowsy"

    parsed, spans = parse_flowsy(grammar, flow)

    # Verify spans is a dict
    assert isinstance(spans, dict)

    # 1. Flow-level scalars
    assert "name" in spans
    name_span = spans["name"]
    assert name_span["start_line"] == 1
    assert name_span["end_line"] == 1
    assert "Travel Insurance Email Routing" in name_span["content"]

    assert "description" in spans
    desc_span = spans["description"]
    assert desc_span["start_line"] == 2
    assert desc_span["end_line"] == 2

    # 2. context_in (dict of key_value_pairs)
    assert "context_in" in spans
    assert "context_in.email" in spans
    email_span = spans["context_in.email"]
    assert email_span["start_line"] == email_span["end_line"]  # single line
    assert "email" in email_span["content"]

    # 3. nodes dict
    assert "nodes" in spans
    nodes_span = spans["nodes"]
    assert nodes_span["start_line"] < nodes_span["end_line"]  # multiline

    # 4. Specific node (multiline)
    assert "nodes.classify_email" in spans
    node_span = spans["nodes.classify_email"]
    assert node_span["start_line"] < node_span["end_line"]  # multiline
    assert "classify_email:" in node_span["content"]

    # 5. Actions list
    assert "nodes.classify_email.actions" in spans
    actions_span = spans["nodes.classify_email.actions"]
    assert (
        actions_span["start_line"] < actions_span["end_line"]
    )  # multiline (multiple actions)

    # 6. Specific action (single line)
    assert "nodes.classify_email.actions[0]" in spans
    action_span = spans["nodes.classify_email.actions[0]"]
    assert action_span["start_line"] == action_span["end_line"]  # single line
    assert "show" in action_span["content"]

    # 7. Edges list
    assert "nodes.classify_email.edges" in spans
    _ = spans["nodes.classify_email.edges"]

    # 8. Specific edge (single line)
    assert "nodes.classify_email.edges[0]" in spans
    edge_span = spans["nodes.classify_email.edges[0]"]
    assert edge_span["start_line"] == edge_span["end_line"]  # single line

    # 9. All spans have required fields
    for path, span in spans.items():
        assert "file_name" in span, f"Missing file_name in span for {path}"
        assert "start_line" in span, f"Missing start_line in span for {path}"
        assert "end_line" in span, f"Missing end_line in span for {path}"
        assert "content" in span, f"Missing content in span for {path}"
        assert span["start_line"] <= span["end_line"], (
            f"start_line > end_line in span for {path}"
        )
        assert span["start_line"] >= 1, f"Invalid start_line in span for {path}"


def test_source_spans_for_simple_flow(tmp_path: Path) -> None:
    """Test SourceSpan with a simple flow to verify exact line numbers."""
    schema_text = """
flowsy_version: 0.1
meta:
  indentation: 2
  dict_separator: ":"
  list_bullet: "-"

flow:
  content_type: dict
  fix_name_entries:
    - name:
      occurrence: "1"
      content_type: scalar
    - nodes:
      occurrence: "1"
      content_type: dict node

node:
  content_type: dict
  fix_name_entries:
    - actions:
      occurrence: "?"
      content_type: list action
    - edges:
      occurrence: "?"
      content_type: list edge

action:
  content_type: scalar

edge:
  content_type: key_value_pair
  parsing: right
"""
    # Lines are numbered 1-based:
    # 1: name: Test Flow
    # 2: nodes:
    # 3:   first_node:
    # 4:     actions:
    # 5:       - action_one()
    # 6:       - action_two()
    # 7:     edges:
    # 8:       - True: second_node
    # 9:   second_node:
    # 10:    actions:
    # 11:      - action_three()
    flow_text = """name: Test Flow
nodes:
  first_node:
    actions:
      - action_one()
      - action_two()
    edges:
      - True: second_node
  second_node:
    actions:
      - action_three()
"""
    schema_file = tmp_path / "schema.yaml"
    flow_file = tmp_path / "flow.flowsy"
    schema_file.write_text(schema_text.strip() + "\n", encoding="utf-8")
    flow_file.write_text(flow_text.strip() + "\n", encoding="utf-8")

    parsed, spans = parse_flowsy(schema_file, flow_file)

    # Verify parsed values
    assert parsed["name"] == "Test Flow"
    assert "first_node" in parsed["nodes"]
    assert "second_node" in parsed["nodes"]

    # Verify spans with exact line numbers
    assert spans["name"]["start_line"] == 1
    assert spans["name"]["end_line"] == 1

    assert spans["nodes"]["start_line"] == 3  # first node line

    # first_node spans lines 3-8
    assert spans["nodes.first_node"]["start_line"] == 3
    assert spans["nodes.first_node"]["end_line"] == 8

    # first_node actions span lines 5-6
    assert spans["nodes.first_node.actions"]["start_line"] == 5
    assert spans["nodes.first_node.actions"]["end_line"] == 6

    # Individual actions
    assert spans["nodes.first_node.actions[0]"]["start_line"] == 5
    assert spans["nodes.first_node.actions[0]"]["end_line"] == 5
    assert "action_one" in spans["nodes.first_node.actions[0]"]["content"]

    assert spans["nodes.first_node.actions[1]"]["start_line"] == 6
    assert spans["nodes.first_node.actions[1]"]["end_line"] == 6
    assert "action_two" in spans["nodes.first_node.actions[1]"]["content"]

    # first_node edges
    assert spans["nodes.first_node.edges"]["start_line"] == 8
    assert spans["nodes.first_node.edges"]["end_line"] == 8
    assert spans["nodes.first_node.edges[0]"]["start_line"] == 8

    # second_node
    assert spans["nodes.second_node"]["start_line"] == 9
    assert spans["nodes.second_node.actions[0]"]["start_line"] == 11
    assert "action_three" in spans["nodes.second_node.actions[0]"]["content"]


def test_split_colon_left_quote_aware() -> None:
    left, right = split_colon_left_quote_aware("email: Email", sep=":")
    assert left.strip() == "email"
    assert right.strip() == "Email"

    left, right = split_colon_left_quote_aware('k: "a:b:c"', sep=":")
    assert left.strip() == "k"
    assert right.strip() == '"a:b:c"'


def test_split_colon_right_quote_aware() -> None:
    left, right = split_colon_right_quote_aware('a == "x:y": target', sep=":")
    assert left.strip() == 'a == "x:y"'
    assert right.strip() == "target"

    left, right = split_colon_right_quote_aware('a:b:"c:d"', sep=":")
    assert left.strip() == "a:b"
    assert right.strip() == '"c:d"'
