"""Abstract EmailAccount interface."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .email import Email

logger = logging.getLogger(__name__)


class EmailAccount(ABC):
    """
    Abstract base class for email account implementations.

    Provides unified interface for fetching, searching, and sending emails
    across different providers (Graph, Gmail, Mock/File-based).
    """

    @abstractmethod
    def get_emails(
        self,
        *,
        folders: list[str] | None = None,
        max_results: int = 100,
        only_unread: bool = False,
    ) -> list[Email]:
        """
        Fetch emails from the account.

        Args:
            folders: List of folder names to fetch from. None = inbox.
            max_results: Maximum number of emails to return.
            only_unread: If True, only return unread emails.

        Returns:
            List of Email objects with this account bound.
        """
        ...

    @abstractmethod
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
        """
        Search for emails matching filters.

        Args:
            folders: List of folder names to search. None = all folders.
            max_results: Maximum number of emails to return.
            to_contains: Filter by recipient containing string.
            from_contains: Filter by sender containing string.
            cc_contains: Filter by CC containing string.
            subject_contains: Filter by subject containing string.
            body_contains: Filter by body containing string.
            has_attachments: Filter by presence of attachments.
            email_contains: Search across all fields (to, from, subject, body).

        Returns:
            List of matching Email objects with this account bound.
        """
        ...

    @abstractmethod
    def send_email(self, email: Email, *, draft_only: bool = False) -> Email:
        """
        Send an email.

        Args:
            email: Email object to send.
            draft_only: If True (or EMAIL_DRAFT_ONLY env), save as draft instead of sending.

        Returns:
            sent email.
        """
        ...

    @abstractmethod
    def reply_email(
        self,
        email: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list | None = None,
        draft_only: bool = False,
    ) -> Email:
        """
        Reply to an email (sender only).

        Args:
            email: original email to reply to.
            text: Reply message text.
            subject: Override the reply subject (default: keeps original).
            attachments: List of Attachment objects to include in the reply.
            draft_only: If True (or EMAIL_DRAFT_ONLY env), save as draft instead of sending.

        Returns:
            sent reply email.
        """
        ...

    @abstractmethod
    def reply_all_email(
        self,
        email: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list | None = None,
        draft_only: bool = False,
    ) -> Email:
        """
        Reply-all to an email (all original recipients).

        Args:
            email: original email to reply to.
            text: Reply message text.
            subject: Override the reply subject (default: keeps original).
            attachments: List of Attachment objects to include in the reply.
            draft_only: If True (or EMAIL_DRAFT_ONLY env), save as draft instead of sending.

        Returns:
            sent reply email.
        """
        ...

    @abstractmethod
    def forward_email(
        self, email: Email, to: str, *, draft_only: bool = False
    ) -> Email:
        """
        Forward an email.

        Args:
            email: email to forward.
            to: Recipient address.
            draft_only: If True (or EMAIL_DRAFT_ONLY env), save as draft instead of sending.

        Returns:
            sent forwarded email.
        """
        ...

    @abstractmethod
    def move_email(self, email: Email, folder: str) -> None:
        """
        Move an email to a folder.

        Args:
            email: email to move.
            folder: Target folder name.
        """
        ...

    @abstractmethod
    def copy_email(self, email: Email, folder: str) -> None:
        """
        Copy an email to a folder, keeping the original in place.

        Args:
            email: email to copy.
            folder: Target folder name.
        """
        ...

    @abstractmethod
    def delete_email(self, email: Email) -> None:
        """
        Delete an email.

        Args:
            email: email to delete.
        """
        ...

    @abstractmethod
    def mark_read_email(self, email: Email) -> None:
        """
        Mark an email as read.

        Args:
            email: email to mark as read.
        """
        ...

    @abstractmethod
    def mark_unread_email(self, email: Email) -> None:
        """
        Mark an email as unread.

        Args:
            email: email to mark as unread.
        """
        ...

    @abstractmethod
    def add_label_email(self, email: Email, text: str) -> None:
        """
        Add a label/category to an email.

        Args:
            email: email to label.
            text: Label/category name.
        """
        ...

    @abstractmethod
    def has_label_email(self, email: Email, text: str) -> bool:
        """
        Check whether an email has a label/category.

        Args:
            email: email to inspect.
            text: Label/category name to check.
        """
        ...

    @abstractmethod
    def enrich_email(self, email: Email, content) -> None:
        """
        Add visible content/annotation to an email.

        Args:
            email: email to enrich.
            content: Content to add (string or dict).
        """
        ...

    @abstractmethod
    def enrich_email_hidden(self, email: Email, content) -> None:
        """
        Add hidden content/annotation to an email.

        Args:
            email: email to enrich.
            content: Hidden content to add.
        """
        ...

    @abstractmethod
    def create_draft(self, email: Email, folder: str) -> None:
        """
        Save an email as draft in a folder.

        Args:
            email: email to save.
            folder: Target folder name.
        """
        ...

    def fetch_attachments(self, email: Email) -> None:
        """
        Fetch and populate email.attachments if not already loaded.

        Default no-op. Override in account implementations that support
        lazy-loading attachments (e.g. GraphEmailAccount).
        """
        pass

    def _bind_account(self, email: Email) -> Email:
        """Helper to bind this account to an email."""
        email.account = self
        return email

    def _should_draft_only(self, draft_only: bool) -> bool:
        """Return True if the operation should save to drafts instead of sending."""
        if draft_only:
            logger.info("Draft-only mode enabled by call parameter (draft_only=True)")
            return True
        env_raw = os.getenv("EMAIL_DRAFT_ONLY", "")
        env_enabled = env_raw.strip().lower() in ("true", "1", "yes")
        if env_enabled:
            logger.info(
                "Draft-only mode enabled by EMAIL_DRAFT_ONLY=%r",
                env_raw,
            )
        return env_enabled

    def _log_outgoing_draft_redirect(
        self,
        operation: str,
        *,
        draft_only_param: bool,
        recipient: str,
        subject: str | None = None,
    ) -> None:
        """Log that an outgoing operation is being saved as draft instead of sent."""
        from_env = os.getenv("EMAIL_DRAFT_ONLY", "").strip().lower() in (
            "true",
            "1",
            "yes",
        )
        if draft_only_param:
            reason = "draft_only=True"
        elif from_env:
            reason = "EMAIL_DRAFT_ONLY"
        else:
            return
        logger.info(
            "Outgoing email redirected to drafts: operation=%s reason=%s "
            "recipient=%s subject=%r",
            operation,
            reason,
            recipient,
            subject,
        )

    def _log_allowlist_bypass_for_draft(self, operation: str) -> None:
        """Log that outbound allowlist checks were skipped because only a draft is created."""
        logger.info(
            "Skipping ALLOWED_EMAIL_* safety check for %s because draft-only mode "
            "is active (no outbound send)",
            operation,
        )
