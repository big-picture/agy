"""Seed, Langfuse metadata, and multimodal chat helpers on openai_azure."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agy.contrib.llm_call import (
    LLMCall,
    _prepare_openai_create_kwargs,
    _stable_openai_seed,
    clear_provider_clients,
    invoke_model_call,
    openai_azure_chat_completion_result,
    openai_azure_llm_call,
)


def test_stable_openai_seed_is_deterministic() -> None:
    """Same basis always yields the same positive 32-bit seed."""
    a = _stable_openai_seed("CTT-1 hello")
    b = _stable_openai_seed("CTT-1 hello")
    assert a == b
    assert a > 0


def test_prepare_injects_seed_and_langfuse_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Langfuse keys are set, create kwargs include name, metadata, seed."""
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    kw = _prepare_openai_create_kwargs(
        model="gpt-5.4-mini",
        messages=[{"role": "user", "content": "hi"}],
        prompt_for_seed="hi there",
        name="classify",
        metadata={"iss_action": "classify"},
    )
    assert kw["seed"] == _stable_openai_seed("hi there")
    assert kw["name"] == "classify"
    assert kw["metadata"]["iss_action"] == "classify"
    assert kw["model"] == "gpt-5.4-mini"


def test_prepare_omits_langfuse_fields_without_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without Langfuse keys, name/metadata are not sent to the OpenAI client."""
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    kw = _prepare_openai_create_kwargs(
        model="gpt-5.4-mini",
        messages=[{"role": "user", "content": "hi"}],
        name="classify",
        metadata={"agy_flow": "x"},
    )
    assert "name" not in kw
    assert "metadata" not in kw
    assert "seed" in kw


def test_invoke_model_call_passes_name_when_supported() -> None:
    """invoke_model_call forwards name= for callables that accept **kwargs."""
    seen: dict[str, object] = {}

    def mc(prompt: str, **kwargs: object) -> str:
        seen["prompt"] = prompt
        seen["kwargs"] = kwargs
        return "ok"

    assert invoke_model_call(mc, "p", name="classify") == "ok"
    assert seen["prompt"] == "p"
    assert seen["kwargs"] == {"name": "classify"}


def test_invoke_model_call_falls_back_for_prompt_only() -> None:
    """Callables that only take prompt still work."""

    def mc(prompt: str) -> str:
        return prompt.upper()

    assert invoke_model_call(mc, "ab", name="classify") == "AB"


def test_openai_azure_llm_call_uses_prepared_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text azure call builds messages and passes seed into create."""
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    clear_provider_clients()

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="yes"))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
    )
    with patch(
        "agy.contrib.llm_call._azure_sync_client", return_value=mock_client
    ):
        out = openai_azure_llm_call("hello world", model="gpt-5.4-mini")
    assert out == "yes"
    create_kw = mock_client.chat.completions.create.call_args.kwargs
    assert create_kw["messages"] == [{"role": "user", "content": "hello world"}]
    assert create_kw["seed"] == _stable_openai_seed("hello world")


def test_openai_azure_chat_completion_multimodal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multimodal messages path returns text + usage via ChatCompletionResult."""
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    clear_provider_clients()

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "see image"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,abc"},
                },
            ],
        },
    ]
    with patch(
        "agy.contrib.llm_call._azure_sync_client", return_value=mock_client
    ):
        result = openai_azure_chat_completion_result(
            messages,
            model="gpt-5.4-mini",
            name="pod_vision",
            response_format={"type": "json_object"},
        )
    assert result.text == '{"ok":true}'
    assert result.usage["total_tokens"] == 15
    create_kw = mock_client.chat.completions.create.call_args.kwargs
    assert create_kw["name"] == "pod_vision"
    assert create_kw["response_format"] == {"type": "json_object"}
    assert create_kw["messages"] == messages


def test_llm_call_chat_completion_routes_openai_azure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMCall.chat_completion uses openai_azure when that provider is configured."""
    clear_provider_clients()
    LLMCall._initialized = False
    LLMCall._instance = None
    llm = LLMCall()
    llm.set_model_call(provider="openai_azure", model="gpt-5.4-mini")
    with patch(
        "agy.contrib.llm_call.openai_azure_chat_completion_result",
        return_value=MagicMock(text="z", usage={}),
    ) as mocked:
        assert llm.chat_completion([{"role": "user", "content": "q"}]) == "z"
        mocked.assert_called_once()
