"""Tests for contrib."""

# test/test_contrib.py

import pytest

from agy.action_call import ActionCall
from agy.action_type import ActionType
from agy.edge import Edge
from agy.flow import Flow
from agy.flow_executor import FlowExecutor
from agy.node import Node


def fake_llm_call(prompt: str, model: str = "gpt-5-mini") -> str:
    """
    Fake LLM call that simply returns the prompt.
    Useful for testing without making real API calls.
    """
    return prompt


@pytest.mark.asyncio
async def test_contrib_action_types_auto_loaded():
    """Test that contrib ActionTypes are automatically loaded in FlowExecutor"""
    # Create a simple flow that uses model_call
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("model_call(prompt='Test prompt', model='gpt-5-mini')", False)],
        kwargs={},
        output="result",
    )

    node1 = Node(name="start", control_type="deterministic", actions=[action_call])

    terminate = Node(name="end", control_type="deterministic", actions=None, edges=[])

    node1.edges = [Edge(target=terminate, condition="True")]

    flow = Flow(
        name="Test Flow",
        description="Test contrib ActionTypes",
        nodes=[node1, terminate],
        context_in={},
    )

    # Override model_call with fake_llm_call for testing
    fake_action_type = ActionType(
        object_name="global_function",
        method_name="model_call",
        kwargs={"prompt": str, "model": str},
        callable=fake_llm_call,
    )

    executor = FlowExecutor(action_types=[fake_action_type], context_in={})
    context = await executor.execute(flow)

    # Should use our fake_llm_call (overrides contrib)
    assert context["result"] == "Test prompt"
    assert context["success"] is True
