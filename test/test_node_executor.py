"""Tests for node executor."""

# test/test_node_executor.py

import pytest

from agy.action_call import ActionCall
from agy.action_executor import ActionExecutor, ActionRegistry
from agy.action_type import ActionType
from agy.edge import Edge
from agy.flow import Flow
from agy.node import Node
from agy.node_executor import DeterministicNodeExecutor


@pytest.mark.asyncio
async def test_deterministic_node_executor_edge_evaluation():
    """Test that DeterministicNodeExecutor evaluates edges correctly"""
    # Create simple flow for testing
    node1 = Node(name="node1", control_type="deterministic", actions=[])
    node2 = Node(name="node2", control_type="deterministic", actions=[])

    # Node1: condition-based edge
    node1.edges = [
        Edge(target=node2, condition="x > 5"),
        Edge(target="end", condition="True"),  # Default - end as string keyword
    ]

    flow = Flow(
        name="Edge Test",
        description="Test edge evaluation",
        nodes=[node1, node2],
        context_in={},
    )

    registry = ActionRegistry()
    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    # Test with condition matching
    context1 = flow.context.copy()
    context1["x"] = 10
    result1 = await node_executor.execute(node1, context1)
    assert result1.next_node is not None
    assert result1.next_node.name == "node2"
    assert result1.terminated is False

    # Test with condition not matching (should use default edge to terminate)
    context2 = flow.context.copy()
    context2["x"] = 3
    result2 = await node_executor.execute(node1, context2)
    assert result2.terminated is True
    assert result2.next_node is None  # Termination via end keyword


@pytest.mark.asyncio
async def test_deterministic_node_executor_termination():
    """Test that termination nodes are detected correctly"""
    node1 = Node(name="node1", control_type="deterministic", actions=[])

    node1.edges = [Edge(target="end", condition="True")]  # end as string keyword

    flow = Flow(
        name="Termination Test",
        description="Test termination",
        nodes=[node1],
        context_in={},
    )

    registry = ActionRegistry()
    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    context = flow.context.copy()
    result = await node_executor.execute(node1, context)

    assert result.terminated is True
    assert result.next_node is None


@pytest.mark.asyncio
async def test_deterministic_node_executor_action_execution():
    """Test that DeterministicNodeExecutor executes actions in sequence"""

    # Create a simple add function
    def add(a: int, b: int) -> int:
        """Add.

        Args:
            a: a.
            b: b.

        Returns:
            int: Operation result.
        """
        return a + b

    # Create action type and action call
    action_type = ActionType(
        object_name="global_function", method_name="add", callable=add
    )

    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("add(a, b)", False)],
        kwargs={},
        output="result",
    )

    # Register action type
    registry = ActionRegistry()
    registry.register(action_type)
    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    # Create node with action call
    node1 = Node(name="node1", control_type="deterministic", actions=[action_call])
    # No edges = automatic termination
    node1.edges = []

    flow = Flow(
        name="Action Execution Test",
        description="Test action execution",
        nodes=[node1],
        context_in={},
    )

    context = flow.context.copy()
    context["a"] = 5
    context["b"] = 3

    result = await node_executor.execute(node1, context)

    assert context["result"] == 8
    assert context["success"] is True
    assert result.terminated is True


@pytest.mark.asyncio
async def test_deterministic_node_executor_multiple_actions():
    """Test executing multiple actions in a node"""

    def multiply(x: int, y: int) -> int:
        """Multiply.

        Args:
            x: x.
            y: y.

        Returns:
            int: Operation result.
        """
        return x * y

    def add(x: int, y: int) -> int:
        """Add.

        Args:
            x: x.
            y: y.

        Returns:
            int: Operation result.
        """
        return x + y

    action_type1 = ActionType(
        object_name="global_function", method_name="multiply", callable=multiply
    )

    action_type2 = ActionType(
        object_name="global_function", method_name="add", callable=add
    )

    action_call1 = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("multiply(x, y)", False)],
        kwargs={},
        output="product",
    )

    # After first action, product=6 will be in context
    action_call2 = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("add(product, z)", False)],
        kwargs={},
        output="result",
    )

    registry = ActionRegistry()
    registry.register(action_type1)
    registry.register(action_type2)
    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    node1 = Node(
        name="node1", control_type="deterministic", actions=[action_call1, action_call2]
    )
    # No edges = automatic termination
    node1.edges = []

    flow = Flow(
        name="Multiple Actions Test",
        description="Test multiple actions",
        nodes=[node1],
        context_in={},
    )

    context = flow.context.copy()
    context["x"] = 2
    context["y"] = 3
    context["z"] = 1

    result = await node_executor.execute(node1, context)

    assert context["product"] == 6
    # After first action: product=6
    # Second action: add(product=6, z=1) = add(6, 1) = 7
    assert context["result"] == 7
    assert context["success"] is True
    assert result.terminated is True


@pytest.mark.asyncio
async def test_deterministic_node_executor_edge_conditions_order():
    """Test that edges are evaluated in order, first matching edge wins"""
    node1 = Node(name="node1", control_type="deterministic", actions=[])
    node2 = Node(name="node2", control_type="deterministic", actions=[])
    node3 = Node(name="node3", control_type="deterministic", actions=[])

    # Edge order: condition, condition, condition-less
    node1.edges = [
        Edge(target=node2, condition="x > 10"),
        Edge(target=node3, condition="x > 5"),
        Edge(target="end", condition="True"),  # Default - end as string keyword
    ]

    flow = Flow(
        name="Edge Order Test",
        description="Test edge evaluation order",
        nodes=[node1, node2, node3],
        context_in={},
    )

    registry = ActionRegistry()
    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    # x=15: First condition matches (x > 10), should go to node2
    context1 = flow.context.copy()
    context1["x"] = 15
    result1 = await node_executor.execute(node1, context1)
    assert result1.next_node is not None
    assert result1.next_node.name == "node2"

    # x=7: Second condition matches (x > 5), should go to node3
    context2 = flow.context.copy()
    context2["x"] = 7
    result2 = await node_executor.execute(node1, context2)
    assert result2.next_node is not None
    assert result2.next_node.name == "node3"

    # x=3: No condition matches, should use default edge to terminate
    context3 = flow.context.copy()
    context3["x"] = 3
    result3 = await node_executor.execute(node1, context3)
    assert result3.terminated is True


@pytest.mark.asyncio
async def test_deterministic_node_executor_no_edges_terminates():
    """Test that nodes without edges terminate automatically"""

    def add(a: int, b: int) -> int:
        """Add.

        Args:
            a: a.
            b: b.

        Returns:
            int: Operation result.
        """
        return a + b

    action_type = ActionType(
        object_name="global_function", method_name="add", callable=add
    )

    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("add(5, 3)", False)],
        kwargs={},
        output="result",
    )

    registry = ActionRegistry()
    registry.register(action_type)
    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    node1 = Node(name="node1", control_type="deterministic", actions=[action_call])
    # No edges - should terminate automatically

    flow = Flow(
        name="No Edges Test",
        description="Test node without edges",
        nodes=[node1],
        context_in={},
    )

    context = flow.context.copy()
    result = await node_executor.execute(node1, context)

    # Should terminate automatically
    assert result.terminated is True
    assert result.next_node is None
    # Actions should have executed
    assert context["result"] == 8


@pytest.mark.asyncio
async def test_deterministic_node_executor_end_keyword_in_edge():
    """Test that 'end' as string keyword in edge terminates flow"""
    node1 = Node(name="node1", control_type="deterministic", actions=[])
    node2 = Node(name="node2", control_type="deterministic", actions=[])

    # Edge with "end" keyword
    node1.edges = [
        Edge(target=node2, condition="x > 5"),
        Edge(target="end", condition="True"),  # end as string keyword
    ]

    flow = Flow(
        name="End Keyword Test",
        description="Test end keyword in edge",
        nodes=[node1, node2],
        context_in={},
    )

    registry = ActionRegistry()
    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    # Test with condition not matching - should go to end
    context = flow.context.copy()
    context["x"] = 3
    result = await node_executor.execute(node1, context)

    # Should terminate via end keyword
    assert result.terminated is True
    assert result.next_node is None

    # Test with condition matching - should go to node2
    context2 = flow.context.copy()
    context2["x"] = 10
    result2 = await node_executor.execute(node1, context2)

    # Should go to node2
    assert result2.terminated is False
    assert result2.next_node is not None
    assert result2.next_node.name == "node2"


@pytest.mark.asyncio
async def test_deterministic_node_executor_end_with_args_in_edge():
    """Test that end(...) in edge executes end() action and terminates"""
    # Import end action
    from agy.action_type import ActionType
    from agy.contrib.action_type_functions import end

    node1 = Node(name="node1", control_type="deterministic", actions=[])

    # Edge with end(...) that sets context values
    node1.edges = [
        Edge(target='end(success=False, error_msg="test error")', condition="x < 5"),
        Edge(target='end(success=True, category="processed")', condition="True"),
    ]

    flow = Flow(
        name="End With Args Test",
        description="Test end(...) in edge",
        nodes=[node1],
        context_in={},
    )

    registry = ActionRegistry()
    # Register end() action
    end_action_type = ActionType(
        object_name="global_function", method_name="end", kwargs={}, callable=end
    )
    registry.register(end_action_type)

    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    # Test with condition matching first edge
    context = flow.context.copy()
    context["x"] = 3
    result = await node_executor.execute(node1, context)

    # Should terminate and context should be updated
    assert result.terminated is True
    assert result.next_node is None
    assert context["success"] is False
    assert context["error_msg"] == "test error"

    # Test with condition matching second edge
    context2 = flow.context.copy()
    context2["x"] = 10
    result2 = await node_executor.execute(node1, context2)

    # Should terminate and context should be updated
    assert result2.terminated is True
    assert context2["success"] is True
    assert context2["category"] == "processed"


@pytest.mark.asyncio
async def test_deterministic_node_executor_end_with_quoted_params():
    """Test that end(...) works with standard parameter names (no quotes)"""
    from agy.action_type import ActionType
    from agy.contrib.action_type_functions import end

    node1 = Node(name="node1", control_type="deterministic", actions=[])

    # Edge with end(...) using standard parameter names (no quotes around param names)
    node1.edges = [Edge(target='end(success=True, error_msg="test")', condition="True")]

    flow = Flow(
        name="End With Quoted Params Test",
        description="Test end(...) with quoted params",
        nodes=[node1],
        context_in={},
    )

    registry = ActionRegistry()
    end_action_type = ActionType(
        object_name="global_function", method_name="end", kwargs={}, callable=end
    )
    registry.register(end_action_type)

    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    context = flow.context.copy()
    result = await node_executor.execute(node1, context)

    # Should terminate and context should be updated
    assert result.terminated is True
    assert context["success"] is True
    assert context["error_msg"] == "test"


@pytest.mark.asyncio
async def test_deterministic_node_executor_stops_on_action_failure():
    """Test that node execution stops when an action fails and goes to edges"""

    def success_action() -> str:
        """Success action.

        Returns:
            str: Operation result.
        """
        return "success"

    def failing_action() -> str:
        """Failing action.

        Returns:
            str: Operation result.
        """
        raise ValueError("Action failed")

    action_type1 = ActionType(
        object_name="global_function",
        method_name="success_action",
        callable=success_action,
    )

    action_type2 = ActionType(
        object_name="global_function",
        method_name="failing_action",
        callable=failing_action,
    )

    action_call1 = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("success_action()", False)],
        kwargs={},
        output="result1",
    )

    action_call2 = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("failing_action()", False)],
        kwargs={},
        output="result2",
    )

    action_call3 = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("success_action()", False)],
        kwargs={},
        output="result3",
    )

    registry = ActionRegistry()
    registry.register(action_type1)
    registry.register(action_type2)
    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    node1 = Node(
        name="node1",
        control_type="deterministic",
        actions=[action_call1, action_call2, action_call3],
    )
    # No edges - should terminate implicitly with success=False

    flow = Flow(
        name="Action Failure Test",
        description="Test stopping on action failure",
        nodes=[node1],
        context_in={},
    )

    context = flow.context.copy()
    result = await node_executor.execute(node1, context)

    # Should have stopped after action_call2 failed
    assert context["success"] is False
    assert "Action failed" in context["error_msg"]
    assert "result1" in context  # First action succeeded
    assert "result2" not in context  # Second action failed, no output
    assert "result3" not in context  # Third action was not executed

    # Should terminate (no edges, implicit end)
    assert result.terminated is True
    assert result.next_node is None


@pytest.mark.asyncio
async def test_deterministic_node_executor_action_failure_with_edges():
    """Test that node execution stops on failure and evaluates edges"""

    def failing_action() -> str:
        """Failing action.

        Returns:
            str: Operation result.
        """
        raise ValueError("Action failed")

    action_type = ActionType(
        object_name="global_function",
        method_name="failing_action",
        callable=failing_action,
    )

    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("failing_action()", False)],
        kwargs={},
        output="result",
    )

    registry = ActionRegistry()
    registry.register(action_type)
    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    error_handler = Node(name="error_handler", control_type="deterministic", actions=[])
    next_node = Node(name="next_node", control_type="deterministic", actions=[])

    node1 = Node(name="node1", control_type="deterministic", actions=[action_call])
    # Edge that handles errors
    node1.edges = [
        Edge(target=error_handler, condition="success == False"),
        Edge(target=next_node, condition="True"),
    ]

    flow = Flow(
        name="Action Failure With Edges Test",
        description="Test action failure with error handling edges",
        nodes=[node1, error_handler, next_node],
        context_in={},
    )

    context = flow.context.copy()
    result = await node_executor.execute(node1, context)

    # Should have failed
    assert context["success"] is False
    assert "Action failed" in context["error_msg"]

    # Should route to error_handler (first matching edge)
    assert result.terminated is False
    assert result.next_node is not None
    assert result.next_node.name == "error_handler"


@pytest.mark.asyncio
async def test_deterministic_node_executor_dynamic_object_registration():
    """Test that objects in context are called directly (no registration needed)"""

    class Calculator:
        """Represents a Calculator object."""

        def multiply(self, a: int, b: int) -> int:
            """Multiply.

            Args:
                a: a.
                b: b.

            Returns:
                int: Operation result.
            """
            return a * b

    calc = Calculator()

    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("calc.multiply(a, b)", False)],
        kwargs={},
        output="result",
    )

    registry = ActionRegistry()
    action_executor = ActionExecutor(registry)
    node_executor = DeterministicNodeExecutor(action_executor)

    node1 = Node(name="node1", control_type="deterministic", actions=[action_call])
    # No edges = automatic termination
    node1.edges = []

    flow = Flow(
        name="Dynamic Registration Test",
        description="Test dynamic object registration",
        nodes=[node1],
        context_in={"calc": "Calculator"},
    )

    context = flow.context.copy()
    context["calc"] = calc
    context["a"] = 4
    context["b"] = 5

    await node_executor.execute(node1, context)

    assert context["result"] == 20
    assert context["success"] is True
    # Objects are called directly, not registered
