"""Unit tests for Graph outbound safety: typed errors, recipients, token refresh."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
import requests

from agy.integrations.email import (
    Email,
    EmailPermanentError,
    EmailSafetyError,
    EmailSendError,
    EmailTransientError,
    GraphEmailAccount,
)

GRAPH = "https://graph.microsoft.com/v1.0"


class _Recorder:
    """Record requests.<method> calls and return queued responses."""

    def __init__(self, *responses: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses)

    def __call__(self, url: str, *args: Any, **kwargs: Any) -> Any:
        self.calls.append({"url": url, **kwargs})
        response = self._responses.pop(0) if self._responses else Mock()
        if isinstance(response, Exception):
            raise response
        return response


def _validator(ok: bool = True) -> Mock:
    validator = Mock()
    result = (ok, "" if ok else "not allowed")
    validator.validate_recipients.return_value = result
    validator.validate_forward.return_value = result
    return validator


def _resp(status: int, headers: dict[str, str] | None = None) -> Mock:
    return Mock(status_code=status, text="body", headers=headers or {})


@pytest.fixture
def account() -> GraphEmailAccount:
    api = Mock()
    api._get_headers.return_value = {"Authorization": "Bearer token"}
    api.get_folder_id_by_name.return_value = "drafts-folder-id"
    return GraphEmailAccount(api=api, user_email="user@example.com")


@pytest.fixture
def validator(monkeypatch: pytest.MonkeyPatch) -> Mock:
    v = _validator(ok=True)
    monkeypatch.setattr(
        "agy.integrations.email.email_safety.get_validator",
        lambda provider=None: v,
    )
    return v


@pytest.fixture(autouse=True)
def _no_draft_only_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("EMAIL_DRAFT_ONLY", "GRAPH_EMAIL_DRAFT_ONLY"):
        monkeypatch.delenv(name, raising=False)


def _patch_post(monkeypatch: pytest.MonkeyPatch, *responses: Any) -> _Recorder:
    recorder = _Recorder(*responses)
    monkeypatch.setattr("agy.integrations.email.graph_account.requests.post", recorder)
    return recorder


def _send_email(account: GraphEmailAccount) -> Any:
    return account.send_email(Email(recipient="to@example.com", subject="s", text="t"))


def _send_draft(account: GraphEmailAccount) -> Any:
    return account.send_draft(Email(recipient="to@example.com", message_id="d1"))


def _create_draft(account: GraphEmailAccount) -> Any:
    return account.create_draft(Email(recipient="to@example.com"), "drafts")


# (operation, success status, message prefix)
OPERATIONS = [
    pytest.param(_send_email, 202, "Failed to send email", id="send_email"),
    pytest.param(_send_draft, 202, "Failed to send draft", id="send_draft"),
    pytest.param(_create_draft, 201, "Failed to create draft", id="create_draft"),
]


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


def test_error_hierarchy_subclasses_runtime_error() -> None:
    assert issubclass(EmailSendError, RuntimeError)
    assert issubclass(EmailTransientError, EmailSendError)
    assert issubclass(EmailPermanentError, EmailSendError)
    assert issubclass(EmailSafetyError, EmailPermanentError)
    assert not issubclass(EmailTransientError, EmailPermanentError)


def test_error_attributes_default_to_none() -> None:
    transient = EmailTransientError("x")
    assert transient.status_code is None
    assert transient.retry_after is None
    assert EmailPermanentError("x").status_code is None
    assert EmailSafetyError("x").status_code is None
    assert str(EmailTransientError("msg", status_code=429, retry_after=3.0)) == "msg"


def test_errors_module_exports() -> None:
    from agy.integrations.email import errors

    assert errors.EmailSendError is EmailSendError
    assert errors.EmailSafetyError is EmailSafetyError


# ---------------------------------------------------------------------------
# HTTP status classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [429, 503, 504])
@pytest.mark.parametrize(("operation", "ok_status", "prefix"), OPERATIONS)
def test_retryable_status_raises_transient(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    operation: Any,
    ok_status: int,
    prefix: str,
    status: int,
) -> None:
    _patch_post(monkeypatch, _resp(status))

    with pytest.raises(EmailTransientError, match=f"^{prefix}: HTTP {status}") as info:
        operation(account)

    assert info.value.status_code == status
    assert info.value.retry_after is None


@pytest.mark.parametrize(
    ("header", "expected"),
    [("7", 7.0), ("1.5", 1.5), ("0", 0.0), ("Wed, 21 Oct 2026 07:28:00 GMT", None)],
)
def test_transient_error_parses_retry_after_seconds(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    header: str,
    expected: float | None,
) -> None:
    _patch_post(monkeypatch, _resp(429, headers={"Retry-After": header}))

    with pytest.raises(EmailTransientError) as info:
        _send_email(account)

    assert info.value.retry_after == expected


@pytest.mark.parametrize("status", [400, 403, 404, 500])
@pytest.mark.parametrize(("operation", "ok_status", "prefix"), OPERATIONS)
def test_other_status_raises_permanent(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    operation: Any,
    ok_status: int,
    prefix: str,
    status: int,
) -> None:
    _patch_post(monkeypatch, _resp(status))

    with pytest.raises(EmailPermanentError, match=f"^{prefix}: HTTP {status}") as info:
        operation(account)

    assert info.value.status_code == status
    assert not isinstance(info.value, EmailSafetyError)


# ---------------------------------------------------------------------------
# requests exception classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.ConnectionError("conn refused"),
        requests.exceptions.ConnectTimeout("connect timeout"),
    ],
    ids=["ConnectionError", "ConnectTimeout"],
)
@pytest.mark.parametrize(("operation", "ok_status", "prefix"), OPERATIONS)
def test_connection_failures_raise_transient_from_exc(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    operation: Any,
    ok_status: int,
    prefix: str,
    exc: Exception,
) -> None:
    _patch_post(monkeypatch, exc)

    with pytest.raises(EmailTransientError, match=f"^{prefix}: ") as info:
        operation(account)

    assert info.value.__cause__ is exc
    assert info.value.status_code is None


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.ReadTimeout("read timeout"),
        requests.exceptions.InvalidURL("bad url"),
    ],
    ids=["ReadTimeout", "InvalidURL"],
)
@pytest.mark.parametrize(("operation", "ok_status", "prefix"), OPERATIONS)
def test_ambiguous_or_invalid_requests_raise_permanent_from_exc(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    operation: Any,
    ok_status: int,
    prefix: str,
    exc: Exception,
) -> None:
    """ReadTimeout is ambiguous (Graph may have accepted it): never retry."""
    _patch_post(monkeypatch, exc)

    with pytest.raises(EmailPermanentError, match=f"^{prefix}: ") as info:
        operation(account)

    assert info.value.__cause__ is exc


# ---------------------------------------------------------------------------
# Backwards compatibility
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [_resp(429), _resp(404), requests.exceptions.ConnectionError("boom")],
    ids=["transient-http", "permanent-http", "connection-error"],
)
def test_except_runtime_error_still_catches_send_failures(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    response: Any,
) -> None:
    _patch_post(monkeypatch, response)

    try:
        _send_email(account)
    except RuntimeError as exc:
        assert str(exc).startswith("Failed to send email: ")
    else:  # pragma: no cover - the send must fail
        pytest.fail("send_email did not raise")


def test_safety_failure_raises_safety_error_with_legacy_prefix(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount
) -> None:
    monkeypatch.setattr(
        "agy.integrations.email.email_safety.get_validator",
        lambda provider=None: _validator(ok=False),
    )
    post = _patch_post(monkeypatch, _resp(202))

    with pytest.raises(EmailSafetyError, match="^Safety check failed: not allowed"):
        _send_email(account)
    with pytest.raises(RuntimeError, match="^Safety check failed: not allowed"):
        _send_draft(account)

    assert post.calls == []


# ---------------------------------------------------------------------------
# Per-address recipient validation with the real validator
# ---------------------------------------------------------------------------


@pytest.fixture
def real_validator(monkeypatch: pytest.MonkeyPatch):
    from agy.integrations.email.email_safety import EmailSafetyValidator

    v = EmailSafetyValidator(allowed_domains=["example.com"], allowed_addresses=[])
    monkeypatch.setattr(
        "agy.integrations.email.email_safety.get_validator",
        lambda provider=None: v,
    )
    return v


@pytest.mark.parametrize(
    ("to", "cc"),
    [
        ("x@evil.org, a@example.com", ""),  # used to pass: last domain only
        ("a@example.com", "x@evil.org"),  # Cc used to be unchecked
        ("a@example.com", "b@example.com, Eve <x@evil.org>"),
    ],
)
def test_send_email_rejects_any_disallowed_to_or_cc(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    real_validator: Any,
    to: str,
    cc: str,
) -> None:
    post = _patch_post(monkeypatch, _resp(202))

    with pytest.raises(EmailSafetyError, match="^Safety check failed: .*x@evil.org"):
        account.send_email(Email(recipient=to, cc=cc, subject="s", text="t"))

    assert post.calls == []


def test_send_email_accepts_all_allowed_to_and_cc(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, real_validator: Any
) -> None:
    post = _patch_post(monkeypatch, _resp(202))

    account.send_email(
        Email(
            recipient="a@example.com, B <b@example.com>",
            cc="c@example.com",
            subject="s",
            text="t",
        )
    )

    assert len(post.calls) == 1


def test_send_draft_rejects_disallowed_cc_loaded_from_graph(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, real_validator: Any
) -> None:
    get = _Recorder(
        Mock(
            status_code=200,
            json=Mock(
                return_value={
                    "id": "d1",
                    "toRecipients": [{"emailAddress": {"address": "a@example.com"}}],
                    "ccRecipients": [{"emailAddress": {"address": "x@evil.org"}}],
                }
            ),
        )
    )
    monkeypatch.setattr("agy.integrations.email.graph_account.requests.get", get)
    post = _patch_post(monkeypatch, _resp(202))

    with pytest.raises(EmailSafetyError, match="x@evil.org"):
        account.send_draft("d1")

    assert post.calls == []


def test_create_draft_and_draft_only_still_bypass_allowlist(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, real_validator: Any
) -> None:
    post = _patch_post(monkeypatch, _resp(201), _resp(201))
    email = Email(recipient="x@evil.org", cc="y@evil.org")

    account.create_draft(email, "drafts")
    account.send_email(email, draft_only=True)

    assert len(post.calls) == 2


# ---------------------------------------------------------------------------
# 401 -> refresh token once and retry once
# ---------------------------------------------------------------------------


def _refreshing_account() -> GraphEmailAccount:
    api = Mock()
    api._get_headers.side_effect = lambda force_refresh_token=False: {
        "Authorization": "Bearer fresh" if force_refresh_token else "Bearer stale"
    }
    api.get_folder_id_by_name.return_value = "drafts-folder-id"
    return GraphEmailAccount(api=api, user_email="user@example.com")


@pytest.mark.parametrize(("operation", "ok_status", "prefix"), OPERATIONS)
def test_401_refreshes_token_and_retries_once(
    monkeypatch: pytest.MonkeyPatch,
    validator: Mock,
    operation: Any,
    ok_status: int,
    prefix: str,
) -> None:
    account = _refreshing_account()
    ok = _resp(ok_status)
    ok.json = Mock(return_value={"id": "draft-1"})
    post = _patch_post(monkeypatch, _resp(401), ok)

    operation(account)

    assert [c["headers"]["Authorization"] for c in post.calls] == [
        "Bearer stale",
        "Bearer fresh",
    ]
    assert post.calls[0]["url"] == post.calls[1]["url"]
    assert post.calls[0].get("json") == post.calls[1].get("json")
    account.api._get_headers.assert_any_call(force_refresh_token=True)


@pytest.mark.parametrize(("operation", "ok_status", "prefix"), OPERATIONS)
def test_second_401_raises_permanent_without_further_retries(
    monkeypatch: pytest.MonkeyPatch,
    validator: Mock,
    operation: Any,
    ok_status: int,
    prefix: str,
) -> None:
    account = _refreshing_account()
    post = _patch_post(monkeypatch, _resp(401), _resp(401), _resp(ok_status))

    with pytest.raises(EmailPermanentError, match=f"^{prefix}: HTTP 401") as info:
        operation(account)

    assert info.value.status_code == 401
    assert len(post.calls) == 2


def test_retry_after_401_is_classified_like_any_response(
    monkeypatch: pytest.MonkeyPatch, validator: Mock
) -> None:
    account = _refreshing_account()
    _patch_post(monkeypatch, _resp(401), _resp(503, headers={"Retry-After": "12"}))

    with pytest.raises(EmailTransientError) as info:
        _send_email(account)

    assert info.value.status_code == 503
    assert info.value.retry_after == 12.0


def test_no_token_refresh_without_401(
    monkeypatch: pytest.MonkeyPatch, validator: Mock
) -> None:
    account = _refreshing_account()
    post = _patch_post(monkeypatch, _resp(202))

    _send_email(account)

    assert len(post.calls) == 1
    for call in account.api._get_headers.call_args_list:
        assert not call.kwargs.get("force_refresh_token")
