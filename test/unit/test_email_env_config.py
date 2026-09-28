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


# ---------------------------------------------------------------------------
# Explicit allow-all ("*")
# ---------------------------------------------------------------------------


@pytest.fixture
def _no_address_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("GRAPH_ALLOWED_EMAIL_ADDRESSES", "ALLOWED_EMAIL_ADDRESSES"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.usefixtures("_no_address_env")
@pytest.mark.parametrize("value", ["*", " * ", "*,big-picture.com"])
def test_graph_allowed_domains_star_allows_any_domain(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("GRAPH_ALLOWED_EMAIL_DOMAINS", value)
    v = get_validator("graph")
    assert v.allow_all is True
    assert v.validate_recipients(["a@supplier.org", "B <b@other.net>"]) == (True, "")
    assert v.validate_forward("x@anything.io") == (True, "")


@pytest.mark.usefixtures("_no_address_env")
def test_legacy_allowed_domains_star_allows_any_domain_for_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "*")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        v = get_validator("graph")
    assert v.allow_all is True
    assert v.validate_recipients(["a@supplier.org"])[0] is True


@pytest.mark.usefixtures("_no_address_env")
def test_global_allowed_domains_star_allows_any_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "*")
    v = get_validator()
    assert v.allow_all is True
    assert v.validate_recipient("a@supplier.org")[0] is True


@pytest.mark.usefixtures("_no_address_env")
def test_allow_all_still_rejects_malformed_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_ALLOWED_EMAIL_DOMAINS", "*")
    v = get_validator("graph")
    assert v.validate_recipients(["not-an-address"])[0] is False
    assert v.validate_recipients([])[0] is False


@pytest.mark.usefixtures("_no_address_env")
def test_allow_all_logs_single_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("GRAPH_ALLOWED_EMAIL_DOMAINS", "*")
    with caplog.at_level("INFO", logger="agy.integrations.email.email_safety"):
        v = get_validator("graph")
        get_validator("graph")
        v.validate_recipients(["a@x.org", "b@y.org"])
        v.validate_forward("c@z.org")
    warnings_logged = [
        r
        for r in caplog.records
        if r.levelname == "WARNING" and "allow" in r.getMessage().lower()
    ]
    assert len(warnings_logged) == 1
    assert "graph" in warnings_logged[0].getMessage().lower()


@pytest.mark.usefixtures("_no_address_env")
def test_default_allowlist_unchanged_when_unset() -> None:
    v = get_validator("graph")
    assert v.allow_all is False
    assert v.allowed_domains == ["big-picture.com"]
    assert v.validate_recipients(["a@big-picture.com"])[0] is True
    assert v.validate_recipients(["a@supplier.org"])[0] is False


@pytest.mark.usefixtures("_no_address_env")
def test_star_inside_domain_is_not_a_wildcard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_ALLOWED_EMAIL_DOMAINS", "*.example.com")
    v = get_validator("graph")
    assert v.allow_all is False
    assert v.validate_recipients(["a@sub.example.com"])[0] is False
