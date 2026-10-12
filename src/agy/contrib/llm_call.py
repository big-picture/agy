# agy/contrib/llm_call.py
"""LLM Call Singleton - Central management for all LLM provider calls."""

import asyncio
import inspect
import os
import weakref
from collections.abc import Callable
from typing import Any

from agy.config import get_provider_config, load_llm_config

_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
_AZURE_API_VERSION = "2024-02-15-preview"
_DEFAULT_AZURE_KEY_ENVS = ("AZURE_OPENAI_API_KEY", "OPENAI_API_AZURE_KEY")
_DEFAULT_AZURE_ENDPOINT_ENVS = ("AZURE_OPENAI_ENDPOINT", "OPENAI_AZURE_BASE_URL")


def _require_text(value: Any, provider: str) -> str:
    """Normalize provider response text to a guaranteed string."""
    if isinstance(value, str):
        return value
    if value is None:
        raise ValueError(f"{provider} returned empty response text")
    return str(value)


# Provider clients are cached so repeated calls reuse pooled connections instead
# of paying a fresh TLS handshake per prompt.
_sync_clients: dict[tuple[str, ...], Any] = {}
_async_clients: "weakref.WeakKeyDictionary[Any, dict[tuple[str, ...], Any]]" = (
    weakref.WeakKeyDictionary()
)


def clear_provider_clients() -> None:
    """Drop cached SDK clients (tests / credential rotation)."""
    _sync_clients.clear()
    _async_clients.clear()


def _cached_sync_client(cache_key: tuple[str, ...], factory: Callable[[], Any]) -> Any:
    client = _sync_clients.get(cache_key)
    if client is None:
        client = factory()
        _sync_clients[cache_key] = client
    return client


def _cached_async_client(cache_key: tuple[str, ...], factory: Callable[[], Any]) -> Any:
    """Cache async clients per event loop.

    Async HTTP clients bind their connection pool to the loop that opened it, so a
    single process-wide instance breaks under pytest-asyncio, which runs each test
    on a fresh loop.
    """
    loop = asyncio.get_running_loop()
    per_loop = _async_clients.get(loop)
    if per_loop is None:
        per_loop = {}
        _async_clients[loop] = per_loop
    client = per_loop.get(cache_key)
    if client is None:
        client = factory()
        per_loop[cache_key] = client
    return client


def _configured_env_name(provider: str, key: str) -> str | None:
    """Return non-empty ``api_key_env`` / ``endpoint_env`` from provider config."""
    raw = get_provider_config(provider).get(key)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _resolve_env(configured_env: str | None, *fallback_env_names: str) -> tuple[str, str]:
    """Return ``(value, env_name)`` using configured name then legacy fallbacks."""
    if configured_env:
        return (os.getenv(configured_env) or "").strip(), configured_env
    for name in fallback_env_names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value, name
    expected = fallback_env_names[0] if fallback_env_names else configured_env or ""
    return "", expected


def _provider_api_key(provider: str, default_env: str, label: str) -> str:
    """Resolve an API key from ``[tool.agy.providers.<provider>].api_key_env``."""
    configured = _configured_env_name(provider, "api_key_env")
    value, env_name = _resolve_env(configured, default_env)
    if not value:
        raise ValueError(f"Missing environment variable for {label}: {env_name}")
    return value


def _azure_api_version() -> str:
    """API version from provider config, ``OPENAI_API_VERSION``, or default."""
    cfg_version = get_provider_config("openai_azure").get("api_version")
    if isinstance(cfg_version, str) and cfg_version.strip():
        return cfg_version.strip()
    env_version = (os.getenv("OPENAI_API_VERSION") or "").strip()
    return env_version or _AZURE_API_VERSION


def _azure_auth(
    endpoint_override: str | None,
) -> tuple[str, str | None, Any | None, str]:
    """Resolve Azure endpoint + api-key or AAD token provider.

    When the key env is unset/empty, use ``DefaultAzureCredential`` (managed
    identity on Azure, ``az login`` locally). Requires ``azure-identity``.
    """
    key_env = _configured_env_name("openai_azure", "api_key_env")
    endpoint_env = _configured_env_name("openai_azure", "endpoint_env")
    api_version = _azure_api_version()

    api_key, key_name = _resolve_env(key_env, *_DEFAULT_AZURE_KEY_ENVS)
    if endpoint_override and endpoint_override.strip():
        endpoint = endpoint_override.strip()
        endpoint_name = "endpoint"
    else:
        endpoint, endpoint_name = _resolve_env(
            endpoint_env, *_DEFAULT_AZURE_ENDPOINT_ENVS
        )

    if not endpoint:
        raise ValueError(
            "Missing environment variable for Azure OpenAI endpoint: "
            f"{endpoint_name or 'AZURE_OPENAI_ENDPOINT'}"
        )

    if api_key:
        return endpoint, api_key, None, api_version

    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    except ImportError as exc:
        raise ValueError(
            "Azure OpenAI API key unset and azure-identity is not installed. "
            f"Set {key_name or 'AZURE_OPENAI_API_KEY'}, or install "
            "`pip install 'agy[azure]'` for managed identity / AAD auth."
        ) from exc

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), _COGNITIVE_SCOPE
    )
    return endpoint, None, token_provider, api_version


def _azure_sync_client(endpoint: str | None) -> Any:
    """Cached ``AzureOpenAI`` client (api-key or ``azure_ad_token_provider``)."""
    from openai import AzureOpenAI

    azure_endpoint, api_key, token_provider, api_version = _azure_auth(endpoint)
    if api_key is not None:

        def factory(
            ep: str = azure_endpoint,
            key: str = api_key,
            ver: str = api_version,
        ) -> Any:
            return AzureOpenAI(azure_endpoint=ep, api_key=key, api_version=ver)

        return _cached_sync_client(
            ("openai_azure", "key", api_key, azure_endpoint, api_version), factory
        )

    def mi_factory(
        ep: str = azure_endpoint,
        provider: Any = token_provider,
        ver: str = api_version,
    ) -> Any:
        return AzureOpenAI(
            azure_endpoint=ep,
            azure_ad_token_provider=provider,
            api_version=ver,
        )

    return _cached_sync_client(
        ("openai_azure", "mi", azure_endpoint, api_version), mi_factory
    )


def _azure_async_client(endpoint: str | None) -> Any:
    """Cached ``AsyncAzureOpenAI`` client (api-key or ``azure_ad_token_provider``)."""
    from openai import AsyncAzureOpenAI

    azure_endpoint, api_key, token_provider, api_version = _azure_auth(endpoint)
    if api_key is not None:

        def factory(
            ep: str = azure_endpoint,
            key: str = api_key,
            ver: str = api_version,
        ) -> Any:
            return AsyncAzureOpenAI(azure_endpoint=ep, api_key=key, api_version=ver)

        return _cached_async_client(
            ("openai_azure", "key", api_key, azure_endpoint, api_version), factory
        )

    def mi_factory(
        ep: str = azure_endpoint,
        provider: Any = token_provider,
        ver: str = api_version,
    ) -> Any:
        return AsyncAzureOpenAI(
            azure_endpoint=ep,
            azure_ad_token_provider=provider,
            api_version=ver,
        )

    return _cached_async_client(
        ("openai_azure", "mi", azure_endpoint, api_version), mi_factory
    )


# Provider Callables (Module-Level Functions)
def openai_llm_call(prompt: str, model: str = "gpt-5-mini", **params) -> str:
    """OpenAI LLM call."""
    from openai import OpenAI

    openai_api_key = _provider_api_key("openai", "OPENAI_API_KEY", "OpenAI")
    client = _cached_sync_client(
        ("openai", openai_api_key),
        lambda key=openai_api_key: OpenAI(api_key=key),
    )
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], **params
    )
    return _require_text(response.choices[0].message.content, "OpenAI")


async def openai_llm_call_async(
    prompt: str, model: str = "gpt-5-mini", **params
) -> str:
    """OpenAI LLM call (async)."""
    from openai import AsyncOpenAI

    openai_api_key = _provider_api_key("openai", "OPENAI_API_KEY", "OpenAI")
    client = _cached_async_client(
        ("openai", openai_api_key),
        lambda key=openai_api_key: AsyncOpenAI(api_key=key),
    )
    response = await client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], **params
    )
    return _require_text(response.choices[0].message.content, "OpenAI")


def openai_azure_llm_call(
    prompt: str, model: str = "gpt-4o", endpoint: str | None = None, **params
) -> str:
    """Azure OpenAI / Azure AI Foundry chat completions (api-key or managed identity)."""
    client = _azure_sync_client(endpoint)
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}], model=model, **params
    )
    return _require_text(response.choices[0].message.content, "Azure OpenAI")


async def openai_azure_llm_call_async(
    prompt: str, model: str = "gpt-4o", endpoint: str | None = None, **params
) -> str:
    """Azure OpenAI / Azure AI Foundry chat completions (async)."""
    client = _azure_async_client(endpoint)
    response = await client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}], model=model, **params
    )
    return _require_text(response.choices[0].message.content, "Azure OpenAI")


def _gemini_client() -> Any:
    from google import genai

    gemini_api_key = _provider_api_key("gemini", "GEMINI_API_KEY", "Google Gemini")
    return _cached_sync_client(
        ("gemini", gemini_api_key),
        lambda key=gemini_api_key: genai.Client(api_key=key),
    )


def gemini_llm_call(prompt: str, model: str = "gemini-2.0-flash", **params) -> str:
    """Google Gemini LLM call."""
    from google.genai import types

    response = _gemini_client().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(**params) if params else None,
    )
    return _require_text(response.text, "Google Gemini")


async def gemini_llm_call_async(
    prompt: str, model: str = "gemini-2.0-flash", **params
) -> str:
    """Google Gemini LLM call (async)."""
    from google.genai import types

    response = await _gemini_client().aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(**params) if params else None,
    )
    return _require_text(response.text, "Google Gemini")


def _first_anthropic_text(response: Any) -> str:
    # Anthropic returns a list of content blocks; take the first text block
    for block in response.content:
        if hasattr(block, "text"):
            return _require_text(block.text, "Anthropic")
    return ""


def anthropic_llm_call(
    prompt: str, model: str = "claude-3-sonnet-20240229", **params
) -> str:
    """Anthropic Claude LLM call."""
    from anthropic import Anthropic

    anthropic_api_key = _provider_api_key("anthropic", "ANTHROPIC_API_KEY", "Anthropic")
    client = _cached_sync_client(
        ("anthropic", anthropic_api_key),
        lambda key=anthropic_api_key: Anthropic(api_key=key),
    )
    response = client.messages.create(
        model=model,
        max_tokens=params.pop("max_tokens", 1024),
        messages=[{"role": "user", "content": prompt}],
        **params,
    )
    return _first_anthropic_text(response)


async def anthropic_llm_call_async(
    prompt: str, model: str = "claude-3-sonnet-20240229", **params
) -> str:
    """Anthropic Claude LLM call (async)."""
    from anthropic import AsyncAnthropic

    anthropic_api_key = _provider_api_key("anthropic", "ANTHROPIC_API_KEY", "Anthropic")
    client = _cached_async_client(
        ("anthropic", anthropic_api_key),
        lambda key=anthropic_api_key: AsyncAnthropic(api_key=key),
    )
    response = await client.messages.create(
        model=model,
        max_tokens=params.pop("max_tokens", 1024),
        messages=[{"role": "user", "content": prompt}],
        **params,
    )
    return _first_anthropic_text(response)


def fake_llm_call(prompt: str, model: str = "no_model", **params: Any) -> str:
    """Fake LLM call for testing - just returns the prompt."""
    return prompt


async def fake_llm_call_async(
    prompt: str, model: str = "no_model", **params: Any
) -> str:
    """Fake async LLM call for testing - just returns the prompt."""
    return prompt


class LLMCall:
    """
    Singleton that manages the current model_call implementation.

    Initialized at project start with config defaults.
    Each thread can have its own model_call (thread-local storage planned for later).
    """

    _instance: "LLMCall | None" = None
    _initialized = False

    def __new__(cls) -> "LLMCall":
        """New.

        Returns:
            'LLMCall': Operation result.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the object."""
        if not self._initialized:
            # Provider Registry (all available provider callables)
            self.provider_registry: dict[str, Callable[..., str]] = {
                "openai": openai_llm_call,
                "openai_azure": openai_azure_llm_call,
                "gemini": gemini_llm_call,
                "anthropic": anthropic_llm_call,
                "fake": fake_llm_call,
            }

            # Async counterparts, keyed by the same provider names.
            self.async_provider_registry: dict[str, Callable[..., Any]] = {
                "openai": openai_llm_call_async,
                "openai_azure": openai_azure_llm_call_async,
                "gemini": gemini_llm_call_async,
                "anthropic": anthropic_llm_call_async,
                "fake": fake_llm_call_async,
            }

            # Current model_call (global for now, thread-local later)
            self._current_callable: Callable[..., str] | None = None
            self._current_async_callable: Callable[..., Any] | None = None

            # Initialize from config
            self._initialize_from_config()
            LLMCall._initialized = True

    def _initialize_from_config(self) -> None:
        """Load default from pyproject.toml or fallback to OpenAI."""
        config = load_llm_config()
        provider = config.get("default_provider", "openai")
        model = config.get("default_model", "gpt-5-mini")
        params = config.get("default_params", {}) or {}
        self.set_model_call(provider=provider, model=model, params=params)

    def set_model_call(
        self,
        provider: str | None = None,
        model: str | None = None,
        params: dict[str, Any] | None = None,
        callable: Callable[..., str] | None = None,
    ) -> None:
        """
        Set the current model_call.

        Either:
        - provider/model/params → Factory builds wrapper
        - callable → Direct set (Custom)

        Args:
            provider: Provider name (openai, openai_azure, gemini, anthropic, fake)
            model: Model name (optional, uses config default if not provided)
            params: Additional parameters dict (optional)
            callable: Custom callable to use directly (optional, overrides provider)
        """
        if callable:
            custom_callable = callable
            if params:
                configured_params = dict(params)

                def wrapper(prompt: str, **kwargs: Any) -> Any:
                    """Apply configured params to custom callables."""
                    final_kwargs = {**configured_params, **kwargs}
                    return custom_callable(prompt, **final_kwargs)

                resolved: Callable[..., Any] = wrapper
            else:
                resolved = custom_callable

            # A custom callable is either sync or async; the other side of the pair
            # is derived on demand in model_call / amodel_call.
            if inspect.iscoroutinefunction(custom_callable):
                self._current_callable = None
                self._current_async_callable = resolved
            else:
                self._current_callable = resolved
                self._current_async_callable = None
        elif provider:
            # Factory builds wrapper
            provider_func = self.provider_registry.get(provider)
            if not provider_func:
                raise ValueError(f"Unknown provider: {provider}")
            async_provider_func = self.async_provider_registry.get(provider)

            # Load config for defaults
            config = load_llm_config()
            default_model = config.get("default_model")
            default_model_name = (
                default_model if isinstance(default_model, str) else "gpt-5-mini"
            )
            default_params = config.get("default_params", {}) or {}

            # Wrapper with model/params
            def wrapper(prompt: str, **kwargs: Any) -> str:
                """Wrapper.

                Args:
                    prompt: prompt.
                    **kwargs: Additional keyword arguments (Any).

                Returns:
                    str: Operation result.
                """
                final_params = {**default_params, **(params or {}), **kwargs}
                final_model = model or default_model_name
                return provider_func(prompt=prompt, model=final_model, **final_params)

            self._current_callable = wrapper

            if async_provider_func is None:
                self._current_async_callable = None
            else:

                async def async_wrapper(prompt: str, **kwargs: Any) -> str:
                    """Async counterpart of the provider wrapper."""
                    final_params = {**default_params, **(params or {}), **kwargs}
                    final_model = model or default_model_name
                    return await async_provider_func(
                        prompt=prompt, model=final_model, **final_params
                    )

                self._current_async_callable = async_wrapper
        else:
            raise ValueError("set_model_call requires either 'callable' or 'provider'")

    def model_call(self, prompt: str, **kwargs: Any) -> str:
        """
        Execute the current model_call.

        This is what classify/respond/extract call.

        Args:
            prompt: The prompt to send to the LLM
            **kwargs: Additional parameters to pass to the model_call

        Returns:
            The LLM response as a string
        """
        if self._current_callable is None and self._current_async_callable is None:
            # Fallback: Initialize with config defaults
            self._initialize_from_config()

        if self._current_callable is None:
            if self._current_async_callable is not None:
                raise ValueError(
                    "The configured model_call is async. Use amodel_call() instead."
                )
            raise ValueError(
                "model_call not initialized. Call set_model_call() first or ensure config is set."
            )

        return _require_text(
            self._current_callable(prompt, **kwargs), "Configured provider"
        )

    async def amodel_call(self, prompt: str, **kwargs: Any) -> str:
        """
        Execute the current model_call without blocking the event loop.

        Providers with a native async implementation are awaited directly. A custom
        sync callable is offloaded to a worker thread so callers can always await.

        Args:
            prompt: The prompt to send to the LLM
            **kwargs: Additional parameters to pass to the model_call

        Returns:
            The LLM response as a string
        """
        if self._current_callable is None and self._current_async_callable is None:
            # Fallback: Initialize with config defaults
            self._initialize_from_config()

        if self._current_async_callable is not None:
            result = await self._current_async_callable(prompt, **kwargs)
            return _require_text(result, "Configured provider")

        if self._current_callable is None:
            raise ValueError(
                "model_call not initialized. Call set_model_call() first or ensure config is set."
            )

        sync_callable = self._current_callable
        result = await asyncio.to_thread(lambda: sync_callable(prompt, **kwargs))
        return _require_text(result, "Configured provider")

    def register_provider(
        self,
        name: str,
        callable: Callable[..., str],
        async_callable: Callable[..., Any] | None = None,
    ) -> None:
        """
        Register a custom provider (e.g., Mistral).

        Only available in code, not as a Flow action.

        Args:
            name: Provider name
            callable: Callable that takes (prompt: str, model: str, **params) -> str
            async_callable: Optional awaitable counterpart used by amodel_call
        """
        self.provider_registry[name] = callable
        if async_callable is not None:
            self.async_provider_registry[name] = async_callable
