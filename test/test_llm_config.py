"""Tests for LLM / provider config loading from pyproject.toml."""

from __future__ import annotations

from pathlib import Path

from agy.config import get_provider_config, load_llm_config, reset_cache


def test_load_llm_config_reads_tool_agy_providers(
    tmp_path: Path, monkeypatch
) -> None:
    """``[tool.agy.providers.*]`` lands in load_llm_config()['providers']."""
    reset_cache()
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.agy.llm]
default_provider = "openai_azure"
default_model = "gpt-4o"

[tool.agy.providers.openai_azure]
api_key_env = "AZURE_AI_SERVICES_KEY"
endpoint_env = "AZURE_AI_SERVICES_OPENAI_ENDPOINT"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_llm_config()
    assert config["default_provider"] == "openai_azure"
    assert config["providers"]["openai_azure"]["api_key_env"] == "AZURE_AI_SERVICES_KEY"
    assert (
        get_provider_config("openai_azure")["endpoint_env"]
        == "AZURE_AI_SERVICES_OPENAI_ENDPOINT"
    )


def test_load_llm_config_falls_back_to_top_level_providers(
    tmp_path: Path, monkeypatch
) -> None:
    """Legacy top-level ``[providers.*]`` still loads when tool.agy.providers absent."""
    reset_cache()
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.agy.llm]
default_provider = "openai"

[providers.openai]
api_key_env = "CUSTOM_OPENAI_KEY"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_llm_config()
    assert config["providers"]["openai"]["api_key_env"] == "CUSTOM_OPENAI_KEY"


def test_reset_cache_clears_llm_config(tmp_path: Path, monkeypatch) -> None:
    """reset_cache() forces reload of provider tables after pyproject changes."""
    reset_cache()
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.agy.llm]
default_provider = "openai"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert load_llm_config()["default_provider"] == "openai"

    (tmp_path / "pyproject.toml").write_text(
        """
[tool.agy.llm]
default_provider = "anthropic"
""",
        encoding="utf-8",
    )
    assert load_llm_config()["default_provider"] == "openai"  # cached
    reset_cache()
    assert load_llm_config()["default_provider"] == "anthropic"
