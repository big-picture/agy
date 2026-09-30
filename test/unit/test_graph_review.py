"""Regression tests for PR #7's outbound Graph review."""

from unittest.mock import Mock

import pytest
import requests

from agy.integrations.email import (
    Email,
    EmailPermanentError,
    EmailTransientError,
    GraphEmailAccount,
)
from agy.integrations.email._graph_api import GraphAPI
from agy.integrations.email.email_safety import EmailSafetyValidator


def response(status=200, data=None):
    return Mock(
        status_code=status,
        headers={"Retry-After": "12"},
        text="error",
        json=Mock(return_value=data),
    )


@pytest.fixture
def account(monkeypatch):
    api = GraphAPI(tenant_id="t", client_id="c", client_secret="s")
    monkeypatch.setattr(api, "_get_headers", Mock(return_value={}))
    account = GraphEmailAccount(api=api, user_email="me@example.com")
    monkeypatch.setattr(account, "_should_draft_only", lambda _: False)
    validator = EmailSafetyValidator(
        allowed_domains=["example.com"], allowed_addresses=[]
    )
    monkeypatch.setattr(
        "agy.integrations.email.email_safety.get_validator", lambda _: validator
    )
    return account


@pytest.mark.parametrize("folder", ["drafts", "Custom", "Parent/Child"])
@pytest.mark.parametrize(
    "failure,expected",
    [
        (requests.ReadTimeout("read"), EmailTransientError),
        (requests.ConnectionError("disconnected"), EmailTransientError),
        (requests.exceptions.SSLError("TLS"), EmailPermanentError),
        (response(429), EmailTransientError),
        (response(503), EmailTransientError),
        (response(403), EmailPermanentError),
    ],
)
def test_real_folder_resolver_preserves_errors(
    account, monkeypatch, folder, failure, expected
):
    get = Mock(side_effect=[failure])
    post = Mock()
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(expected) as error:
        account.create_draft(Email(), folder)
    if not isinstance(failure, Exception):
        assert error.value.status_code == failure.status_code
        if expected is EmailTransientError:
            assert error.value.retry_after == 12
    assert get.call_count == 1
    post.assert_not_called()


def test_folder_auth_refresh_and_pagination(account, monkeypatch):
    base = f"{account.GRAPH_ROOT}/users/me@example.com/mailFolders"
    get = Mock(
        side_effect=[
            response(401),
            response(data={"value": [], "@odata.nextLink": base + "?page=2"}),
            response(data={"value": [{"id": "parent", "displayName": "Parent"}]}),
            response(data={"value": [{"id": "child", "displayName": "Child"}]}),
        ]
    )
    monkeypatch.setattr(requests, "get", get)
    post = Mock(return_value=response(201, {"id": "new"}))
    monkeypatch.setattr(requests, "post", post)
    assert account.create_draft(Email(), "Parent/Child") == "new"
    assert [c.args[0] for c in get.call_args_list] == [
        base,
        base,
        base + "?page=2",
        base + "/parent/childFolders",
    ]
    assert account.api._get_headers.call_args_list[1].kwargs == {
        "force_refresh_token": True
    }
    assert post.call_args.args[0].endswith("/mailFolders/child/messages")


def test_missing_folder_is_typed(account, monkeypatch):
    monkeypatch.setattr(
        requests, "get", Mock(return_value=response(data={"value": []}))
    )
    with pytest.raises(EmailPermanentError, match="not found"):
        account.create_draft(Email(), "Absent")


@pytest.mark.parametrize("operation", ["send", "draft"])
def test_display_names_use_same_address_for_safety_and_payload(
    account, monkeypatch, operation
):
    monkeypatch.setattr(
        requests, "get", Mock(return_value=response(data={"id": "drafts"}))
    )
    post = Mock(
        return_value=response(202 if operation == "send" else 201, {"id": "new"})
    )
    monkeypatch.setattr(requests, "post", post)
    email = Email(
        recipient="Alice <alice@example.com>, bob@example.com",
        cc="Carol <carol@example.com>",
    )
    if operation == "send":
        account.send_email(email)
        payload = post.call_args.kwargs["json"]["message"]
    else:
        account.create_draft(email, "drafts")
        payload = post.call_args.kwargs["json"]
    assert payload["toRecipients"] == [
        {"emailAddress": {"address": a}}
        for a in ["alice@example.com", "bob@example.com"]
    ]
    assert payload["ccRecipients"] == [
        {"emailAddress": {"address": "carol@example.com"}}
    ]


@pytest.mark.parametrize(
    "data",
    [None, [], {}, {"id": None}, {"id": 42}, {"id": ""}, {"id": "  "}, "invalid-json"],
)
def test_invalid_draft_creation_does_not_reuse_old_id(account, monkeypatch, data):
    monkeypatch.setattr(
        requests, "get", Mock(return_value=response(data={"id": "drafts"}))
    )
    result = response(201, data)
    if data == "invalid-json":
        result.json.side_effect = requests.exceptions.JSONDecodeError("bad", "x", 0)
    post = Mock(return_value=result)
    monkeypatch.setattr(requests, "post", post)
    email = Email(message_id="old")
    with pytest.raises(EmailPermanentError, match="may have been accepted") as error:
        account.create_draft(email, "drafts")
    assert error.value.status_code == 201
    assert email.message_id == "old"
    assert post.call_count == 1


@pytest.mark.parametrize("operation", ["folder", "envelope"])
@pytest.mark.parametrize("data", [None, [], "invalid-json"])
def test_malformed_read_response_is_typed_and_does_not_send(
    account, monkeypatch, operation, data
):
    result = response(data=data)
    if data == "invalid-json":
        result.json.side_effect = requests.exceptions.JSONDecodeError("bad", "x", 0)
    monkeypatch.setattr(requests, "get", Mock(return_value=result))
    post = Mock()
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(EmailTransientError) as error:
        if operation == "folder":
            account.create_draft(Email(), "drafts")
        else:
            account.send_draft("draft")
    assert error.value.status_code == 200
    post.assert_not_called()
