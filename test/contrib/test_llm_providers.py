"""Unit tests for provider call wrappers (fully mocked, no network)."""

from __future__ import annotations

import sys
import types

import pytest

from agy.contrib.llm_call import (
    anthropic_llm_call,
    fake_llm_call,
    gemini_llm_call,
    openai_azure_llm_call,
    openai_llm_call,
)

TEST_PROMPT = "Reply with exactly one word: Hello"


def test_fake_provider() -> None:
    """Fake provider returns prompt unchanged."""
    result = fake_llm_call(TEST_PROMPT)
    assert result == TEST_PROMPT


def test_openai_provider_uses_mocked_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI wrapper can be tested with mocked SDK client."""
    calls: dict[str, object] = {}

    class _Completions:
        """Represents completions API mock behavior."""

        @staticmethod
        def create(*, model, messages, **params):
            """Create.

            Args:
                model: model.
                messages: messages.
                **params: Additional keyword arguments.
            """
            calls["model"] = model
            calls["messages"] = messages
            calls["params"] = params
            return types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        message=types.SimpleNamespace(content="Hello")
                    )
                ]
            )

    class _OpenAI:
        """Represents a OpenAI object."""

        def __init__(self, api_key):
            """Initialize the object.

            Args:
                api_key: api key.
            """
            calls["api_key"] = api_key
            self.chat = types.SimpleNamespace(completions=_Completions())

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_OpenAI))

    result = openai_llm_call(TEST_PROMPT, model="gpt-4o-mini", temperature=0.2)
    assert result == "Hello"
    assert calls["api_key"] == "test-key"
    assert calls["model"] == "gpt-4o-mini"


def test_openai_provider_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that openai provider missing key raises.

    Args:
        monkeypatch: monkeypatch.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        openai_llm_call(TEST_PROMPT)


def test_azure_provider_uses_mocked_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that azure provider uses mocked sdk.

    Args:
        monkeypatch: monkeypatch.
    """
    calls: dict[str, object] = {}

    class _Completions:
        """Represents completions API mock behavior."""

        @staticmethod
        def create(*, messages, model, **params):
            """Create.

            Args:
                messages: messages.
                model: model.
                **params: Additional keyword arguments.
            """
            calls["messages"] = messages
            calls["model"] = model
            calls["params"] = params
            return types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        message=types.SimpleNamespace(content="Hello Azure")
                    )
                ]
            )

    class _AzureOpenAI:
        """Represents a AzureOpenAI object."""

        def __init__(self, azure_endpoint, api_key, api_version):
            """Initialize the object.

            Args:
                azure_endpoint: azure endpoint.
                api_key: api key.
                api_version: api version.
            """
            calls["azure_endpoint"] = azure_endpoint
            calls["api_key"] = api_key
            calls["api_version"] = api_version
            self.chat = types.SimpleNamespace(completions=_Completions())

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setitem(
        sys.modules, "openai", types.SimpleNamespace(AzureOpenAI=_AzureOpenAI)
    )

    result = openai_azure_llm_call(TEST_PROMPT, model="gpt-4o")
    assert result == "Hello Azure"
    assert calls["api_key"] == "azure-key"


def test_gemini_provider_uses_mocked_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that gemini provider uses mocked sdk.

    Args:
        monkeypatch: monkeypatch.
    """

    class _GenerateContentConfig:
        """Represents a GenerateContentConfig object."""

        def __init__(self, **kwargs):
            """Initialize the object.

            Args:
                **kwargs: Additional keyword arguments.
            """
            self.kwargs = kwargs

    class _Models:
        """Represents model API mock behavior."""

        @staticmethod
        def generate_content(*, model, contents, config):
            """Generate content.

            Args:
                model: model.
                contents: contents.
                config: config.
            """
            assert model == "gemini-2.0-flash"
            assert contents == TEST_PROMPT
            assert config is not None
            return types.SimpleNamespace(text="Hello Gemini")

    class _Client:
        """Represents a Client object."""

        def __init__(self, api_key):
            """Initialize the object.

            Args:
                api_key: api key.
            """
            assert api_key == "gemini-key"
            self.models = _Models()

    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    google_module = types.ModuleType("google")
    genai_module = types.ModuleType("google.genai")
    genai_types_module = types.ModuleType("google.genai.types")
    setattr(genai_types_module, "GenerateContentConfig", _GenerateContentConfig)
    setattr(genai_module, "Client", _Client)
    setattr(genai_module, "types", genai_types_module)
    setattr(google_module, "genai", genai_module)
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.genai", genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai_types_module)

    result = gemini_llm_call(TEST_PROMPT, model="gemini-2.0-flash", temperature=0.1)
    assert result == "Hello Gemini"


def test_anthropic_provider_uses_mocked_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that anthropic provider uses mocked sdk.

    Args:
        monkeypatch: monkeypatch.
    """

    class _Messages:
        """Represents message API mock behavior."""

        @staticmethod
        def create(*, model, max_tokens, messages, **params):
            """Create.

            Args:
                model: model.
                max_tokens: max tokens.
                messages: messages.
                **params: Additional keyword arguments.
            """
            assert model == "claude-3-sonnet-20240229"
            assert max_tokens == 17
            assert messages[0]["content"] == TEST_PROMPT
            assert params["temperature"] == 0.1
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text="Hello Claude")]
            )

    class _Anthropic:
        """Represents a Anthropic object."""

        def __init__(self, api_key):
            """Initialize the object.

            Args:
                api_key: api key.
            """
            assert api_key == "anthropic-key"
            self.messages = _Messages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        types.SimpleNamespace(Anthropic=_Anthropic),
    )

    result = anthropic_llm_call(TEST_PROMPT, max_tokens=17, temperature=0.1)
    assert result == "Hello Claude"
