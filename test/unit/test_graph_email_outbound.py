"""Unit tests for GraphEmailAccount outbound payloads: bodies, drafts, send_draft."""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import Mock

import pytest
import requests

from agy.integrations.email import (
    Attachment,
    Email,
    EmailAccount,
    EmailBodyType,
    GraphEmailAccount,
    MockEmailAccount,
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
    validator.validate_forward.return_value = (ok, "" if ok else "not allowed")
    validator.validate_reply.return_value = (ok, "" if ok else "not allowed")
    return validator


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


def _draft_created(draft_id: str = "draft-1") -> Mock:
    return Mock(status_code=201, json=Mock(return_value={"id": draft_id}))


def _full_email(**overrides: Any) -> Email:
    values: dict[str, Any] = {
        "recipient": "to@example.com, to2@example.com",
        "cc": "cc@example.com, ",
        "subject": "Subject",
        "text": "Line 1\nLine <2> & more",
        "attachments": [
            Attachment(
                filename="report.pdf",
                content=b"%PDF-bytes",
                content_type="application/pdf",
            )
        ],
    }
    values.update(overrides)
    return Email(**values)


EXPECTED_ATTACHMENTS = [
    {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": "report.pdf",
        "contentBytes": base64.b64encode(b"%PDF-bytes").decode("utf-8"),
        "contentType": "application/pdf",
    }
]


# ---------------------------------------------------------------------------
# EmailBodyType
# ---------------------------------------------------------------------------


def test_email_body_type_values_match_read_path_values() -> None:
    assert EmailBodyType.TEXT == "text"
    assert EmailBodyType.HTML == "html"
    assert Email().body_type == ""


def test_email_create_accepts_body_type() -> None:
    email = Email.create(
        to="to@example.com", subject="s", text="<p>x</p>", body_type=EmailBodyType.HTML
    )
    assert email.body_type == EmailBodyType.HTML


# ---------------------------------------------------------------------------
# send_email bodies
# ---------------------------------------------------------------------------


def test_send_email_plain_text_is_escaped_unchanged(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    post = _patch_post(monkeypatch, Mock(status_code=202))

    account.send_email(Email(recipient="to@example.com", text="a <b> & c\n\nd\ne"))

    body = post.calls[0]["json"]["message"]["body"]
    assert body == {
        "contentType": "HTML",
        "content": "a &lt;b&gt; &amp; c<br/><br/>d<br/>e",
    }


@pytest.mark.parametrize("body_type", [EmailBodyType.TEXT, "text", "", "TEXT"])
def test_send_email_non_html_body_types_are_escaped(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    body_type: str,
) -> None:
    post = _patch_post(monkeypatch, Mock(status_code=202))

    account.send_email(
        Email(recipient="to@example.com", text="<p>x</p>", body_type=body_type)
    )

    assert post.calls[0]["json"]["message"]["body"]["content"] == "&lt;p&gt;x&lt;/p&gt;"


@pytest.mark.parametrize("body_type", [EmailBodyType.HTML, "html", "HTML"])
def test_send_email_html_body_is_passed_through(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    body_type: str,
) -> None:
    post = _patch_post(monkeypatch, Mock(status_code=202))
    html_body = "<p>Hello &amp; <b>world</b></p>\n<table><tr><td>1</td></tr></table>"

    account.send_email(
        Email(recipient="to@example.com", text=html_body, body_type=body_type)
    )

    assert post.calls[0]["json"]["message"]["body"] == {
        "contentType": "HTML",
        "content": html_body,
    }


def test_send_email_payload_is_unchanged_for_existing_callers(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    post = _patch_post(monkeypatch, Mock(status_code=202))

    account.send_email(_full_email())

    call = post.calls[0]
    assert call["url"] == f"{GRAPH}/users/user@example.com/sendMail"
    assert call["json"] == {
        "message": {
            "subject": "Subject",
            "body": {
                "contentType": "HTML",
                "content": "Line 1<br/>Line &lt;2&gt; &amp; more",
            },
            "toRecipients": [
                {"emailAddress": {"address": "to@example.com"}},
                {"emailAddress": {"address": "to2@example.com"}},
            ],
            "ccRecipients": [{"emailAddress": {"address": "cc@example.com"}}],
            "attachments": EXPECTED_ATTACHMENTS,
        },
        "saveToSentItems": "true",
    }
    validator.validate_forward.assert_called_once_with(
        "to@example.com, to2@example.com"
    )


# ---------------------------------------------------------------------------
# create_draft
# ---------------------------------------------------------------------------


def test_create_draft_includes_cc_and_attachments(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount
) -> None:
    post = _patch_post(monkeypatch, _draft_created("draft-42"))
    email = _full_email()

    draft_id = account.create_draft(email, "drafts")

    assert draft_id == "draft-42"
    assert email.message_id == "draft-42"
    assert email.account is account
    call = post.calls[0]
    assert call["url"] == (
        f"{GRAPH}/users/user@example.com/mailFolders/drafts-folder-id/messages"
    )
    assert call["json"] == {
        "subject": "Subject",
        "body": {
            "contentType": "HTML",
            "content": "Line 1<br/>Line &lt;2&gt; &amp; more",
        },
        "toRecipients": [
            {"emailAddress": {"address": "to@example.com"}},
            {"emailAddress": {"address": "to2@example.com"}},
        ],
        "ccRecipients": [{"emailAddress": {"address": "cc@example.com"}}],
        "attachments": EXPECTED_ATTACHMENTS,
    }


def test_create_draft_without_cc_or_attachments(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount
) -> None:
    post = _patch_post(monkeypatch, _draft_created())

    account.create_draft(Email(recipient="to@example.com", text="hi"), "drafts")

    message = post.calls[0]["json"]
    assert message["ccRecipients"] == []
    assert "attachments" not in message


def test_create_draft_html_body_is_passed_through(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount
) -> None:
    post = _patch_post(monkeypatch, _draft_created())

    account.create_draft(
        Email(recipient="to@example.com", text="<p>Hi</p>", body_type="html"),
        "drafts",
    )

    assert post.calls[0]["json"]["body"] == {
        "contentType": "HTML",
        "content": "<p>Hi</p>",
    }


def test_create_draft_http_error_raises(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount
) -> None:
    _patch_post(monkeypatch, Mock(status_code=400, text="bad"))

    with pytest.raises(RuntimeError, match="Failed to create draft: HTTP 400"):
        account.create_draft(Email(recipient="to@example.com"), "drafts")


def test_send_email_draft_only_creates_complete_draft(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    monkeypatch.setenv("GRAPH_EMAIL_DRAFT_ONLY", "true")
    post = _patch_post(monkeypatch, _draft_created("draft-7"))
    email = _full_email(text="<p>Hi</p>", body_type=EmailBodyType.HTML)

    result = account.send_email(email)

    assert result is email
    assert email.message_id == "draft-7"
    assert len(post.calls) == 1
    call = post.calls[0]
    assert call["url"].endswith("/mailFolders/drafts-folder-id/messages")
    assert call["json"]["ccRecipients"] == [
        {"emailAddress": {"address": "cc@example.com"}}
    ]
    assert call["json"]["attachments"] == EXPECTED_ATTACHMENTS
    assert call["json"]["body"]["content"] == "<p>Hi</p>"
    validator.validate_forward.assert_not_called()


def test_draft_and_send_payloads_match(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    post = _patch_post(monkeypatch, Mock(status_code=202), _draft_created())

    account.send_email(_full_email())
    account.create_draft(_full_email(), "drafts")

    assert post.calls[0]["json"]["message"] == post.calls[1]["json"]


# ---------------------------------------------------------------------------
# send_draft
# ---------------------------------------------------------------------------


def test_send_draft_posts_to_send_endpoint(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    post = _patch_post(monkeypatch, Mock(status_code=202))
    email = Email(recipient="to@example.com", message_id="draft-1")

    result = account.send_draft(email)

    assert result is email
    assert email.sender == "user@example.com"
    assert email.account is account
    call = post.calls[0]
    assert call["url"] == f"{GRAPH}/users/user@example.com/messages/draft-1/send"
    assert call["headers"] == {"Authorization": "Bearer token"}
    validator.validate_forward.assert_called_once_with("to@example.com")


def test_send_draft_accepts_draft_id_and_validates_server_recipients(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    get = _Recorder(
        Mock(
            status_code=200,
            json=Mock(
                return_value={
                    "id": "draft-9",
                    "subject": "S",
                    "toRecipients": [
                        {"emailAddress": {"address": "a@example.com"}},
                        {"emailAddress": {"address": "b@example.com"}},
                    ],
                    "ccRecipients": [{"emailAddress": {"address": "c@example.com"}}],
                }
            ),
        )
    )
    monkeypatch.setattr("agy.integrations.email.graph_account.requests.get", get)
    post = _patch_post(monkeypatch, Mock(status_code=202))

    result = account.send_draft("draft-9")

    assert get.calls[0]["url"] == f"{GRAPH}/users/user@example.com/messages/draft-9"
    assert result.message_id == "draft-9"
    assert result.recipient == "a@example.com, b@example.com"
    assert result.cc == "c@example.com"
    assert result.subject == "S"
    assert result.sender == "user@example.com"
    assert result.account is account
    validator.validate_forward.assert_called_once_with("a@example.com, b@example.com")
    assert (
        post.calls[0]["url"] == f"{GRAPH}/users/user@example.com/messages/draft-9/send"
    )


def test_send_draft_safety_failure_does_not_send(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount
) -> None:
    monkeypatch.setattr(
        "agy.integrations.email.email_safety.get_validator",
        lambda provider=None: _validator(ok=False),
    )
    post = _patch_post(monkeypatch, Mock(status_code=202))

    with pytest.raises(RuntimeError, match="Safety check failed: not allowed"):
        account.send_draft(Email(recipient="evil@example.org", message_id="d1"))

    assert post.calls == []


def test_send_draft_uses_graph_validator(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount
) -> None:
    providers: list[str | None] = []

    def _get_validator(provider=None) -> Mock:
        providers.append(provider)
        return _validator(ok=True)

    monkeypatch.setattr(
        "agy.integrations.email.email_safety.get_validator", _get_validator
    )
    _patch_post(monkeypatch, Mock(status_code=202))

    account.send_draft(Email(recipient="to@example.com", message_id="d1"))

    assert providers == ["graph"]


@pytest.mark.parametrize("env_name", ["EMAIL_DRAFT_ONLY", "GRAPH_EMAIL_DRAFT_ONLY"])
def test_send_draft_in_draft_only_mode_leaves_draft_unsent(
    monkeypatch: pytest.MonkeyPatch,
    account: GraphEmailAccount,
    validator: Mock,
    env_name: str,
) -> None:
    """Draft-only mode is a kill switch: nothing is sent, the draft stays put."""
    monkeypatch.setenv(env_name, "true")
    post = _patch_post(monkeypatch, Mock(status_code=202))
    email = Email(recipient="to@example.com", message_id="d1")

    result = account.send_draft(email)

    assert result is email
    assert post.calls == []
    validator.validate_forward.assert_not_called()


def test_send_draft_draft_only_param_leaves_draft_unsent(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    post = _patch_post(monkeypatch, Mock(status_code=202))

    result = account.send_draft("d1", draft_only=True)

    assert result.message_id == "d1"
    assert result.account is account
    assert post.calls == []


def test_send_draft_id_fetch_failure_raises(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    monkeypatch.setattr(
        "agy.integrations.email.graph_account.requests.get",
        _Recorder(Mock(status_code=404, text="missing")),
    )
    post = _patch_post(monkeypatch, Mock(status_code=202))

    with pytest.raises(RuntimeError, match="Failed to load draft: HTTP 404"):
        account.send_draft("d1")

    assert post.calls == []


def test_send_draft_non_202_raises(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    _patch_post(monkeypatch, Mock(status_code=404, text="not found"))

    with pytest.raises(RuntimeError, match="Failed to send draft: HTTP 404"):
        account.send_draft(Email(recipient="to@example.com", message_id="d1"))


def test_send_draft_request_exception_raises(
    monkeypatch: pytest.MonkeyPatch, account: GraphEmailAccount, validator: Mock
) -> None:
    _patch_post(monkeypatch, requests.exceptions.ConnectionError("boom"))

    with pytest.raises(RuntimeError, match="Failed to send draft: boom"):
        account.send_draft(Email(recipient="to@example.com", message_id="d1"))


def test_send_draft_requires_message_id(
    account: GraphEmailAccount, validator: Mock
) -> None:
    with pytest.raises(ValueError, match="message_id"):
        account.send_draft(Email(recipient="to@example.com"))


def test_send_draft_default_is_not_implemented(tmp_path) -> None:
    mock_account = MockEmailAccount(base_path=tmp_path)
    assert type(mock_account).send_draft is EmailAccount.send_draft
    with pytest.raises(NotImplementedError):
        mock_account.send_draft("d1")


def test_email_send_draft_delegates_to_account() -> None:
    fake_account = Mock()
    email = Email(message_id="d1", account=fake_account)
    fake_account.send_draft.return_value = email

    assert email.send_draft() is email
    fake_account.send_draft.assert_called_once_with(email, draft_only=False)
