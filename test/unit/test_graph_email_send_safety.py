"""Unit tests for Graph outbound safety: typed errors, recipients, token refresh."""

from __future__ import annotations

import socket
from http.client import RemoteDisconnected
from typing import Any
from unittest.mock import Mock

import pytest
import requests
from urllib3.connection import HTTPSConnection
from urllib3.exceptions import (
    ConnectTimeoutError,
    MaxRetryError,
    NameResolutionError,
    NewConnectionError,
    ProtocolError,
)

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


def _draft_envelope(
    to: tuple[str, ...] = ("to@example.com",), cc: tuple[str, ...] = ()
) -> Mock:
    """GET /messages/{id} response for a stored draft's envelope."""
    return Mock(
        status_code=200,
        json=Mock(
            return_value={
                "id": "d1",
                "subject": "Stored subject",
                "toRecipients": [{"emailAddress": {"address": a}} for a in to],
                "ccRecipients": [{"emailAddress": {"address": a}} for a in cc],
            }
        ),
    )


@pytest.fixture(autouse=True)
def draft_get(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """send_draft always loads the stored draft's recipients first."""
    recorder = _Recorder(*[_draft_envelope() for _ in range(5)])
    monkeypatch.setattr("agy.integrations.email.graph_account.requests.get", recorder)
    return recorder


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


@pytest.mark.parametrize("status", [429, 502, 503, 504])
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


@pytest.mark.parametrize("status", [429, 502, 503])
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
    status: int,
) -> None:
    _patch_post(monkeypatch, _resp(status, headers={"Retry-After": header}))

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


# Exceptions built the way requests.adapters.HTTPAdapter.send wraps urllib3's.
_URL = "/v1.0/users/user@example.com/sendMail"


def _conn() -> HTTPSConnection:
    return HTTPSConnection("graph.microsoft.com", 443)


def _conn_refused() -> requests.exceptions.ConnectionError:
    reason = NewConnectionError(
        _conn(), "Failed to establish a new connection: [Errno 61] Connection refused"
    )
    return requests.exceptions.ConnectionError(MaxRetryError(None, _URL, reason))  # type: ignore[arg-type]


def _dns_failure() -> requests.exceptions.ConnectionError:
    reason = NameResolutionError(
        "graph.microsoft.com", _conn(), socket.gaierror(8, "nodename nor servname")
    )
    return requests.exceptions.ConnectionError(MaxRetryError(None, _URL, reason))  # type: ignore[arg-type]


def _conn_refused_as_context() -> requests.exceptions.ConnectionError:
    """Only the implicit __context__ carries the urllib3 cause."""
    try:
        raise NewConnectionError(_conn(), "Connection refused")
    except NewConnectionError:
        try:
            raise requests.exceptions.ConnectionError("connection failed")
        except requests.exceptions.ConnectionError as exc:
            return exc


def _connect_timeout() -> requests.exceptions.ConnectTimeout:
    reason = ConnectTimeoutError(_conn(), "Connection to graph timed out")
    return requests.exceptions.ConnectTimeout(MaxRetryError(None, _URL, reason))  # type: ignore[arg-type]


def _remote_disconnected() -> requests.exceptions.ConnectionError:
    return requests.exceptions.ConnectionError(
        ProtocolError(
            "Connection aborted.",
            RemoteDisconnected("Remote end closed connection without response"),
        )
    )


def _connection_reset() -> requests.exceptions.ConnectionError:
    return requests.exceptions.ConnectionError(
        ProtocolError(
            "Connection aborted.", ConnectionResetError(54, "Connection reset by peer")
        )
    )


def _protocol_error_after_retries() -> requests.exceptions.ConnectionError:
    reason = ProtocolError("Connection aborted.", RemoteDisconnected("closed"))
    return requests.exceptions.ConnectionError(MaxRetryError(None, _URL, reason))  # type: ignore[arg-type]


def _bare_connection_error() -> requests.exceptions.ConnectionError:
    return requests.exceptions.ConnectionError("boom")


@pytest.mark.parametrize(
    "make_exc",
    [_conn_refused, _dns_failure, _conn_refused_as_context, _connect_timeout],
)
@pytest.mark.parametrize(("operation", "ok_status", "prefix"), OPERATIONS)
def test_connection_never_established_raises_transient_from_exc(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    operation: Any,
    ok_status: int,
    prefix: str,
    make_exc: Any,
) -> None:
    exc = make_exc()
    _patch_post(monkeypatch, exc)

    with pytest.raises(EmailTransientError, match=f"^{prefix}: ") as info:
        operation(account)

    assert info.value.__cause__ is exc
    assert info.value.status_code is None


@pytest.mark.parametrize(
    "make_exc",
    [
        _remote_disconnected,
        _connection_reset,
        _protocol_error_after_retries,
        _bare_connection_error,
    ],
)
@pytest.mark.parametrize(("operation", "ok_status", "prefix"), OPERATIONS)
def test_connection_lost_after_connect_raises_permanent_from_exc(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    operation: Any,
    ok_status: int,
    prefix: str,
    make_exc: Any,
) -> None:
    """The request may have reached Graph: retrying could send it twice."""
    exc = make_exc()
    _patch_post(monkeypatch, exc)

    with pytest.raises(EmailPermanentError, match=f"^{prefix}: ") as info:
        operation(account)

    assert info.value.__cause__ is exc
    assert "may have been accepted" in str(info.value)


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


def test_read_timeout_message_notes_possible_acceptance(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    _patch_post(monkeypatch, requests.exceptions.ReadTimeout("read timeout"))

    with pytest.raises(EmailPermanentError, match="may have been accepted"):
        _send_email(account)


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
    post = _patch_post(
        monkeypatch,
        Mock(status_code=201, json=lambda: {"id": "draft-1"}),
        Mock(status_code=201, json=lambda: {"id": "draft-2"}),
    )
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


# ---------------------------------------------------------------------------
# send_draft validates the stored draft's recipients
# ---------------------------------------------------------------------------


def test_send_draft_validates_stored_cc_even_if_caller_passed_recipients(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    real_validator: Any,
    draft_get: _Recorder,
) -> None:
    monkeypatch.setattr(
        "agy.integrations.email.graph_account.requests.get",
        get := _Recorder(_draft_envelope(("a@example.com",), ("x@evil.org",))),
    )
    post = _patch_post(monkeypatch, _resp(202))

    with pytest.raises(EmailSafetyError, match="^Safety check failed: .*x@evil.org"):
        account.send_draft(
            Email(recipient="a@example.com", cc="", subject="S", message_id="d1")
        )

    assert get.calls[0]["url"] == f"{GRAPH}/users/user@example.com/messages/d1"
    assert post.calls == []


def test_send_draft_validates_stored_to_not_caller_to(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    monkeypatch.setattr(
        "agy.integrations.email.graph_account.requests.get",
        _Recorder(_draft_envelope(("server@example.com",), ("cc@example.com",))),
    )
    _patch_post(monkeypatch, _resp(202))
    email = Email(recipient="caller@example.com", subject="Mine", message_id="d1")

    result = account.send_draft(email)

    validator.validate_recipients.assert_called_once_with(
        ["server@example.com", "cc@example.com"], operation="send"
    )
    assert result.recipient == "server@example.com"
    assert result.cc == "cc@example.com"
    assert result.subject == "Mine"


def test_send_draft_uses_stored_subject_when_caller_has_none(
    account: GraphEmailAccount, validator: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_post(monkeypatch, _resp(202))

    result = account.send_draft("d1")

    assert result.subject == "Stored subject"


@pytest.mark.parametrize(
    ("response", "error", "match"),
    [
        (_resp(503), EmailTransientError, "^Failed to load draft: HTTP 503$"),
        (_resp(502), EmailTransientError, "^Failed to load draft: HTTP 502$"),
        (_resp(404), EmailPermanentError, "^Failed to load draft: HTTP 404$"),
        (_conn_refused(), EmailTransientError, "^Failed to load draft: "),
        # The load is an idempotent GET: ambiguous failures are safe to retry.
        (_remote_disconnected(), EmailTransientError, "^Failed to load draft: "),
        (_connection_reset(), EmailTransientError, "^Failed to load draft: "),
        (
            _protocol_error_after_retries(),
            EmailTransientError,
            "^Failed to load draft: ",
        ),
        (_bare_connection_error(), EmailTransientError, "^Failed to load draft: "),
        (
            requests.exceptions.ReadTimeout("read timeout"),
            EmailTransientError,
            "^Failed to load draft: ",
        ),
        (
            requests.exceptions.InvalidURL("bad url"),
            EmailPermanentError,
            "^Failed to load draft: ",
        ),
    ],
    ids=[
        "503",
        "502",
        "404",
        "refused",
        "aborted",
        "reset",
        "protocol-after-retries",
        "bare-connection-error",
        "read-timeout",
        "invalid-url",
    ],
)
def test_send_draft_envelope_load_failures_are_typed(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    response: Any,
    error: type[Exception],
    match: str,
) -> None:
    monkeypatch.setattr(
        "agy.integrations.email.graph_account.requests.get", _Recorder(response)
    )
    post = _patch_post(monkeypatch, _resp(202))

    with pytest.raises(error, match=match) as info:
        _send_draft(account)

    assert isinstance(info.value, RuntimeError)
    assert "may have been accepted" not in str(info.value)
    if isinstance(response, Exception):
        assert info.value.__cause__ is response
    assert post.calls == []
    validator.validate_recipients.assert_not_called()


@pytest.mark.parametrize(
    "make_exc",
    [
        _remote_disconnected,
        _connection_reset,
        _bare_connection_error,
        lambda: requests.exceptions.ReadTimeout("read timeout"),
    ],
    ids=["aborted", "reset", "bare-connection-error", "read-timeout"],
)
def test_send_draft_ambiguous_failure_on_send_post_stays_permanent(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    draft_get: _Recorder,
    make_exc: Any,
) -> None:
    """Same failure: transient on the envelope GET, permanent on the /send POST."""
    exc = make_exc()
    _patch_post(monkeypatch, exc)

    with pytest.raises(EmailPermanentError, match="^Failed to send draft: ") as info:
        _send_draft(account)

    assert not isinstance(info.value, EmailTransientError)
    assert "may have been accepted" in str(info.value)
    assert info.value.__cause__ is exc
    assert len(draft_get.calls) == 1


def test_send_draft_envelope_load_retries_once_on_401(
    monkeypatch: pytest.MonkeyPatch, validator: Mock
) -> None:
    account = _refreshing_account()
    get = _Recorder(_resp(401), _draft_envelope())
    monkeypatch.setattr("agy.integrations.email.graph_account.requests.get", get)
    _patch_post(monkeypatch, _resp(202))

    _send_draft(account)

    assert [c["headers"]["Authorization"] for c in get.calls] == [
        "Bearer stale",
        "Bearer fresh",
    ]
