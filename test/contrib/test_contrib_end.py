"""Tests for end() action"""

import pytest

from agy import (
    ActionCall,
    ActionExecutor,
    ActionRegistry,
    ActionType,
    Flow,
    FlowExecutor,
)
from agy.contrib.action_type_functions import FlowTerminationError, end
from agy.node import Node


@pytest.mark.asyncio
async def test_end_action_terminates_flow():
    """Test that end() action terminates the flow"""
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("end(success=True, error_msg='')", False)],
        kwargs={},
        output="result",
    )

    node1 = Node(name="test_node", control_type="deterministic", actions=[action_call])
    # No edges needed - end() will terminate

    flow = Flow(
        name="End Action Test",
        description="Test end() action",
        nodes=[node1],
        context_in={},
    )

    executor = FlowExecutor(context_in={})
    context = await executor.execute(flow)

    # Flow should have terminated
    assert context["success"] is True
    assert context["error_msg"] == ""


@pytest.mark.asyncio
async def test_end_action_sets_context_values():
    """Test that end() action can set multiple context values"""
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[
            (
                "end(success=False, error_msg='Loading the file failed', category='error')",
                False,
            )
        ],
        kwargs={},
        output="result",
    )

    node1 = Node(name="test_node", control_type="deterministic", actions=[action_call])

    flow = Flow(
        name="End Action Context Test",
        description="Test end() action with context values",
        nodes=[node1],
        context_in={},
    )

    executor = FlowExecutor(context_in={})
    context = await executor.execute(flow)

    # Context should be updated by end() action
    assert context["success"] is False
    assert context["error_msg"] == "Loading the file failed"
    assert context["category"] == "error"


@pytest.mark.asyncio
async def test_end_action_raises_exception():
    """Test that end() action raises FlowTerminationError via ActionExecutor"""
    registry = ActionRegistry()
    action_type = ActionType(
        object_name="global_function", method_name="end", kwargs={}, callable=end
    )
    registry.register(action_type)

    action_executor = ActionExecutor(registry)

    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("end(success=True)", False)],
        kwargs={},
        output="result",
    )

    context = {"success": False, "error_msg": ""}

    # end() returns dict with flow_control="TERMINATE", ActionExecutor raises FlowTerminationError
    with pytest.raises(FlowTerminationError) as exc_info:
        await action_executor.execute(action_call, context)

    # Context should be updated before exception is raised
    assert context["success"] is True
    assert exc_info.value.context_updates == {"success": True}


@pytest.mark.asyncio
async def test_end_action_with_variable_kwargs():
    """Test that end() action accepts any kwargs (not just success/error_msg)"""
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[
            (
                "end(success=True, category='processed', result='Done', custom_key='custom_value')",
                False,
            )
        ],
        kwargs={},
        output="result",
    )

    node1 = Node(name="test_node", control_type="deterministic", actions=[action_call])

    flow = Flow(
        name="End Action Variable Kwargs Test",
        description="Test end() action with variable kwargs",
        nodes=[node1],
        context_in={},
    )

    executor = FlowExecutor(context_in={})
    context = await executor.execute(flow)

    # All kwargs should be set in context
    assert context["success"] is True
    assert context["category"] == "processed"
    assert context["result"] == "Done"
    assert context["custom_key"] == "custom_value"


@pytest.mark.asyncio
async def test_end_action_from_flowsy():
    """Test that end() action works from FLOWSY flow"""
    flowsy_content = """
name: End Action FLOWSY Test
description: Test end() action from FLOWSY

nodes:
  test_node:
    actions:
      - end(success=False, error_msg="Loading the file failed", category="error")
"""

    flow = Flow.from_flowsy_string(flowsy_content)
    executor = FlowExecutor(context_in={})
    context = await executor.execute(flow)

    # Context should be updated by end() action
    assert context["success"] is False
    assert context["error_msg"] == "Loading the file failed"
    assert context["category"] == "error"


@pytest.mark.asyncio
async def test_end_in_edge_from_flowsy():
    """Test that end(...) works in edges from FLOWSY"""
    flowsy_content = """
name: End In Edge Test
description: Test end(...) in edge from FLOWSY

nodes:
  test_node:
    actions:
      - show("Processing...")
    edges:
      - x > 5: end(success=True, category="done")
      - True: end(success=False, error_msg="Failed")
"""

    flow = Flow.from_flowsy_string(flowsy_content)
    executor = FlowExecutor(context_in={})

    # Test execution - x is not set, so first condition fails, second matches
    context = await executor.execute(flow)
    # Flow should have terminated via end() in edge
    assert context["success"] is False
    assert context["error_msg"] == "Failed"
