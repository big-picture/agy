"""Unit tests for GraphEmailAccount and GmailEmailAccount wrappers."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from agy.integrations.email import Email, GmailEmailAccount, GraphEmailAccount


def _validator_ok(provider=None) -> Mock:
    validator = Mock()
    validator.validate_forward.return_value = (True, "")
    validator.validate_reply.return_value = (True, "")
    return validator


def test_graph_send_email_populates_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    api = Mock()
    api._get_headers.return_value = {"Authorization": "Bearer token"}
    account = GraphEmailAccount(api=api, user_email="user@example.com")

    monkeypatch.setattr(
        "agy.integrations.email.graph_account.requests.post",
        lambda *args, **kwargs: Mock(status_code=202),
    )
    monkeypatch.setattr(
        "agy.integrations.email.email_safety.get_validator",
        _validator_ok,
    )

    email = Email(recipient="to@example.com", subject="s", text="body")
    sent = account.send_email(email)
    assert sent.sender == "user@example.com"
    assert sent.account is account


def test_graph_move_email_requires_message_id() -> None:
    account = GraphEmailAccount(api=Mock(), user_email="user@example.com")
    with pytest.raises(ValueError, match="message_id"):
        account.move_email(Email(subject="x"), "Archive")


def test_graph_move_email_refreshes_message_id_for_follow_up_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = Mock()
    api.get_folder_id_by_name.return_value = "folder-2"
    api.move_message.return_value = {"id": "m2", "isRead": False}
    account = GraphEmailAccount(api=api, user_email="user@example.com")
    email = Email(subject="s", message_id="m1", account=account)

    patch_calls: list[str] = []

    def _fake_patch(url: str, *args, **kwargs) -> Mock:
        patch_calls.append(url)
        return Mock(status_code=200)

    monkeypatch.setattr(
        "agy.integrations.email.graph_account.requests.patch",
        _fake_patch,
    )

    email.move("Archive")
    email.mark_unread()

    assert email.message_id == "m2"
    assert email._folder == "Archive"
    assert email._is_unread is True
    assert patch_calls == [
        "https://graph.microsoft.com/v1.0/users/user@example.com/messages/m2"
    ]


def test_graph_mark_unread_email_sets_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = Mock()
    api._get_headers.return_value = {"Authorization": "Bearer token"}
    account = GraphEmailAccount(api=api, user_email="user@example.com")
    email = Email(subject="s", message_id="m1")

    monkeypatch.setattr(
        "agy.integrations.email.graph_account.requests.patch",
        lambda *args, **kwargs: Mock(status_code=200),
    )

    account.mark_unread_email(email)

    assert email._is_unread is True


def test_graph_add_label_email_merges_existing_categories() -> None:
    api = Mock()
    api.get_message_categories.return_value = ["Existing"]
    api.update_message_categories.return_value = True
    account = GraphEmailAccount(api=api, user_email="user@example.com")
    email = Email(subject="s", message_id="m1")

    account.add_label_email(email, "Erledigt")

    api.update_message_categories.assert_called_once_with(
        "m1",
        ["Existing", "Erledigt"],
        mailbox_type="personal",
        mailbox_upn="user@example.com",
    )
    assert email._labels == ["Existing", "Erledigt"]


def test_graph_has_label_email_reads_categories() -> None:
    api = Mock()
    api.get_message_categories.return_value = ["Existing", "Erledigt"]
    account = GraphEmailAccount(api=api, user_email="user@example.com")
    email = Email(subject="s", message_id="m1")

    assert account.has_label_email(email, "Erledigt") is True
    assert email._labels == ["Existing", "Erledigt"]


def test_gmail_reply_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    api = Mock()
    api._user = "me@example.com"
    api.create_reply_message.return_value = None
    account = GmailEmailAccount(api=api)
    monkeypatch.setattr(
        "agy.integrations.email.email_safety.get_validator",
        _validator_ok,
    )
    with pytest.raises(RuntimeError, match="Failed to send Gmail reply"):
        account.reply_email(
            Email(sender="a@example.com", subject="s", text="orig", message_id="m1"),
            "reply",
        )


def test_gmail_create_draft_with_label(monkeypatch: pytest.MonkeyPatch) -> None:
    api = Mock()
    api._user = "me@example.com"
    api.get_label_id_by_name.return_value = "L1"
    api._service.users().drafts().create().execute.return_value = {
        "message": {"id": "M1"}
    }
    account = GmailEmailAccount(api=api)
    email = Email(recipient="to@example.com", subject="sub", text="body")
    account.create_draft(email, "MyLabel")
    assert email.message_id == "M1"
    assert email.account is account


def test_gmail_mark_unread_calls_modify() -> None:
    api = Mock()
    api._user = "me@example.com"
    account = GmailEmailAccount(api=api)
    email = Email(subject="s", message_id="m1")

    account.mark_unread_email(email)

    api._service.users().messages().modify.assert_called_once_with(
        userId="me@example.com",
        id="m1",
        body={"addLabelIds": ["UNREAD"]},
    )
    assert email._is_unread is True


def test_gmail_add_label_calls_modify() -> None:
    api = Mock()
    api._user = "me@example.com"
    api.get_label_id_by_name.return_value = "L1"
    account = GmailEmailAccount(api=api)
    email = Email(subject="s", message_id="m1")

    account.add_label_email(email, "Erledigt")

    api.get_label_id_by_name.assert_called_once_with("Erledigt", create_if_missing=True)
    api._service.users().messages().modify.assert_called_once_with(
        userId="me@example.com",
        id="m1",
        body={"addLabelIds": ["L1"]},
    )
    assert email._labels == ["Erledigt"]


def test_gmail_has_label_checks_message_label_ids() -> None:
    api = Mock()
    api._user = "me@example.com"
    api.get_label_id_by_name.return_value = "L1"
    api.get_message.return_value = {"id": "m1", "labelIds": ["L1", "UNREAD"]}
    account = GmailEmailAccount(api=api)
    email = Email(subject="s", message_id="m1")

    assert account.has_label_email(email, "Erledigt") is True
    assert email._labels == ["Erledigt"]
