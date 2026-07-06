# test/test_flow_parser.py


import pytest

from agy.flow import Flow
from agy.node import Node
from agy.source_span import SourceSpan


def test_parse_flowsy_simple():
    """Test parsing a simple FLOWSY flow"""
    flowsy_content = """name: Test Flow
description: A simple test flow
nodes:
  start:
"""

    flow = Flow.from_flowsy_string(flowsy_content)

    assert flow.name == "Test Flow"
    assert flow.description == "A simple test flow"
    assert len(flow.nodes) == 1
    assert flow.nodes[0].name == "start"
    assert flow.nodes[0].control_type == "deterministic"


def test_parse_flowsy_with_context():
    """Test parsing flow with context_in"""
    flowsy_content = """name: Flow with Context
description: Flow with context definitions
context_in:
  email: Email
nodes:
  start:
"""

    flow = Flow.from_flowsy_string(flowsy_content)

    assert flow.context_in == {"email": "Email"}
    # Check that context contains all expected keys
    assert "email" in flow.context
    # Check defaults
    assert "result" in flow.context
    assert "success" in flow.context
    assert flow.context["success"] is False


def test_parse_flowsy_with_edges():
    """Test parsing flow with edges"""
    flowsy_content = """name: Flow with Edges
description: Flow with node edges
nodes:
  node1:
    edges:
      - True: node2
      - condition == true: node3
  node2:
  node3:
"""

    flow = Flow.from_flowsy_string(flowsy_content)

    assert len(flow.nodes) == 3
    node1 = flow.nodes[0]
    assert len(node1.edges) == 2
    assert node1.edges[0].target.name == "node2"
    assert node1.edges[0].condition == "True"
    assert node1.edges[1].target.name == "node3"
    assert node1.edges[1].condition == "condition == true"


def test_parse_flowsy_with_edges_string_format():
    """Test parsing flow with edges using string format: 'condition: target'"""
    flowsy_content = """name: Flow with String Edges
description: Flow with edges in string format
nodes:
  classify:
    edges:
      - True: default_target
      - confidence < 0.5: low_confidence
      - category == "sales": handle_sales
      - category == "support": handle_support
  default_target:
  low_confidence:
  handle_sales:
  handle_support:
"""

    flow = Flow.from_flowsy_string(flowsy_content)

    assert len(flow.nodes) == 5
    classify_node = flow.nodes[0]
    assert len(classify_node.edges) == 4

    # First edge: True → condition="True"
    assert classify_node.edges[0].target.name == "default_target"
    assert classify_node.edges[0].condition == "True"

    # Second edge: string with colon → condition="confidence < 0.5"
    assert classify_node.edges[1].target.name == "low_confidence"
    assert classify_node.edges[1].condition == "confidence < 0.5"

    # Third edge: string with colon and quotes → condition='category == "sales"'
    assert classify_node.edges[2].target.name == "handle_sales"
    assert classify_node.edges[2].condition == 'category == "sales"'

    # Fourth edge: string with colon and quotes → condition='category == "support"'
    assert classify_node.edges[3].target.name == "handle_support"
    assert classify_node.edges[3].condition == 'category == "support"'


def test_parse_flowsy_with_final_fallback_edge_without_condition():
    """Test parsing final fallback edge shorthand without `True:`."""
    flowsy_content = """name: Flow with Fallback Edge Shorthand
nodes:
  classify:
    edges:
      - confidence < 0.5: manual_review
      - default_target
  manual_review:
  default_target:
"""

    flow = Flow.from_flowsy_string(flowsy_content)

    classify_node = flow.nodes[0]
    assert len(classify_node.edges) == 2
    assert classify_node.edges[0].target.name == "manual_review"
    assert classify_node.edges[0].condition == "confidence < 0.5"
    assert classify_node.edges[1].target.name == "default_target"
    assert classify_node.edges[1].condition == "True"


def test_parse_flowsy_rejects_non_final_fallback_edge_without_condition():
    """Fallback edge shorthand is only valid as the last edge."""
    flowsy_content = """name: Flow with Invalid Fallback Edge Shorthand
nodes:
  classify:
    edges:
      - default_target
      - confidence < 0.5: manual_review
  manual_review:
  default_target:
"""

    with pytest.raises(ValueError, match="Fallback edge without condition"):
        Flow.from_flowsy_string(flowsy_content)


def test_parse_flowsy_implicit_edge():
    """Test that nodes without edges terminate automatically (no implicit edges)"""
    flowsy_content = """name: Flow without Edges
description: Flow with nodes without edges
nodes:
  node1:
  node2:
"""

    flow = Flow.from_flowsy_string(flowsy_content)

    # Nodes without edges should have empty edges list (will terminate automatically)
    assert flow.nodes[0].edges is None or len(flow.nodes[0].edges) == 0


def test_parse_flowsy_auto_create_end_nodes():
    """Test that end keyword is recognized as string (not a node)"""
    flowsy_content = """name: Flow with End Keyword
description: Flow that references end keyword
nodes:
  process_result:
    edges:
      - True: end
"""

    flow = Flow.from_flowsy_string(flowsy_content)

    # Should have only 1 node: process_result (end is not a node anymore)
    assert len(flow.nodes) == 1

    # Check that process_result node exists and has edges
    process_node = next(node for node in flow.nodes if node.name == "process_result")
    assert len(process_node.edges) == 1
    # end is now a string keyword, not a node
    assert process_node.edges[0].target == "end"
    assert isinstance(process_node.edges[0].target, str)


def test_parse_flowsy_end_nodes_no_implicit_edges():
    """Test that end keyword works and nodes without edges terminate"""
    # Case 1: End keyword used in edge (not a node)
    flowsy_content = """name: Flow with End Keyword
description: End keyword used in edge
nodes:
  start:
    edges:
      - True: end
"""

    flow = Flow.from_flowsy_string(flowsy_content)

    # Should have only 1 node (end is keyword, not node)
    assert len(flow.nodes) == 1
    start_node = flow.nodes[0]
    assert len(start_node.edges) == 1
    assert start_node.edges[0].target == "end"
    assert isinstance(start_node.edges[0].target, str)

    # Case 2: Node without edges (will terminate automatically)
    flowsy_content2 = """name: Flow without Edges
nodes:
  process:
"""

    flow2 = Flow.from_flowsy_string(flowsy_content2)

    # Node without edges should have empty edges list
    process_node = flow2.nodes[0]
    assert process_node.edges is None or process_node.edges == []


def test_parse_flowsy_end_call_with_space_before_parenthesis():
    """end (...) with whitespace should be treated as end() target."""
    flowsy_content = """name: End Call With Space
nodes:
  start:
    edges:
      - True: end (success=True, result="ok")
"""

    flow = Flow.from_flowsy_string(flowsy_content)
    start = flow.nodes[0]
    assert start.edges
    assert isinstance(start.edges[0].target, str)
    assert start.edges[0].target.strip().startswith("end")


def test_parse_flowsy_node_name_starting_with_end_resolves_as_regular_node():
    """Node names like end_review must not be treated as end()."""
    flowsy_content = """name: End Prefix Node
nodes:
  start:
    edges:
      - True: end_review
  end_review:
"""

    flow = Flow.from_flowsy_string(flowsy_content)
    start = next(node for node in flow.nodes if node.name == "start")
    assert start.edges
    assert isinstance(start.edges[0].target, Node)
    assert start.edges[0].target.name == "end_review"


def test_parse_flowsy_node_order_preserved():
    """Test that node order is preserved (Python 3.7+ dict insertion order)"""
    flowsy_content = """name: Order Test
nodes:
  first_node:
  second_node:
  third_node:
"""

    flow = Flow.from_flowsy_string(flowsy_content)

    assert len(flow.nodes) == 3
    assert flow.nodes[0].name == "first_node"
    assert flow.nodes[1].name == "second_node"
    assert flow.nodes[2].name == "third_node"


def test_parse_flowsy_with_actions():
    """Test parsing flow with actions"""
    flowsy_content = """name: Flow with Actions
nodes:
  start:
    actions:
      - result = add(a=1, b=2)
      - show("Result:", result)
"""

    flow = Flow.from_flowsy_string(flowsy_content)

    start_node = flow.nodes[0]
    assert len(start_node.actions) == 2
    # Actions are parsed as __eval__ ActionCalls via AST
    assert start_node.actions[0].method_name == "__eval__"
    assert start_node.actions[1].method_name == "__eval__"


def test_parse_flowsy_source_spans_assigned():
    """Test that SourceSpans are correctly assigned to all objects"""
    # Line numbers (1-based):
    # 1: name: Flow with SourceSpans
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
    flowsy_content = """name: Flow with SourceSpans
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

    flow = Flow.from_flowsy_string(flowsy_content)

    # Flow should have source_span (from "name:" line)
    assert flow.source_span is not None
    assert isinstance(flow.source_span, SourceSpan)
    assert flow.source_span.start_line == 1
    assert "name:" in flow.source_span.content

    # first_node should have source_span
    first_node = flow.nodes[0]
    assert first_node.source_span is not None
    assert isinstance(first_node.source_span, SourceSpan)
    assert first_node.source_span.start_line == 3
    assert "first_node:" in first_node.source_span.content

    # first_node actions should have source_spans
    assert len(first_node.actions) == 2

    action1 = first_node.actions[0]
    assert action1.source_span is not None
    assert isinstance(action1.source_span, SourceSpan)
    assert action1.source_span.start_line == 5
    assert "action_one" in action1.source_span.content

    action2 = first_node.actions[1]
    assert action2.source_span is not None
    assert action2.source_span.start_line == 6
    assert "action_two" in action2.source_span.content

    # first_node edges should have source_spans
    assert len(first_node.edges) == 1

    edge1 = first_node.edges[0]
    assert edge1.source_span is not None
    assert isinstance(edge1.source_span, SourceSpan)
    assert edge1.source_span.start_line == 8
    assert "True" in edge1.source_span.content
    assert "second_node" in edge1.source_span.content

    # second_node should have source_span
    second_node = flow.nodes[1]
    assert second_node.source_span is not None
    assert second_node.source_span.start_line == 9
    assert "second_node:" in second_node.source_span.content

    # second_node actions should have source_spans
    assert len(second_node.actions) == 1
    action3 = second_node.actions[0]
    assert action3.source_span is not None
    assert action3.source_span.start_line == 11
    assert "action_three" in action3.source_span.content


def test_source_span_str_representation():
    """Test SourceSpan __str__ for single and multiline spans"""
    # Single line span
    single_line = SourceSpan(
        file_name="test.flowsy",
        start_line=5,
        end_line=5,
        content="      - action_one()",
    )
    assert "Line 5:" in str(single_line)
    assert "action_one" in str(single_line)

    # Multiline span
    multiline = SourceSpan(
        file_name="test.flowsy",
        start_line=3,
        end_line=8,
        content="  first_node:\n    actions:\n      - action_one()",
    )
    assert "Lines 3-8:" in str(multiline)
    assert "first_node:" in str(multiline)
