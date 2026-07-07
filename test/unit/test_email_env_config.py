"""Unit tests for provider-scoped email env configuration."""

from __future__ import annotations

import warnings

import pytest

from agy.integrations.email.email_safety import get_validator, reset_validator
from agy.integrations.email.env_config import (
    env_for,
    get_draft_only,
    get_graph_credentials,
    get_safety_config,
    reset_env_warnings,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = [
        "GRAPH_TENANT_ID",
        "TENANT_ID",
        "GRAPH_ALLOWED_EMAIL_DOMAINS",
        "ALLOWED_EMAIL_DOMAINS",
        "GMAIL_EMAIL_DRAFT_ONLY",
        "EMAIL_DRAFT_ONLY",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    reset_env_warnings()
    reset_validator()


def test_env_for_prefers_provider_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPH_TENANT_ID", "prefixed")
    monkeypatch.setenv("TENANT_ID", "legacy")
    assert env_for("graph", "TENANT_ID") == "prefixed"


def test_env_for_falls_back_with_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TENANT_ID", "legacy")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert env_for("graph", "TENANT_ID") == "legacy"
    assert any(
        issubclass(w.category, DeprecationWarning)
        and "TENANT_ID" in str(w.message)
        for w in caught
    )


def test_get_safety_config_uses_provider_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GMAIL_ALLOWED_EMAIL_DOMAINS", "gmail.com,example.com")
    config = get_safety_config("gmail")
    assert config["allowed_domains"] == ["gmail.com", "example.com"]


def test_get_draft_only_provider_specific(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAP_EMAIL_DRAFT_ONLY", "true")
    assert get_draft_only("imap") is True
    assert get_draft_only("graph") is False


def test_get_graph_credentials_resolves_prefixed_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_TENANT_ID", "t")
    monkeypatch.setenv("GRAPH_CLIENT_ID", "c")
    monkeypatch.setenv("GRAPH_CLIENT_SECRET", "s")
    monkeypatch.setenv("GRAPH_USER_EMAIL", "u@example.com")
    creds = get_graph_credentials()
    assert creds["tenant_id"] == "t"
    assert creds["user_email"] == "u@example.com"


def test_get_validator_isolated_per_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPH_ALLOWED_EMAIL_DOMAINS", "graph.com")
    monkeypatch.setenv("GMAIL_ALLOWED_EMAIL_DOMAINS", "gmail.com")
    graph_v = get_validator("graph")
    gmail_v = get_validator("gmail")
    assert graph_v.allowed_domains == ["graph.com"]
    assert gmail_v.allowed_domains == ["gmail.com"]
