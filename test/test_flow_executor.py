# test/test_flow_executor.py

import pytest

from agy.action_call import ActionCall
from agy.action_type import ActionType
from agy.edge import Edge
from agy.flow import Flow
from agy.flow_executor import FlowExecutor
from agy.node import Node
from agy.node_executor import AgentRequestResult


@pytest.mark.asyncio
async def test_flow_executor_validation():
    """Test that FlowExecutor validates context_in keys"""
    flow = Flow(
        name="Test Flow", description="Test", nodes=[], context_in={"email": "Email"}
    )

    # Missing required key
    executor = FlowExecutor(action_types=None, context_in={})
    with pytest.raises(ValueError, match="Missing context_in keys"):
        await executor.execute(flow)

    # Extra key
    executor2 = FlowExecutor(
        action_types=None, context_in={"email": None, "extra": None}
    )
    with pytest.raises(ValueError, match="Extra context_in keys"):
        await executor2.execute(flow)


@pytest.mark.asyncio
async def test_flow_executor_simple_flow():
    """Test executing a simple flow with one deterministic node"""

    # Create a simple add function
    def add(a: int, b: int) -> int:
        return a + b

    # Register action type
    action_type = ActionType(
        object_name="global_function", method_name="add", callable=add
    )

    # Create action call (__eval__ format)
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("add(5, 3)", False)],
        kwargs={},
        output="result",
    )

    # Create simple flow
    node1 = Node(name="start", control_type="deterministic", actions=[action_call])

    # Create end node
    terminate = Node(name="end", control_type="deterministic", actions=None, edges=[])

    node1.edges = [Edge(target=terminate, condition="True")]

    flow = Flow(
        name="Simple Flow",
        description="Test flow",
        nodes=[node1, terminate],
        context_in={},
    )

    # Execute
    executor = FlowExecutor(action_types=[action_type], context_in={})
    context = await executor.execute(flow)

    assert context["result"] == 8
    assert context["success"] is True
    assert "end" in [n.name for n in flow.nodes]


@pytest.mark.asyncio
async def test_flow_executor_with_context_in():
    """Test executing a flow with context_in objects"""

    class Calculator:
        def add(self, a: int, b: int) -> int:
            return a + b

    calc = Calculator()

    # Create action call for calculator (__eval__ format)
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("calc.add(a, b)", False)],
        kwargs={},
        output="result",
    )

    # Create node
    terminate = Node(name="end", control_type="deterministic", actions=None, edges=[])

    node1 = Node(name="start", control_type="deterministic", actions=[action_call])
    node1.edges = [Edge(target=terminate, condition="True")]

    flow = Flow(
        name="Calculator Flow",
        description="Test with context object",
        nodes=[node1, terminate],
        context_in={"calc": "Calculator"},
    )

    # Set context values in flow (will be copied during execution)
    flow.context["a"] = 5
    flow.context["b"] = 3

    executor = FlowExecutor(action_types=None, context_in={"calc": calc})
    context = await executor.execute(flow)

    assert context["result"] == 8
    assert context["success"] is True


@pytest.mark.asyncio
async def test_flow_executor_starts_from_optional_node():
    """Test starting execution from a specific node name."""

    def add(a: int, b: int) -> int:
        return a + b

    action_type = ActionType(
        object_name="global_function", method_name="add", callable=add
    )

    start_action = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("add(1, 1)", False)],
        kwargs={},
        output="result",
    )
    mid_action = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("add(10, 5)", False)],
        kwargs={},
        output="result",
    )

    start = Node(name="start", control_type="deterministic", actions=[start_action])
    mid = Node(name="mid", control_type="deterministic", actions=[mid_action])
    end = Node(name="end", control_type="deterministic", actions=None, edges=[])

    start.edges = [Edge(target=end, condition="True")]
    mid.edges = [Edge(target=end, condition="True")]

    flow = Flow(
        name="Start Node Flow",
        description="Test optional start node",
        nodes=[start, mid, end],
        context_in={},
    )

    executor = FlowExecutor(action_types=[action_type], context_in={})
    context = await executor.execute(flow, node="mid")

    assert context["result"] == 15
    assert context["success"] is True


@pytest.mark.asyncio
async def test_flow_executor_invalid_optional_node():
    """Test error when start node name does not exist."""
    start = Node(name="start", control_type="deterministic", actions=[])
    flow = Flow(
        name="Invalid Start Node Flow",
        description="Test invalid start node",
        nodes=[start],
        context_in={},
    )

    executor = FlowExecutor(action_types=None, context_in={})
    with pytest.raises(ValueError, match="Start node 'unknown' not found"):
        await executor.execute(flow, node="unknown")


@pytest.mark.asyncio
async def test_flow_executor_multi_node_flow():
    """Test executing a flow with multiple nodes"""

    def add(a: int, b: int) -> int:
        return a + b

    def multiply(x: int, y: int) -> int:
        return x * y

    action_type1 = ActionType(
        object_name="global_function", method_name="add", callable=add
    )

    action_type2 = ActionType(
        object_name="global_function", method_name="multiply", callable=multiply
    )

    action_call1 = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("add(a, b)", False)],
        kwargs={},
        output="sum",
    )

    # For second action, map sum to x parameter
    action_call2 = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("multiply(sum, y)", False)],
        kwargs={},
        output="result",
    )

    node1 = Node(name="start", control_type="deterministic", actions=[action_call1])
    node2 = Node(name="multiply", control_type="deterministic", actions=[action_call2])
    terminate = Node(name="end", control_type="deterministic", actions=None, edges=[])

    node1.edges = [Edge(target=node2, condition="True")]
    node2.edges = [Edge(target=terminate, condition="True")]

    flow = Flow(
        name="Multi Node Flow",
        description="Test flow with multiple nodes",
        nodes=[node1, node2, terminate],
        context_in={},
    )

    flow.context["a"] = 2
    flow.context["b"] = 3
    flow.context["y"] = 2

    executor = FlowExecutor(action_types=[action_type1, action_type2], context_in={})
    context = await executor.execute(flow)

    assert context["sum"] == 5
    assert context["result"] == 10  # sum (5) * y (2) = 10
    assert context["success"] is True


@pytest.mark.asyncio
async def test_flow_executor_conditional_flow():
    """Test executing a flow with conditional edges"""

    def check_value(x: int) -> bool:
        return x > 5

    action_type = ActionType(
        object_name="global_function", method_name="check_value", callable=check_value
    )

    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("check_value(x)", False)],
        kwargs={},
        output="result",
    )

    node1 = Node(name="check", control_type="deterministic", actions=[action_call])
    node2 = Node(name="high", control_type="deterministic", actions=[])
    terminate = Node(name="end", control_type="deterministic", actions=None, edges=[])

    node1.edges = [
        Edge(target=node2, condition="result == True"),
        Edge(target=terminate, condition="True"),
    ]
    node2.edges = [Edge(target=terminate, condition="True")]

    flow = Flow(
        name="Conditional Flow",
        description="Test conditional flow",
        nodes=[node1, node2, terminate],
        context_in={},
    )

    executor = FlowExecutor(action_types=[action_type], context_in={})

    # Test with x=10 (should go to node2)
    flow.context["x"] = 10
    context1 = await executor.execute(flow)
    assert context1["result"] is True

    # Test with x=3 (should terminate directly)
    flow.context["x"] = 3
    context2 = await executor.execute(flow)
    assert context2["result"] is False


@pytest.mark.asyncio
async def test_flow_executor_empty_nodes():
    """Test that FlowExecutor raises error for empty flow"""
    flow = Flow(
        name="Empty Flow", description="Flow with no nodes", nodes=[], context_in={}
    )

    executor = FlowExecutor(action_types=None, context_in={})

    with pytest.raises(ValueError, match="Flow has no nodes"):
        await executor.execute(flow)


@pytest.mark.asyncio
async def test_flow_executor_stochastic_node_runs_requests():
    """Test executing a stochastic node with multiple agent requests."""

    class FakeAgent:
        def __init__(self):
            self.calls = []

        async def run(self, request, options=None, previous_output=None):
            self.calls.append(
                {
                    "request": request,
                    "options": options,
                    "previous_output": previous_output,
                }
            )
            return AgentRequestResult(
                outputs=[f"output:{request}"],
                output=f"final:{request}",
                message=f"message:{request}",
                success=True,
            )

    agent = FakeAgent()
    stochastic_node = Node(
        name="summarize",
        control_type="stochastic",
        agent="consc",
        requests=["First request.", "Second request."],
        options={"mode": "careful"},
        output="email_report_md",
        message="agent_message",
    )
    terminate = Node(name="end", control_type="deterministic", actions=None, edges=[])
    stochastic_node.edges = [Edge(target=terminate, condition="success == True")]

    flow = Flow(
        name="Stochastic Flow",
        description="Test stochastic node",
        nodes=[stochastic_node, terminate],
        context_in={"consc": "FakeAgent"},
    )

    executor = FlowExecutor(action_types=None, context_in={"consc": agent})
    context = await executor.execute(flow)

    assert context["email_report_md"] == "final:Second request."
    assert context["agent_message"] == "message:Second request."
    assert context["agent_outputs"] == [
        "output:First request.",
        "output:Second request.",
    ]
    assert context["result"] == "final:Second request."
    assert context["success"] is True
    assert context["error_msg"] == ""
    assert agent.calls[0]["previous_output"] is None
    assert agent.calls[1]["previous_output"] == "final:First request."


@pytest.mark.asyncio
async def test_flow_executor_stochastic_node_evaluates_request_fstrings():
    """Test that stochastic request expressions use the flow eval context."""

    class FakeAgent:
        def __init__(self):
            self.calls = []

        async def run(self, request, options=None, previous_output=None):
            self.calls.append(request)
            return AgentRequestResult(
                outputs=[request],
                output=request,
                message="done",
                success=True,
            )

    project_action = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("'Apollo'", False)],
        kwargs={},
        output="project_name",
    )
    prepare_node = Node(
        name="prepare",
        control_type="deterministic",
        actions=[project_action],
    )
    stochastic_node = Node(
        name="screen",
        control_type="stochastic",
        agent="consc",
        requests=[
            "f'Find all mails discussing {project_name} in all different spellings in the mails of the last two weeks'"
        ],
        output="screening_request",
        message="agent_message",
    )
    terminate = Node(name="end", control_type="deterministic", actions=None, edges=[])
    prepare_node.edges = [Edge(target=stochastic_node, condition="True")]
    stochastic_node.edges = [Edge(target=terminate, condition="success == True")]

    agent = FakeAgent()
    flow = Flow(
        name="Request Eval Flow",
        description="Test request eval",
        nodes=[prepare_node, stochastic_node, terminate],
        context_in={"consc": "FakeAgent"},
    )

    executor = FlowExecutor(action_types=None, context_in={"consc": agent})
    context = await executor.execute(flow)

    expected = (
        "Find all mails discussing Apollo in all different spellings in the mails "
        "of the last two weeks"
    )
    assert agent.calls == [expected]
    assert context["screening_request"] == expected


@pytest.mark.asyncio
async def test_flow_executor_stochastic_plain_text_request_is_unchanged():
    """Test that normal natural-language requests are not forced through eval."""

    class FakeAgent:
        def __init__(self):
            self.calls = []

        async def run(self, request, options=None, previous_output=None):
            self.calls.append(request)
            return request

    agent = FakeAgent()
    stochastic_node = Node(
        name="summarize",
        control_type="stochastic",
        agent="consc",
        requests=["Create a report."],
        output="summary",
    )
    terminate = Node(name="end", control_type="deterministic", actions=None, edges=[])
    stochastic_node.edges = [Edge(target=terminate, condition="success == True")]
    flow = Flow(
        name="Plain Request Flow",
        description="Test plain request",
        nodes=[stochastic_node, terminate],
        context_in={"consc": "FakeAgent"},
    )

    executor = FlowExecutor(action_types=None, context_in={"consc": agent})
    context = await executor.execute(flow)

    assert agent.calls == ["Create a report."]
    assert context["summary"] == "Create a report."


@pytest.mark.asyncio
async def test_flow_executor_stochastic_request_expression_must_evaluate_to_string():
    """Test that non-string request expressions fail before calling the agent."""

    class FakeAgent:
        def __init__(self):
            self.calls = []

        async def run(self, request, options=None, previous_output=None):
            self.calls.append(request)
            return request

    agent = FakeAgent()
    stochastic_node = Node(
        name="summarize",
        control_type="stochastic",
        agent="consc",
        requests=["1 + 1"],
        output="summary",
    )
    error_node = Node(name="error_handler", control_type="deterministic", actions=[])
    stochastic_node.edges = [Edge(target=error_node, condition="success == False")]
    flow = Flow(
        name="Non String Request Flow",
        description="Test non-string request expression",
        nodes=[stochastic_node, error_node],
        context_in={"consc": "FakeAgent"},
    )

    executor = FlowExecutor(action_types=None, context_in={"consc": agent})
    context = await executor.execute(flow)

    assert agent.calls == []
    assert context["success"] is False
    assert "must evaluate to str" in context["error_msg"]


@pytest.mark.asyncio
async def test_flow_executor_stochastic_node_routes_errors():
    """Test that stochastic node errors set context and use normal edge routing."""

    class BrokenAgent:
        pass

    stochastic_node = Node(
        name="summarize",
        control_type="stochastic",
        agent="consc",
        requests=["First request."],
        output="email_report_md",
        message="agent_message",
    )
    error_node = Node(name="error_handler", control_type="deterministic", actions=[])
    stochastic_node.edges = [Edge(target=error_node, condition="success == False")]

    flow = Flow(
        name="Stochastic Error Flow",
        description="Test stochastic error routing",
        nodes=[stochastic_node, error_node],
        context_in={"consc": "BrokenAgent"},
    )

    executor = FlowExecutor(action_types=None, context_in={"consc": BrokenAgent()})
    context = await executor.execute(flow)

    assert context["success"] is False
    assert "run" in context["error_msg"]
    assert context["email_report_md"] is None
    assert context["agent_message"] == ""
