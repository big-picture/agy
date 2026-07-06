# test/test_flow.py

import pytest

from agy.action_call import ActionCall
from agy.action_type import ActionType
from agy.edge import Edge
from agy.flow import Flow
from agy.node import Node


def test_flow_creation():
    """Test dass Flow erstellt werden kann"""
    flow = Flow(name="Test Flow", description="A simple test flow", nodes=[])

    assert flow.name == "Test Flow"
    assert flow.description == "A simple test flow"
    assert flow.nodes == []


def test_flow_with_nodes():
    """Test dass Flow mit Nodes erstellt werden kann"""
    nodes = [
        Node(name="node1", control_type="deterministic"),
        Node(name="node2", control_type="stochastic"),
    ]
    flow = Flow(
        name="Flow with Nodes",
        description="Flow containing multiple nodes",
        nodes=nodes,
    )

    assert len(flow.nodes) == 2
    assert flow.nodes[0].name == "node1"
    assert flow.nodes[1].name == "node2"


def test_flow_default_values():
    """Test dass Flow Default-Werte korrekt setzt"""
    flow = Flow(name="Default Flow", description="Testing defaults", nodes=[])

    assert flow.status == "created"
    assert flow.current_node_id is None
    assert flow.context["success"] is False
    assert flow.context["error_msg"] == ""
    assert flow.context["confidence"] is None


# test_flow_execute() removed - Flow execution is now handled by FlowExecutor


def test_flow_context():
    """Test dass Flow Context beibehalten wird"""
    flow = Flow(name="Context Flow", description="Testing context", nodes=[])

    # Context Default-Werte
    assert flow.context["success"] is False

    # Context ändern
    flow.context["success"] = True
    flow.context["category"] = "email"

    assert flow.context["success"] is True
    assert flow.context["category"] == "email"


def test_flow_with_context_list():
    """Test dass Flow mit context list erstellt werden kann"""
    flow = Flow(
        name="Custom Context Flow",
        description="Testing context list",
        nodes=[],
        context={"pricing_table": "PricingTable", "user_data": "UserData"},
    )

    # Check that additional context keys are initialized
    assert "pricing_table" in flow.context
    assert "user_data" in flow.context
    assert flow.context["pricing_table"] is None
    assert flow.context["user_data"] is None
    # Defaults should still be present
    assert "success" in flow.context
    assert flow.context["success"] is False


def test_flow_from_flowsy_string_with_stochastic_node():
    """Test that FLOWSY stochastic node fields are parsed into Node."""
    flow = Flow.from_flowsy_string(
        """
name: Stochastic Flow
context_in:
  consc: FakeAgent
nodes:
  summarize_yesterday:
    type: stochastic
    agent: consc
    requests:
      - "Read yesterday's email."
      - "Add answered status."
    options:
      mode: careful
    output: email_report_md
    message: agent_message
    edges:
      - success == True: end()
"""
    )

    node = flow.nodes[0]
    assert node.name == "summarize_yesterday"
    assert node.control_type == "stochastic"
    assert node.agent == "consc"
    assert node.requests == ["Read yesterday's email.", "Add answered status."]
    assert node.options == {"mode": "careful"}
    assert node.output == "email_report_md"
    assert node.message == "agent_message"
    assert node.edges[0].condition == "success == True"


def test_flow_from_flowsy_string_preserves_fstring_stochastic_request():
    """Test that f-string requests remain evaluable after FLOWSY parsing."""
    flow = Flow.from_flowsy_string(
        """
name: Stochastic Request Eval Flow
context_in:
  consc: FakeAgent
nodes:
  screen_project:
    type: stochastic
    agent: consc
    requests:
      - f'Find all mails discussing {project_name} in all different spellings'
    output: screening_result
"""
    )

    node = flow.nodes[0]
    assert node.requests == [
        "f'Find all mails discussing {project_name} in all different spellings'"
    ]


# evaluate_condition tests moved to test_edge.py - condition evaluation is now handled by Edge.evaluate()

# test_flow_execute_with_context_in() removed - Flow execution is now handled by FlowExecutor
# See test_flow_executor.py for execution tests


# test_flow_execute_invalid_kwargs() removed - Flow execution is now handled by FlowExecutor
# See test_flow_executor.py::test_flow_executor_validation for validation tests


@pytest.mark.asyncio
async def test_flow_run_async_with_optional_node():
    """Test Flow.run facade with optional start node."""

    def add(a: int, b: int) -> int:
        return a + b

    action_type = ActionType(
        object_name="global_function", method_name="add", callable=add
    )
    action_start = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("add(2, 2)", False)],
        kwargs={},
        output="result",
    )
    action_mid = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("add(7, 8)", False)],
        kwargs={},
        output="result",
    )

    start = Node(name="start", control_type="deterministic", actions=[action_start])
    mid = Node(name="mid", control_type="deterministic", actions=[action_mid])
    end = Node(name="end", control_type="deterministic", actions=None, edges=[])
    start.edges = [Edge(target=end, condition="True")]
    mid.edges = [Edge(target=end, condition="True")]

    flow = Flow(name="Flow Run Test", description="run()", nodes=[start, mid, end])
    context = await flow.run(action_types=[action_type], context_in={}, node="mid")

    assert context["result"] == 15
    assert context["success"] is True
