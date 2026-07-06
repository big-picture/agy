"""Email dataclass with bound account methods."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .account import EmailAccount


@dataclass
class Attachment:
    """Email attachment."""

    filename: str
    content: bytes = field(default=b"", repr=False)
    content_type: str = "application/octet-stream"

    @classmethod
    def from_path(cls, path: str | Path) -> Attachment:
        """Create attachment from file path."""
        p = Path(path)
        content = p.read_bytes()
        return cls(filename=p.name, content=content)


@dataclass
class Email:
    """
    Email object with optional bound account.

    Can be created standalone (account=None) or with an account for operations.
    """

    sender: str = ""
    recipient: str = ""
    subject: str = ""
    text: str = ""
    cc: str = ""
    reply_to: str = ""
    body_type: str = ""
    message_id: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    account: EmailAccount | None = field(default=None, repr=False)

    # Internal: folder where email is stored (for file-based accounts)
    _folder: str | None = field(default=None, repr=False)
    _is_unread: bool | None = field(default=None, repr=False)
    _labels: list[str] = field(default_factory=list, repr=False)

    def _require_account(self) -> EmailAccount:
        """Raise if no account is bound."""
        if self.account is None:
            raise ValueError("Email has no bound account. Set email.account first.")
        return self.account

    def reply(
        self,
        text: str,
        *,
        subject: str | None = None,
        attachments: list[Attachment] | None = None,
        draft_only: bool = False,
    ) -> Email:
        """
        Reply to the sender of this email.

        Args:
            text: Reply message text
            subject: Override the reply subject (default: keeps original)
            attachments: Attachment objects to include in the reply

        Returns:
            The sent reply email
        """
        return self._require_account().reply_email(
            self,
            text,
            subject=subject,
            attachments=attachments,
            draft_only=draft_only,
        )

    def reply_all(
        self,
        text: str,
        *,
        subject: str | None = None,
        attachments: list[Attachment] | None = None,
        draft_only: bool = False,
    ) -> Email:
        """
        Reply to all recipients of this email.

        Args:
            text: Reply message text
            subject: Override the reply subject (default: keeps original)
            attachments: Attachment objects to include in the reply

        Returns:
            The sent reply email
        """
        return self._require_account().reply_all_email(
            self,
            text,
            subject=subject,
            attachments=attachments,
            draft_only=draft_only,
        )

    def forward(self, to: str, *, draft_only: bool = False) -> Email:
        """
        Forward this email.

        Args:
            to: Recipient address

        Returns:
            The sent forwarded email
        """
        return self._require_account().forward_email(self, to, draft_only=draft_only)

    def move(self, folder: str) -> None:
        """
        Move this email to a folder.

        Args:
            folder: Target folder name
        """
        self._require_account().move_email(self, folder)
        self._folder = folder

    def copy(self, folder: str) -> None:
        """
        Copy this email to a folder, keeping the original in place.

        Args:
            folder: Target folder name
        """
        self._require_account().copy_email(self, folder)

    def enrich(self, content) -> None:
        """
        Enrich this email with visible content.

        Args:
            content: Content to add (string or dict with 'result' key)
        """
        self._require_account().enrich_email(self, content)

    def enrich_hidden(self, content) -> None:
        """
        Enrich this email with hidden content.

        Args:
            content: Hidden content to add
        """
        self._require_account().enrich_email_hidden(self, content)

    def delete(self) -> None:
        """Delete this email."""
        self._require_account().delete_email(self)

    def mark_read(self) -> None:
        """Mark this email as read."""
        self._require_account().mark_read_email(self)
        self._is_unread = False

    def mark_unread(self) -> None:
        """Mark this email as unread."""
        self._require_account().mark_unread_email(self)
        self._is_unread = True

    def add_label(self, text: str) -> None:
        """
        Add a label/category to this email.

        Args:
            text: Label/category name.
        """
        self._require_account().add_label_email(self, text)

    def has_label(self, text: str) -> bool:
        """
        Check whether this email has a label/category.

        Args:
            text: Label/category name to check.
        """
        return self._require_account().has_label_email(self, text)

    def send(self, *, draft_only: bool = False) -> Email:
        """
        Send this email.

        Returns:
            The sent email (may have updated message_id)
        """
        return self._require_account().send_email(self, draft_only=draft_only)

    @classmethod
    def create(
        cls,
        *,
        to: str,
        subject: str,
        text: str,
        sender: str = "",
        cc: str = "",
        attachments: list[str | Path] | None = None,
        account: EmailAccount | None = None,
        folder: str | None = None,
    ) -> Email:
        """
        Create a new email, optionally saving as draft.

        Args:
            to: Recipient address
            subject: Email subject
            text: Email body text
            sender: Sender address (optional, may be set by account)
            cc: CC addresses (optional)
            attachments: List of file paths to attach (optional)
            account: Email account to bind (optional)
            folder: If set with account, save as draft in this folder

        Returns:
            The created Email instance
        """
        attachment_list = []
        if attachments:
            for path in attachments:
                attachment_list.append(Attachment.from_path(path))

        email = cls(
            sender=sender,
            recipient=to,
            subject=subject,
            text=text,
            cc=cc,
            attachments=attachment_list,
            account=account,
        )

        if folder and account:
            account.create_draft(email, folder)
            email._folder = folder

        return email
