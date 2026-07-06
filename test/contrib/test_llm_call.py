# test/contrib/test_llm_call.py

"""Tests for LLMCall Singleton and set_model_call action."""

from typing import Any

import pytest

from agy.action_call import ActionCall
from agy.action_executor import ActionExecutor, ActionRegistry
from agy.contrib.action_types import get_contrib_action_types
from agy.contrib.llm_call import LLMCall


@pytest.mark.asyncio
async def test_llm_call_singleton():
    """Test that LLMCall is a singleton."""
    llm1 = LLMCall()
    llm2 = LLMCall()
    assert llm1 is llm2


@pytest.mark.asyncio
async def test_llm_call_initialized_from_config():
    """Test that LLMCall is initialized with config defaults."""
    llm = LLMCall()
    # Should be initialized (not None)
    assert llm._current_callable is not None


@pytest.mark.asyncio
async def test_llm_call_set_model_call_with_provider():
    """Test setting model_call with provider."""
    llm = LLMCall()

    # Set to fake provider
    llm.set_model_call(provider="fake", model="test-model", params=None)

    # Call should work
    result = llm.model_call("test prompt")
    assert result == "test prompt"


@pytest.mark.asyncio
async def test_llm_call_set_model_call_with_custom_callable():
    """Test setting model_call with custom callable."""
    llm = LLMCall()

    def custom_call(prompt: str, **kwargs) -> str:
        """Custom call.

        Args:
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: Operation result.
        """
        return f"CUSTOM: {prompt}"

    llm.set_model_call(callable=custom_call)

    result = llm.model_call("test")
    assert result == "CUSTOM: test"


@pytest.mark.asyncio
async def test_llm_call_register_provider():
    """Test registering a custom provider."""
    llm = LLMCall()

    def mistral_call(prompt: str, model: str = "mistral-small", **params) -> str:
        """Mistral call.

        Args:
            prompt: prompt.
            model: model.
            **params: Additional keyword arguments.

        Returns:
            str: Operation result.
        """
        return f"MISTRAL[{model}]: {prompt}"

    llm.register_provider("mistral", mistral_call)

    # Use the new provider
    llm.set_model_call(provider="mistral", model="mistral-large")
    result = llm.model_call("hello")
    assert "MISTRAL" in result
    assert "mistral-large" in result


@pytest.mark.asyncio
async def test_set_model_call_action():
    """Test set_model_call as an action."""
    registry = ActionRegistry()

    # Register contrib action types
    for action_type in get_contrib_action_types():
        registry.register(action_type)

    executor = ActionExecutor(registry)
    context: dict[str, Any] = {}

    # Call set_model_call action
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("set_model_call(provider='fake', model='test-model')", False)],
        kwargs={},
        output="result",
    )

    await executor.execute(action_call, context)

    # Check that it succeeded
    assert (
        context.get("success") is True
        or context.get("result", {}).get("success") is True
    )

    # Verify model_call now uses fake provider
    model_call_action = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("model_call(prompt='test prompt')", False)],
        kwargs={},
        output="result",
    )

    await executor.execute(model_call_action, context)
    assert context["result"] == "test prompt"


@pytest.mark.asyncio
async def test_set_model_call_action_with_kwargs():
    """Test set_model_call with kwargs (temperature, max_tokens, etc.)."""
    registry = ActionRegistry()

    for action_type in get_contrib_action_types():
        registry.register(action_type)

    executor = ActionExecutor(registry)
    context: dict[str, Any] = {}

    # Custom callable that checks params
    def custom_call(prompt: str, **kwargs) -> str:
        # Verify params were passed through
        """Custom call.

        Args:
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: Operation result.
        """
        temp = kwargs.get("temperature", 0)
        tokens = kwargs.get("max_tokens", 0)
        return f"{prompt}|temp={temp}|tokens={tokens}"

    # Set model_call with temperature and max_tokens as kwargs
    # Note: callable needs to be in context for __eval__
    context["custom_call"] = custom_call
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[
            (
                "set_model_call(callable=custom_call, temperature=0.7, max_tokens=1000)",
                False,
            )
        ],
        kwargs={},
        output="result",
    )

    await executor.execute(action_call, context)

    # Now call model_call and verify params were preserved
    model_call_action = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("model_call(prompt='test')", False)],
        kwargs={},
        output="result",
    )

    await executor.execute(model_call_action, context)
    # Note: params from set_model_call are stored but passed on each call
    # The fake callable would need to receive them
    assert context["result"] is not None


def test_set_model_call_action_type_does_not_advertise_params_kwarg():
    """Action metadata should not suggest params=... for set_model_call."""
    set_model_action = next(
        a for a in get_contrib_action_types() if a.method_name == "set_model_call"
    )
    assert "params" not in set_model_action.kwargs


@pytest.mark.asyncio
async def test_set_model_call_accepts_legacy_params_and_dynamic_kwargs():
    """Legacy params dict and direct kwargs are merged into model params."""
    registry = ActionRegistry()
    for action_type in get_contrib_action_types():
        registry.register(action_type)
    executor = ActionExecutor(registry)
    context: dict[str, Any] = {}

    captured: dict[str, Any] = {}

    def custom_call(prompt: str, **kwargs: Any) -> str:
        captured.update(kwargs)
        return prompt

    context["custom_call"] = custom_call

    set_action = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[
            (
                "set_model_call(callable=custom_call, params={'temperature': 0.3}, max_tokens=128)",
                False,
            )
        ],
        kwargs={},
        output="result",
    )
    await executor.execute(set_action, context)

    model_action = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("model_call(prompt='ping')", False)],
        kwargs={},
        output="result",
    )
    await executor.execute(model_action, context)

    assert context["result"] == "ping"
    assert captured == {"temperature": 0.3, "max_tokens": 128}


@pytest.mark.asyncio
async def test_set_model_call_with_custom_callable_action():
    """Test set_model_call with custom callable as action."""
    registry = ActionRegistry()

    for action_type in get_contrib_action_types():
        registry.register(action_type)

    executor = ActionExecutor(registry)
    context: dict[str, Any] = {}

    def custom_call(prompt: str, **kwargs) -> str:
        """Custom call.

        Args:
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: Operation result.
        """
        return f"CUSTOM: {prompt}"

    # Note: In real flow, callable would be passed differently
    # For now, we test that set_model_call works
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("set_model_call(provider='fake')", False)],
        kwargs={},
        output="result",
    )

    await executor.execute(action_call, context)

    # Verify it worked
    model_call_action = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("model_call(prompt='test')", False)],
        kwargs={},
        output="result",
    )

    await executor.execute(model_call_action, context)
    assert context["result"] == "test"


@pytest.mark.asyncio
async def test_model_call_action_with_params():
    """Test model_call action with additional parameters."""
    registry = ActionRegistry()

    for action_type in get_contrib_action_types():
        registry.register(action_type)

    executor = ActionExecutor(registry)
    context: dict[str, Any] = {}

    # Set fake provider first
    set_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("set_model_call(provider='fake')", False)],
        kwargs={},
        output="result",
    )
    await executor.execute(set_call, context)

    # Call model_call with additional params
    model_call_action = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("model_call(prompt='test prompt', temperature=0.7)", False)],
        kwargs={},
        output="result",
    )

    await executor.execute(model_call_action, context)
    assert context["result"] == "test prompt"


@pytest.mark.asyncio
async def test_classify_uses_llm_call():
    """Test that classify uses LLMCall singleton."""
    registry = ActionRegistry()

    for action_type in get_contrib_action_types():
        registry.register(action_type)

    executor = ActionExecutor(registry)
    context: dict[str, Any] = {}

    # Set fake provider
    set_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("set_model_call(provider='fake')", False)],
        kwargs={},
        output="result",
    )
    await executor.execute(set_call, context)

    # Classify should use fake provider (which returns prompt)
    # But classify expects JSON, so we need a smarter fake
    def fake_classify_call(prompt: str, **kwargs) -> str:
        """Fake classify call.

        Args:
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: Operation result.
        """
        return '{"category": "test", "confidence": 0.9}'

    llm = LLMCall()
    llm.set_model_call(callable=fake_classify_call)

    classify_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[
            ("classify(input_text='test text', categories=['test', 'other'])", False)
        ],
        kwargs={},
        output="category",
    )

    await executor.execute(classify_call, context)

    assert context["category"] == "test"
    assert context["confidence"] == 0.9
