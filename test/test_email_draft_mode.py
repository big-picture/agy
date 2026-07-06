from __future__ import annotations

import logging

import pytest

from agy.integrations.email.account import EmailAccount
from agy.integrations.email.email import Email
from agy.integrations.email.mock_account import MockEmailAccount


class _RecordingAccount(EmailAccount):
    def __init__(self) -> None:
        self.last_call: tuple | None = None

    def get_emails(
        self,
        *,
        folders: list[str] | None = None,
        max_results: int = 100,
        only_unread: bool = False,
    ) -> list[Email]:
        return []

    def find_emails(
        self,
        *,
        folders: list[str] | None = None,
        max_results: int = 100,
        to_contains: str | None = None,
        from_contains: str | None = None,
        cc_contains: str | None = None,
        subject_contains: str | None = None,
        body_contains: str | None = None,
        has_attachments: bool | None = None,
        email_contains: str | None = None,
    ) -> list[Email]:
        return []

    def send_email(self, email: Email, *, draft_only: bool = False) -> Email:
        self.last_call = ("send_email", email, draft_only)
        return email

    def reply_email(
        self,
        email: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list | None = None,
        draft_only: bool = False,
    ) -> Email:
        self.last_call = ("reply_email", email, text, subject, attachments, draft_only)
        return Email(
            sender="agent@example.com",
            recipient=email.sender,
            subject=subject or f"Re: {email.subject}",
            text=text,
            account=self,
        )

    def reply_all_email(
        self,
        email: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list | None = None,
        draft_only: bool = False,
    ) -> Email:
        self.last_call = (
            "reply_all_email",
            email,
            text,
            subject,
            attachments,
            draft_only,
        )
        return Email(
            sender="agent@example.com",
            recipient=", ".join(filter(None, [email.sender, email.cc])),
            subject=subject or f"Re: {email.subject}",
            text=text,
            account=self,
        )

    def forward_email(
        self, email: Email, to: str, *, draft_only: bool = False
    ) -> Email:
        self.last_call = ("forward_email", email, to, draft_only)
        return Email(
            sender="agent@example.com",
            recipient=to,
            subject=f"FW: {email.subject}",
            text=email.text,
            account=self,
        )

    def move_email(self, email: Email, folder: str) -> None:
        email._folder = folder

    def copy_email(self, email: Email, folder: str) -> None:
        return None

    def delete_email(self, email: Email) -> None:
        return None

    def mark_read_email(self, email: Email) -> None:
        self.last_call = ("mark_read_email", email)

    def mark_unread_email(self, email: Email) -> None:
        self.last_call = ("mark_unread_email", email)

    def add_label_email(
        self, email: Email, text: str, *, color: str | None = None
    ) -> None:
        self.last_call = ("add_label_email", email, text, color)

    def has_label_email(self, email: Email, text: str) -> bool:
        self.last_call = ("has_label_email", email, text)
        return False

    def enrich_email(self, email: Email, content) -> None:
        return None

    def enrich_email_hidden(self, email: Email, content) -> None:
        return None

    def create_draft(self, email: Email, folder: str) -> None:
        email._folder = folder
        email.account = self


@pytest.fixture
def recording_account() -> _RecordingAccount:
    return _RecordingAccount()


@pytest.fixture
def sample_email(recording_account: _RecordingAccount) -> Email:
    return Email(
        sender="customer@external.example",
        recipient="support@example.com",
        subject="Need help",
        text="Can you help me?",
        cc="team@example.com",
        message_id="msg-123",
        account=recording_account,
    )


def test_should_draft_only_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMAIL_DRAFT_ONLY", raising=False)
    account = _RecordingAccount()

    assert account._should_draft_only(False) is False


def test_should_draft_only_honors_call_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EMAIL_DRAFT_ONLY", raising=False)
    account = _RecordingAccount()

    assert account._should_draft_only(True) is True


@pytest.mark.parametrize("value", ["true", "1", "yes", "TRUE"])
def test_should_draft_only_honors_env_var(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("EMAIL_DRAFT_ONLY", value)
    account = _RecordingAccount()

    assert account._should_draft_only(False) is True


def test_email_reply_passes_draft_only_flag(
    sample_email: Email, recording_account: _RecordingAccount
) -> None:
    sample_email.reply("Draft this reply", draft_only=True)

    assert recording_account.last_call is not None
    assert recording_account.last_call[0] == "reply_email"
    assert recording_account.last_call[-1] is True


def test_email_reply_all_passes_draft_only_flag(
    sample_email: Email, recording_account: _RecordingAccount
) -> None:
    sample_email.reply_all("Draft this reply-all", draft_only=True)

    assert recording_account.last_call is not None
    assert recording_account.last_call[0] == "reply_all_email"
    assert recording_account.last_call[-1] is True


def test_email_send_passes_draft_only_flag(
    sample_email: Email, recording_account: _RecordingAccount
) -> None:
    sample_email.send(draft_only=True)

    assert recording_account.last_call == ("send_email", sample_email, True)


def test_email_forward_passes_draft_only_flag(
    sample_email: Email, recording_account: _RecordingAccount
) -> None:
    sample_email.forward("reviewer@example.com", draft_only=True)

    assert recording_account.last_call == (
        "forward_email",
        sample_email,
        "reviewer@example.com",
        True,
    )


def test_email_mark_unread_delegates_to_account(
    sample_email: Email, recording_account: _RecordingAccount
) -> None:
    sample_email.mark_unread()

    assert recording_account.last_call == ("mark_unread_email", sample_email)


def test_mock_send_uses_sent_folder_by_default(tmp_path) -> None:
    account = MockEmailAccount(base_path=tmp_path, user_email="agent@example.com")
    email = Email(
        recipient="customer@external.example",
        subject="Response",
        text="Hello there",
        account=account,
    )

    sent = email.send()

    assert sent._folder == "sent"
    assert len(list((tmp_path / "sent").glob("*.eml"))) == 1
    assert len(list((tmp_path / "drafts").glob("*.eml"))) == 0


def test_mock_send_uses_drafts_folder_when_draft_only(tmp_path) -> None:
    account = MockEmailAccount(base_path=tmp_path, user_email="agent@example.com")
    email = Email(
        recipient="customer@external.example",
        subject="Response",
        text="Hello there",
        account=account,
    )

    drafted = email.send(draft_only=True)

    assert drafted._folder == "drafts"
    assert len(list((tmp_path / "drafts").glob("*.eml"))) == 1
    assert len(list((tmp_path / "sent").glob("*.eml"))) == 0


def test_mock_send_uses_drafts_folder_when_env_enabled(
    tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("EMAIL_DRAFT_ONLY", "true")
    account = MockEmailAccount(base_path=tmp_path, user_email="agent@example.com")
    email = Email(
        recipient="blocked@outside.example",
        subject="Response",
        text="Hello there",
        account=account,
    )

    with caplog.at_level(logging.INFO):
        drafted = email.send()

    assert drafted._folder == "drafts"
    assert len(list((tmp_path / "drafts").glob("*.eml"))) == 1
    assert "EMAIL_DRAFT_ONLY" in caplog.text
    assert "draft" in caplog.text.lower()


def test_mock_reply_uses_drafts_folder_when_draft_only(tmp_path) -> None:
    account = MockEmailAccount(base_path=tmp_path, user_email="agent@example.com")
    original = account.add_email(
        folder="inbox",
        sender="blocked@outside.example",
        recipient="agent@example.com",
        subject="Question",
        text="Can you help?",
    )

    reply = original.reply("Prepared for review", draft_only=True)

    assert reply._folder == "drafts"
    assert len(list((tmp_path / "drafts").glob("*.eml"))) == 1
    assert len(list((tmp_path / "sent").glob("*.eml"))) == 0


def test_mock_forward_uses_drafts_folder_when_env_enabled(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMAIL_DRAFT_ONLY", "true")
    account = MockEmailAccount(base_path=tmp_path, user_email="agent@example.com")
    original = account.add_email(
        folder="inbox",
        sender="customer@external.example",
        recipient="agent@example.com",
        subject="Question",
        text="Can you help?",
    )

    forward = original.forward("blocked@outside.example")

    assert forward._folder == "drafts"
    assert len(list((tmp_path / "drafts").glob("*.eml"))) == 1
    assert len(list((tmp_path / "sent").glob("*.eml"))) == 0
