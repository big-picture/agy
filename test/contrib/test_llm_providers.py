"""Unit tests for provider call wrappers (fully mocked, no network)."""

from __future__ import annotations

import sys
import types

import pytest

from agy.config import reset_cache
from agy.contrib.llm_call import (
    anthropic_llm_call,
    clear_provider_clients,
    fake_llm_call,
    gemini_llm_call,
    langfuse_tracing_enabled,
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
                ],
                usage=None,
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


def _mock_azure_openai(calls: dict[str, object]):
    """Build a fake AzureOpenAI class that records constructor kwargs."""

    class _Completions:
        """Completions API mock."""

        @staticmethod
        def create(*, messages, model, **params):
            """Record chat.completions.create args and return fixed text."""
            calls["messages"] = messages
            calls["model"] = model
            calls["params"] = params
            return types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        message=types.SimpleNamespace(content="Hello Azure")
                    )
                ],
                usage=None,
            )

    class _AzureOpenAI:
        """AzureOpenAI constructor mock (api-key or token provider)."""

        def __init__(self, **kwargs):
            """Record AzureOpenAI kwargs used by the provider."""
            calls.update(kwargs)
            self.chat = types.SimpleNamespace(completions=_Completions())

    return _AzureOpenAI


def test_azure_provider_uses_mocked_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Azure provider uses api-key + endpoint from default env names."""
    calls: dict[str, object] = {}
    clear_provider_clients()
    reset_cache()

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setitem(
        sys.modules,
        "openai",
        types.SimpleNamespace(AzureOpenAI=_mock_azure_openai(calls)),
    )

    result = openai_azure_llm_call(TEST_PROMPT, model="gpt-4o")
    assert result == "Hello Azure"
    assert calls["api_key"] == "azure-key"
    assert calls["azure_endpoint"] == "https://example.openai.azure.com"


def test_azure_provider_honors_provider_env_names(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Azure provider reads api_key_env / endpoint_env from tool.agy.providers."""
    calls: dict[str, object] = {}
    clear_provider_clients()
    reset_cache()

    (tmp_path / "pyproject.toml").write_text(
        """
[tool.agy.llm]
default_provider = "openai_azure"

[tool.agy.providers.openai_azure]
api_key_env = "AZURE_AI_SERVICES_KEY"
endpoint_env = "AZURE_AI_SERVICES_OPENAI_ENDPOINT"
api_version = "2024-12-01-preview"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_AI_SERVICES_KEY", "foundry-key")
    monkeypatch.setenv(
        "AZURE_AI_SERVICES_OPENAI_ENDPOINT", "https://foundry.example.openai.azure.com"
    )
    monkeypatch.setitem(
        sys.modules,
        "openai",
        types.SimpleNamespace(AzureOpenAI=_mock_azure_openai(calls)),
    )

    result = openai_azure_llm_call(TEST_PROMPT, model="gpt-4o")
    assert result == "Hello Azure"
    assert calls["api_key"] == "foundry-key"
    assert calls["azure_endpoint"] == "https://foundry.example.openai.azure.com"
    assert calls["api_version"] == "2024-12-01-preview"


def test_azure_provider_uses_managed_identity_without_key(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When key env empty, Azure provider uses azure_ad_token_provider."""
    calls: dict[str, object] = {}
    clear_provider_clients()
    reset_cache()

    (tmp_path / "pyproject.toml").write_text(
        """
[tool.agy.providers.openai_azure]
api_key_env = "AZURE_AI_SERVICES_KEY"
endpoint_env = "AZURE_AI_SERVICES_OPENAI_ENDPOINT"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AZURE_AI_SERVICES_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv(
        "AZURE_AI_SERVICES_OPENAI_ENDPOINT", "https://foundry.example.openai.azure.com"
    )

    token_provider = object()

    def _fake_get_bearer_token_provider(credential, scope):  # noqa: ARG001
        """Return a sentinel token provider for MI path."""
        return token_provider

    identity_mod = types.ModuleType("azure.identity")
    setattr(identity_mod, "DefaultAzureCredential", lambda *a, **k: object())
    setattr(identity_mod, "get_bearer_token_provider", _fake_get_bearer_token_provider)
    azure_mod = types.ModuleType("azure")
    setattr(azure_mod, "identity", identity_mod)
    monkeypatch.setitem(sys.modules, "azure", azure_mod)
    monkeypatch.setitem(sys.modules, "azure.identity", identity_mod)
    monkeypatch.setitem(
        sys.modules,
        "openai",
        types.SimpleNamespace(AzureOpenAI=_mock_azure_openai(calls)),
    )

    result = openai_azure_llm_call(TEST_PROMPT, model="gpt-4o")
    assert result == "Hello Azure"
    assert "api_key" not in calls
    assert calls["azure_ad_token_provider"] is token_provider
    assert calls["azure_endpoint"] == "https://foundry.example.openai.azure.com"


def test_langfuse_tracing_enabled_requires_both_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Langfuse tracing needs both secret and public keys."""
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    assert langfuse_tracing_enabled() is False
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    assert langfuse_tracing_enabled() is False
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    assert langfuse_tracing_enabled() is True


def test_azure_provider_uses_langfuse_openai_when_keys_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With LANGFUSE_* set, Azure client is built from langfuse.openai."""
    calls: dict[str, object] = {}
    clear_provider_clients()
    reset_cache()

    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")

    langfuse_openai = types.ModuleType("langfuse.openai")
    setattr(langfuse_openai, "AzureOpenAI", _mock_azure_openai(calls))
    setattr(langfuse_openai, "AsyncAzureOpenAI", _mock_azure_openai(calls))
    setattr(langfuse_openai, "OpenAI", object)
    setattr(langfuse_openai, "AsyncOpenAI", object)
    langfuse_mod = types.ModuleType("langfuse")
    setattr(langfuse_mod, "openai", langfuse_openai)
    monkeypatch.setitem(sys.modules, "langfuse", langfuse_mod)
    monkeypatch.setitem(sys.modules, "langfuse.openai", langfuse_openai)

    # Stock openai must not be used when Langfuse is enabled.
    def _boom(**_kwargs):
        raise AssertionError("stock openai.AzureOpenAI should not be constructed")

    monkeypatch.setitem(
        sys.modules, "openai", types.SimpleNamespace(AzureOpenAI=_boom)
    )

    result = openai_azure_llm_call(TEST_PROMPT, model="gpt-4o")
    assert result == "Hello Azure"
    assert calls["api_key"] == "azure-key"


def test_langfuse_enabled_without_package_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing langfuse package with keys set raises a clear install hint."""
    clear_provider_clients()
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setitem(sys.modules, "langfuse", None)
    monkeypatch.setitem(sys.modules, "langfuse.openai", None)

    import builtins

    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name.startswith("langfuse"):
            raise ImportError("No module named langfuse")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)
    with pytest.raises(ValueError, match="agy\\[langfuse\\]"):
        openai_azure_llm_call(TEST_PROMPT)


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
