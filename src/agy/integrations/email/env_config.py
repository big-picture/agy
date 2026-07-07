"""Provider-scoped email environment variable resolution."""

from __future__ import annotations

import os
import warnings
from typing import Literal

ProviderKey = Literal["graph", "gmail", "imap"]

PROVIDERS: tuple[ProviderKey, ...] = ("graph", "gmail", "imap")

_DEFAULT_ALLOWED_DOMAINS = "big-picture.com"

# (provider, suffix) -> deprecated global env key
_DEPRECATED_GLOBAL_KEYS: dict[tuple[ProviderKey, str], str] = {
    ("graph", "TENANT_ID"): "TENANT_ID",
    ("graph", "CLIENT_ID"): "CLIENT_ID",
    ("graph", "CLIENT_SECRET"): "CLIENT_SECRET",
    ("graph", "USER_EMAIL"): "USER_EMAIL",
    ("graph", "SHARED_MAILBOX_UPN"): "SHARED_MAILBOX_UPN",
    ("graph", "ALLOWED_EMAIL_DOMAINS"): "ALLOWED_EMAIL_DOMAINS",
    ("graph", "ALLOWED_EMAIL_ADDRESSES"): "ALLOWED_EMAIL_ADDRESSES",
    ("graph", "EMAIL_DRAFT_ONLY"): "EMAIL_DRAFT_ONLY",
    ("gmail", "ALLOWED_EMAIL_DOMAINS"): "ALLOWED_EMAIL_DOMAINS",
    ("gmail", "ALLOWED_EMAIL_ADDRESSES"): "ALLOWED_EMAIL_ADDRESSES",
    ("gmail", "EMAIL_DRAFT_ONLY"): "EMAIL_DRAFT_ONLY",
    ("imap", "ALLOWED_EMAIL_DOMAINS"): "ALLOWED_EMAIL_DOMAINS",
    ("imap", "ALLOWED_EMAIL_ADDRESSES"): "ALLOWED_EMAIL_ADDRESSES",
    ("imap", "EMAIL_DRAFT_ONLY"): "EMAIL_DRAFT_ONLY",
}

_warned_fallbacks: set[tuple[ProviderKey, str]] = set()


def _provider_prefix(provider: ProviderKey) -> str:
    return provider.upper()


def env_for(
    provider: ProviderKey,
    suffix: str,
    *,
    deprecated_global: str | None = None,
) -> str | None:
    """
    Resolve an env var for a provider.

    Lookup order: {PROVIDER}_{suffix} -> deprecated_global -> None.
    """
    prefixed = f"{_provider_prefix(provider)}_{suffix}"
    value = os.getenv(prefixed)
    if value is not None and value.strip() != "":
        return value

    global_key = deprecated_global or _DEPRECATED_GLOBAL_KEYS.get((provider, suffix))
    if global_key:
        fallback = os.getenv(global_key)
        if fallback is not None and fallback.strip() != "":
            warn_key = (provider, suffix)
            if warn_key not in _warned_fallbacks:
                _warned_fallbacks.add(warn_key)
                warnings.warn(
                    f"Environment variable {global_key!r} is deprecated for "
                    f"{provider} email integration. Use {prefixed!r} instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            return fallback
    return None


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def get_safety_config(provider: ProviderKey) -> dict[str, list[str]]:
    """Return allowed domains/addresses for a provider from env."""
    domains_raw = env_for(provider, "ALLOWED_EMAIL_DOMAINS")
    addresses_raw = env_for(provider, "ALLOWED_EMAIL_ADDRESSES")

    domains = _split_csv(domains_raw)
    if not domains and domains_raw is None and addresses_raw is None:
        domains = _split_csv(_DEFAULT_ALLOWED_DOMAINS)

    return {
        "allowed_domains": domains,
        "allowed_addresses": _split_csv(addresses_raw),
    }


def get_draft_only(provider: ProviderKey) -> bool:
    """Return True if draft-only mode is enabled for the provider."""
    raw = env_for(provider, "EMAIL_DRAFT_ONLY")
    if raw is None:
        return False
    return raw.strip().lower() in ("true", "1", "yes")


def get_graph_credentials() -> dict[str, str | None]:
    """Resolve Microsoft Graph credentials from env."""
    return {
        "tenant_id": env_for("graph", "TENANT_ID"),
        "client_id": env_for("graph", "CLIENT_ID"),
        "client_secret": env_for("graph", "CLIENT_SECRET"),
        "mailbox_upn": env_for("graph", "SHARED_MAILBOX_UPN")
        or env_for("graph", "USER_EMAIL"),
        "user_email": env_for("graph", "USER_EMAIL"),
    }


def reset_env_warnings() -> None:
    """Clear deprecation warning cache (for tests)."""
    _warned_fallbacks.clear()
