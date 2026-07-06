"""Tests for contrib model call."""

# test/contrib/test_contrib_model_call.py

from typing import Any

import pytest

from agy.action_call import ActionCall
from agy.action_executor import ActionExecutor, ActionRegistry
from agy.contrib.action_types import get_contrib_action_types
from agy.contrib.llm_call import LLMCall
from agy.edge import Edge
from agy.flow import Flow
from agy.flow_executor import FlowExecutor
from agy.node import Node


@pytest.mark.asyncio
async def test_model_call_action_type():
    """Test model_call action with contrib action types."""
    registry = ActionRegistry()

    # Register contrib action types (includes model_call)
    for action_type in get_contrib_action_types():
        registry.register(action_type)

    # Set fake provider
    llm = LLMCall()
    llm.set_model_call(provider="fake")

    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("model_call(prompt='Hello, world!')", False)],
        kwargs={},
        output="result",
    )
    await executor.execute(action_call, context)

    assert context["result"] == "Hello, world!"
    assert context["success"] is True


@pytest.mark.asyncio
async def test_model_call_with_default_model():
    """Test model_call with default from config."""
    registry = ActionRegistry()

    for action_type in get_contrib_action_types():
        registry.register(action_type)

    # Set fake provider
    llm = LLMCall()
    llm.set_model_call(provider="fake")

    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("model_call(prompt='Test prompt')", False)],
        kwargs={},
        output="result",
    )

    await executor.execute(action_call, context)
    assert context["success"] is True
    assert context["result"] == "Test prompt"


@pytest.mark.asyncio
async def test_contrib_action_types_auto_loaded():
    """Test that contrib action types work in a flow."""
    # Set fake provider
    llm = LLMCall()
    llm.set_model_call(provider="fake")

    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("model_call(prompt='Test prompt')", False)],
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

    # Use contrib action types
    executor = FlowExecutor(action_types=get_contrib_action_types(), context_in={})
    context = await executor.execute(flow)

    assert context["result"] == "Test prompt"
    assert context["success"] is True


@pytest.mark.asyncio
async def test_model_call_output_json_dict():
    """Test model_call with output='json' returns parsed dict."""
    from agy.contrib.action_type_functions import model_call

    llm = LLMCall()
    # Mock that returns JSON string
    llm.set_model_call(callable=lambda prompt, **kwargs: '{"name": "Max", "age": 30}')

    result = model_call(prompt="Extract data", output="json")

    assert isinstance(result, dict)
    assert result == {"name": "Max", "age": 30}


@pytest.mark.asyncio
async def test_model_call_output_json_list():
    """Test model_call with output='json' returns parsed list."""
    from agy.contrib.action_type_functions import model_call

    llm = LLMCall()
    # Mock that returns JSON array
    llm.set_model_call(callable=lambda prompt, **kwargs: '["item1", "item2", "item3"]')

    result = model_call(prompt="List items", output="json")

    assert isinstance(result, list)
    assert result == ["item1", "item2", "item3"]


@pytest.mark.asyncio
async def test_model_call_output_json_strips_markdown():
    """Test model_call with output='json' strips markdown code blocks."""
    from agy.contrib.action_type_functions import model_call

    llm = LLMCall()
    # Mock that returns JSON wrapped in markdown
    llm.set_model_call(
        callable=lambda prompt, **kwargs: '```json\n{"key": "value"}\n```'
    )

    result = model_call(prompt="Get data", output="json")

    assert isinstance(result, dict)
    assert result == {"key": "value"}


@pytest.mark.asyncio
async def test_model_call_output_str_default():
    """Test model_call with default output='str' returns raw string."""
    from agy.contrib.action_type_functions import model_call

    llm = LLMCall()
    llm.set_model_call(callable=lambda prompt, **kwargs: '{"raw": "string"}')

    result = model_call(prompt="Get data")

    assert isinstance(result, str)
    assert result == '{"raw": "string"}'


@pytest.mark.asyncio
async def test_model_call_output_json_invalid_raises():
    """Test model_call with output='json' raises on invalid JSON."""
    import json

    from agy.contrib.action_type_functions import model_call

    llm = LLMCall()
    llm.set_model_call(callable=lambda prompt, **kwargs: "not valid json")

    with pytest.raises(json.JSONDecodeError):
        model_call(prompt="Get data", output="json")
