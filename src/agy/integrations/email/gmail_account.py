"""Gmail email account implementation."""

from __future__ import annotations

import base64
import logging
import re
from email.message import EmailMessage as PythonEmailMessage
from typing import TYPE_CHECKING, Any

from ._gmail_api import GmailAPI
from .account import EmailAccount
from .email import Email
from .html_utils import plain_to_html

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class GmailEmailAccount(EmailAccount):
    """Gmail-backed email account using OAuth user credentials."""

    PROVIDER_KEY = "gmail"

    def __init__(self, api: GmailAPI | None = None) -> None:
        """
        Initialize GmailEmailAccount.

        Args:
            api: GmailAPI instance (optional, creates one if not provided)
        """
        self.api = api or GmailAPI()
        self.user_email = self.api._user

    def _gmail_message_to_email(self, message: dict) -> Email:
        """Convert Gmail API message to Email object."""
        headers = {
            h["name"].lower(): h["value"]
            for h in message.get("payload", {}).get("headers", [])
        }

        from_addr = headers.get("from", "")
        to_addresses = [
            addr.strip() for addr in headers.get("to", "").split(",") if addr.strip()
        ]
        cc_addresses = [
            addr.strip() for addr in headers.get("cc", "").split(",") if addr.strip()
        ]
        reply_to = headers.get("reply-to", "")
        subject = headers.get("subject", "")

        body_text = self.api._extract_body(message.get("payload", {}))
        body_type = message.get("payload", {}).get("mimeType", "")
        if body_type and "text/html" in body_type.lower():
            body_type = "html"
            body_text_clean = re.sub(r"<[^>]+>", "", body_text)
        else:
            body_type = "text"
            body_text_clean = body_text

        email = Email(
            sender=from_addr,
            recipient=", ".join(to_addresses),
            subject=subject,
            text=body_text_clean,
            cc=", ".join(cc_addresses),
            reply_to=reply_to,
            body_type=body_type,
            message_id=message.get("id"),
            account=self,
            _is_unread="UNREAD" in message.get("labelIds", []),
        )
        return email

    def get_emails(
        self,
        *,
        folders: list[str] | None = None,
        max_results: int = 100,
        only_unread: bool = False,
    ) -> list[Email]:
        """Fetch emails from Gmail."""
        # Build query - Gmail uses labels/queries, not folders
        query_parts = []
        if folders:
            label_query = " OR ".join([f"label:{f}" for f in folders])
            query_parts.append(f"({label_query})")
        else:
            query_parts.append("in:inbox")

        if only_unread:
            query_parts.append("is:unread")

        query = " ".join(query_parts)

        try:
            response = (
                self.api._service.users()
                .messages()
                .list(
                    userId=self.api._user,
                    q=query,
                    maxResults=max_results,
                )
                .execute()
            )
            message_ids = [msg["id"] for msg in response.get("messages", [])]
        except Exception as exc:
            logger.error("Failed to list Gmail messages: %s", exc)
            return []

        emails = []
        for mid in message_ids[:max_results]:
            message = self.api.get_message(mid)
            if message:
                email = self._gmail_message_to_email(message)
                emails.append(email)

        return emails

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
        """Search for emails matching filters."""
        query_parts = []

        if folders:
            label_query = " OR ".join([f"label:{f}" for f in folders])
            query_parts.append(f"({label_query})")

        if email_contains:
            query_parts.append(email_contains)
        else:
            if from_contains:
                query_parts.append(f"from:{from_contains}")
            if to_contains:
                query_parts.append(f"to:{to_contains}")
            if cc_contains:
                query_parts.append(f"cc:{cc_contains}")
            if subject_contains:
                query_parts.append(f"subject:{subject_contains}")
            if body_contains:
                query_parts.append(body_contains)

        # has_attachments can be combined with any search
        if has_attachments is True:
            query_parts.append("has:attachment")
        elif has_attachments is False:
            query_parts.append("-has:attachment")

        query = " ".join(query_parts) if query_parts else "in:inbox"

        try:
            response = (
                self.api._service.users()
                .messages()
                .list(
                    userId=self.api._user,
                    q=query,
                    maxResults=max_results,
                )
                .execute()
            )
            message_ids = [msg["id"] for msg in response.get("messages", [])]
        except Exception as exc:
            logger.error("Failed to search Gmail messages: %s", exc)
            return []

        emails = []
        for mid in message_ids[:max_results]:
            message = self.api.get_message(mid)
            if message:
                email = self._gmail_message_to_email(message)
                emails.append(email)

        return emails

    def send_email(self, email: Email, *, draft_only: bool = False) -> Email:
        """Send an email via Gmail."""
        if self._should_draft_only(draft_only):
            self._log_allowlist_bypass_for_draft("send_email")
            self._log_outgoing_draft_redirect(
                "send",
                draft_only_param=draft_only,
                recipient=email.recipient,
                subject=email.subject,
            )
            self.create_draft(email, "")
            return email

        from .email_safety import get_validator

        is_valid, error_msg = get_validator("gmail").validate_forward(email.recipient)
        if not is_valid:
            raise RuntimeError(f"Safety check failed: {error_msg}")

        msg = PythonEmailMessage()
        msg["To"] = email.recipient
        msg["Subject"] = email.subject
        if email.cc:
            msg["Cc"] = email.cc
        msg.set_content(plain_to_html(email.text), subtype="html")

        # Handle attachments
        for att in email.attachments:
            maintype, subtype = (
                att.content_type.split("/", 1)
                if "/" in att.content_type
                else ("application", "octet-stream")
            )
            msg.add_attachment(
                att.content,
                maintype=maintype,
                subtype=subtype,
                filename=att.filename,
            )

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        body: dict[str, Any] = {"raw": raw}

        try:
            sent = (
                self.api._service.users()
                .messages()
                .send(userId=self.api._user, body=body)
                .execute()
            )
            email.message_id = sent.get("id")
            email.sender = self.user_email
            email.account = self
            return email
        except Exception as exc:
            logger.error("Failed to send Gmail message: %s", exc)
            raise RuntimeError(f"Failed to send email: {exc}")

    def reply_email(
        self,
        email: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list | None = None,
        draft_only: bool = False,
    ) -> Email:
        """Reply to an email."""
        return self._reply(
            email, text, subject=subject, attachments=attachments, draft_only=draft_only
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
        """Reply-all to an email (Gmail: same as reply, CC preserved by API)."""
        return self._reply(
            email, text, subject=subject, attachments=attachments, draft_only=draft_only
        )

    def _reply(
        self,
        email: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list | None = None,
        draft_only: bool = False,
    ) -> Email:
        if not email.message_id:
            raise ValueError("Email.message_id is required to reply")

        should_draft = self._should_draft_only(draft_only)
        if should_draft:
            self._log_allowlist_bypass_for_draft("reply_email")
            self._log_outgoing_draft_redirect(
                "reply",
                draft_only_param=draft_only,
                recipient=email.sender or email.reply_to or "",
                subject=subject or email.subject,
            )
        else:
            from .email_safety import get_validator

            is_valid, error_msg = get_validator("gmail").validate_reply(
                email.sender or email.reply_to
            )
            if not is_valid:
                raise RuntimeError(f"Safety check failed for reply: {error_msg}")

        original_raw = email.text or ""
        full_html = f"{plain_to_html(text)}<br/><br/>--- Original message ---<br/>{plain_to_html(original_raw)}"

        reply_id = self.api.create_reply_message(
            message_id=email.message_id,
            reply_text=full_html,
            send=not should_draft,
        )
        if not reply_id:
            raise RuntimeError("Failed to send Gmail reply")

        resolved_subject = subject or f"Re: {email.subject}"
        result = Email(
            sender=self.user_email,
            recipient=email.sender or "",
            subject=resolved_subject,
            text=text,
            message_id=reply_id,
            account=self,
        )
        return result

    def forward_email(
        self, email: Email, to: str, *, draft_only: bool = False
    ) -> Email:
        """Forward an email."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to forward")

        should_draft = self._should_draft_only(draft_only)
        if should_draft:
            self._log_allowlist_bypass_for_draft("forward_email")
            self._log_outgoing_draft_redirect(
                "forward",
                draft_only_param=draft_only,
                recipient=to,
                subject=f"FW: {email.subject}",
            )
        else:
            from .email_safety import get_validator

            is_valid, error_msg = get_validator("gmail").validate_forward(to)
            if not is_valid:
                raise RuntimeError(f"Safety check failed for forward: {error_msg}")

        forward_id = self.api.forward_message(
            message_id=email.message_id,
            forward_to=to,
            send=not should_draft,
        )
        if not forward_id:
            raise RuntimeError(f"Failed to forward email to {to}")

        forward_email = Email(
            sender=self.user_email,
            recipient=to,
            subject=f"FW: {email.subject}",
            text=email.text or "",
            message_id=forward_id,
            account=self,
        )
        return forward_email

    def move_email(self, email: Email, folder: str) -> None:
        """Move an email to a folder (Gmail label)."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to move")

        success = self.api.move_message(
            message_id=email.message_id,
            destination_label=folder,
        )
        if not success:
            raise RuntimeError(f"Failed to move email to label '{folder}'")

    def copy_email(self, email: Email, folder: str) -> None:
        """Copy an email to a label, keeping it in its current labels."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to copy")

        label_id = self.api.get_label_id_by_name(folder, create_if_missing=True)
        if not label_id:
            raise RuntimeError(f"Failed to resolve Gmail label '{folder}'")

        try:
            self.api._service.users().messages().modify(
                userId=self.api._user,
                id=email.message_id,
                body={"addLabelIds": [label_id]},
            ).execute()
        except Exception as exc:
            logger.error("Failed to copy Gmail message to label %s: %s", folder, exc)
            raise RuntimeError(f"Failed to copy email to label '{folder}': {exc}")

    def delete_email(self, email: Email) -> None:
        """Delete an email (move to trash)."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to delete")

        try:
            self.api._service.users().messages().trash(
                userId=self.api._user,
                id=email.message_id,
            ).execute()
        except Exception as exc:
            logger.error("Failed to delete Gmail message: %s", exc)
            raise RuntimeError(f"Failed to delete email: {exc}")

    def mark_read_email(self, email: Email) -> None:
        """Mark an email as read."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to mark read")

        try:
            self.api._service.users().messages().modify(
                userId=self.api._user,
                id=email.message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            email._is_unread = False
        except Exception as exc:
            logger.error("Failed to mark Gmail message read: %s", exc)
            raise RuntimeError(f"Failed to mark email read: {exc}")

    def mark_unread_email(self, email: Email) -> None:
        """Mark an email as unread."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to mark unread")

        try:
            self.api._service.users().messages().modify(
                userId=self.api._user,
                id=email.message_id,
                body={"addLabelIds": ["UNREAD"]},
            ).execute()
            email._is_unread = True
        except Exception as exc:
            logger.error("Failed to mark Gmail message unread: %s", exc)
            raise RuntimeError(f"Failed to mark email unread: {exc}")

    def add_label_email(self, email: Email, text: str) -> None:
        """Add a Gmail label to an email."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to add a label")

        label_id = self.api.get_label_id_by_name(text, create_if_missing=True)
        if not label_id:
            raise RuntimeError(f"Failed to resolve Gmail label {text!r}")

        try:
            self.api._service.users().messages().modify(
                userId=self.api._user,
                id=email.message_id,
                body={"addLabelIds": [label_id]},
            ).execute()
            if text not in email._labels:
                email._labels.append(text)
        except Exception as exc:
            logger.error("Failed to add Gmail label %s: %s", text, exc)
            raise RuntimeError(f"Failed to add Gmail label: {exc}")

    def has_label_email(self, email: Email, text: str) -> bool:
        """Check whether a Gmail email has a specific label."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to check labels")

        if any(label.lower() == text.lower() for label in email._labels):
            return True

        label_id = self.api.get_label_id_by_name(text, create_if_missing=False)
        if not label_id:
            return False

        message = self.api.get_message(email.message_id)
        if not message:
            return False

        label_ids = message.get("labelIds", [])
        has_label = isinstance(label_ids, list) and label_id in label_ids
        if has_label and text not in email._labels:
            email._labels.append(text)
        return has_label

    def enrich_email(self, email: Email, content) -> None:
        """Add enrichment content to an email."""
        raise NotImplementedError(
            "enrich_email is not supported for GmailEmailAccount (Gmail bodies are immutable)"
        )

    def enrich_email_hidden(self, email: Email, content) -> None:
        """Add hidden enrichment content to an email."""
        raise NotImplementedError(
            "enrich_email_hidden is not supported for GmailEmailAccount"
        )

    def create_draft(self, email: Email, folder: str) -> None:
        """Create a draft email in Gmail."""
        msg = PythonEmailMessage()
        msg["To"] = email.recipient
        msg["Subject"] = email.subject
        if email.cc:
            msg["Cc"] = email.cc
        msg.set_content(plain_to_html(email.text), subtype="html")

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        body: dict[str, Any] = {"message": {"raw": raw}}

        # Add label if specified
        if folder:
            label_id = self.api.get_label_id_by_name(folder, create_if_missing=True)
            if label_id:
                body["message"]["labelIds"] = [label_id]

        try:
            draft = (
                self.api._service.users()
                .drafts()
                .create(userId=self.api._user, body=body)
                .execute()
            )
            email.message_id = draft.get("message", {}).get("id")
            email.account = self
        except Exception as exc:
            logger.error("Failed to create Gmail draft: %s", exc)
            raise RuntimeError(f"Failed to create draft: {exc}")
