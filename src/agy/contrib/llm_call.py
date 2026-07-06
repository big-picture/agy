# agy/contrib/llm_call.py
"""LLM Call Singleton - Central management for all LLM provider calls."""

import os
from collections.abc import Callable
from typing import Any

from agy.config import load_llm_config


def _require_text(value: Any, provider: str) -> str:
    """Normalize provider response text to a guaranteed string."""
    if isinstance(value, str):
        return value
    if value is None:
        raise ValueError(f"{provider} returned empty response text")
    return str(value)


# Provider Callables (Module-Level Functions)
def openai_llm_call(prompt: str, model: str = "gpt-5-mini", **params) -> str:
    """OpenAI LLM call."""
    from openai import OpenAI

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("Missing environment variable for OpenAI: OPENAI_API_KEY")

    client = OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], **params
    )
    return _require_text(response.choices[0].message.content, "OpenAI")


def openai_azure_llm_call(
    prompt: str, model: str = "gpt-4o", endpoint: str | None = None, **params
) -> str:
    """Azure OpenAI LLM call."""
    from openai import AzureOpenAI

    azure_api_key = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv(
        "OPENAI_API_AZURE_KEY"
    )
    azure_endpoint = (
        endpoint
        or os.getenv("AZURE_OPENAI_ENDPOINT")
        or os.getenv("OPENAI_AZURE_BASE_URL")
    )

    if not azure_api_key or not azure_endpoint:
        raise ValueError(
            "Missing environment variables for Azure OpenAI: AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT"
        )

    client = AzureOpenAI(
        azure_endpoint=azure_endpoint,
        api_key=azure_api_key,
        api_version="2024-02-15-preview",
    )
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}], model=model, **params
    )
    return _require_text(response.choices[0].message.content, "Azure OpenAI")


def gemini_llm_call(prompt: str, model: str = "gemini-2.0-flash", **params) -> str:
    """Google Gemini LLM call."""
    from google import genai
    from google.genai import types

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError(
            "Missing environment variable for Google Gemini: GEMINI_API_KEY"
        )

    client = genai.Client(api_key=gemini_api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(**params) if params else None,
    )
    return _require_text(response.text, "Google Gemini")


def anthropic_llm_call(
    prompt: str, model: str = "claude-3-sonnet-20240229", **params
) -> str:
    """Anthropic Claude LLM call."""
    from anthropic import Anthropic

    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ValueError(
            "Missing environment variable for Anthropic: ANTHROPIC_API_KEY"
        )

    client = Anthropic(api_key=anthropic_api_key)
    response = client.messages.create(
        model=model,
        max_tokens=params.pop("max_tokens", 1024),
        messages=[{"role": "user", "content": prompt}],
        **params,
    )
    # Anthropic returns a list of content blocks; take the first text block
    for block in response.content:
        if hasattr(block, "text"):
            return _require_text(block.text, "Anthropic")
    return ""


def fake_llm_call(prompt: str, model: str = "no_model", **params: Any) -> str:
    """Fake LLM call for testing - just returns the prompt."""
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

            # Current model_call (global for now, thread-local later)
            self._current_callable: Callable[..., str] | None = None

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
            if params:
                configured_params = dict(params)
                custom_callable = callable

                def wrapper(prompt: str, **kwargs: Any) -> str:
                    """Apply configured params to custom callables."""
                    final_kwargs = {**configured_params, **kwargs}
                    return custom_callable(prompt, **final_kwargs)

                self._current_callable = wrapper
            else:
                self._current_callable = callable
        elif provider:
            # Factory builds wrapper
            provider_func = self.provider_registry.get(provider)
            if not provider_func:
                raise ValueError(f"Unknown provider: {provider}")

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
        if self._current_callable is None:
            # Fallback: Initialize with config defaults
            self._initialize_from_config()
            if self._current_callable is None:
                raise ValueError(
                    "model_call not initialized. Call set_model_call() first or ensure config is set."
                )

        return _require_text(
            self._current_callable(prompt, **kwargs), "Configured provider"
        )

    def register_provider(self, name: str, callable: Callable[..., str]) -> None:
        """
        Register a custom provider (e.g., Mistral).

        Only available in code, not as a Flow action.

        Args:
            name: Provider name
            callable: Callable that takes (prompt: str, model: str, **params) -> str
        """
        self.provider_registry[name] = callable
