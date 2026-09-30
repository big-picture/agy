"""Regression coverage for draft safety, body round trips and authentication."""

from unittest.mock import Mock

import pytest
import requests

from agy.integrations.email import (
    Email,
    EmailPermanentError,
    EmailSafetyError,
    EmailTransientError,
    GraphEmailAccount,
)
from agy.integrations.email.email_safety import EmailSafetyValidator


@pytest.fixture
def account(monkeypatch):
    api = Mock()
    api._get_headers.return_value = {}
    api.get_folder_id_by_name.return_value = "drafts"
    account = GraphEmailAccount(api=api, user_email="me@example.com")
    monkeypatch.setattr(account, "_should_draft_only", lambda _: False)
    validator = EmailSafetyValidator(
        allowed_domains=["example.com"], allowed_addresses=[]
    )
    monkeypatch.setattr(
        "agy.integrations.email.email_safety.get_validator", lambda _: validator
    )
    return account


@pytest.mark.parametrize("only_bcc", [False, True])
@pytest.mark.parametrize("allowed", [False, True])
def test_stored_bcc_is_checked(account, monkeypatch, only_bcc, allowed):
    draft = {
        "toRecipients": (
            [] if only_bcc else [{"emailAddress": {"address": "safe@example.com"}}]
        ),
        "bccRecipients": [
            {
                "emailAddress": {
                    "address": "bcc@example.com" if allowed else "bcc@external.test"
                }
            }
        ],
    }

    def get(url, **kwargs):
        # Model Graph's projection: omitted fields are not returned.
        selected = kwargs["params"]["$select"].split(",")
        return Mock(
            status_code=200,
            json=lambda: {k: v for k, v in draft.items() if k in selected},
        )

    monkeypatch.setattr(requests, "get", get)
    post = Mock(return_value=Mock(status_code=202))
    monkeypatch.setattr(requests, "post", post)
    if allowed:
        account.send_draft("draft")
        post.assert_called_once()
    else:
        with pytest.raises(EmailSafetyError):
            account.send_draft("draft")
        post.assert_not_called()


@pytest.mark.parametrize("operation", ["send", "draft"])
def test_read_html_can_be_sent_as_converted_plain_text(account, monkeypatch, operation):
    email = account._graph_message_to_email(
        {
            "toRecipients": [{"emailAddress": {"address": "safe@example.com"}}],
            "body": {"contentType": "html", "content": "<p>first</p>\n<p>second</p>"},
        }
    )
    post = Mock(
        return_value=Mock(
            status_code=202 if operation == "send" else 201,
            json=lambda: {"id": "draft"},
        )
    )
    monkeypatch.setattr(requests, "post", post)
    if operation == "send":
        account.send_email(email)
        body = post.call_args.kwargs["json"]["message"]["body"]
    else:
        account.create_draft(email, "drafts")
        body = post.call_args.kwargs["json"]["body"]
    assert body["content"] == "first<br/>second"
    assert email.body_type == "text"


@pytest.mark.parametrize("refresh", [False, True])
@pytest.mark.parametrize(
    "failure,expected",
    [
        (requests.ConnectTimeout("token timeout"), EmailTransientError),
        (requests.ReadTimeout("token timeout"), EmailTransientError),
        (requests.ConnectionError("token disconnected"), EmailTransientError),
        (requests.exceptions.SSLError("certificate invalid"), EmailPermanentError),
    ],
)
def test_authentication_errors_are_typed(
    account, monkeypatch, refresh, failure, expected
):
    account.api._get_headers.side_effect = [{}, failure] if refresh else failure
    post = Mock(return_value=Mock(status_code=401))
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(expected) as caught:
        account.send_email(Email(recipient="safe@example.com"))
    assert caught.value.__cause__ is failure
    assert post.call_count == int(refresh)


@pytest.mark.parametrize(
    "status,expected",
    [
        (429, EmailTransientError),
        (503, EmailTransientError),
        (401, EmailPermanentError),
    ],
)
def test_token_http_errors_preserve_status_and_retry_after(
    account, monkeypatch, status, expected
):
    response = requests.Response()
    response.status_code = status
    response.headers["Retry-After"] = "15"
    account.api._get_headers.side_effect = requests.HTTPError(response=response)
    post = Mock()
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(expected) as caught:
        account.send_email(Email(recipient="safe@example.com"))
    assert caught.value.status_code == status
    if status != 401:
        assert caught.value.retry_after == 15
    post.assert_not_called()
