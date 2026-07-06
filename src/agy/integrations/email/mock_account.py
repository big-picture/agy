"""File-based mock email account using .eml files."""

from __future__ import annotations

import email
import logging
import re
import shutil
import uuid
from email import policy
from email.message import EmailMessage as PythonEmailMessage
from email.message import Message
from pathlib import Path
from typing import TYPE_CHECKING

from .account import EmailAccount
from .email import Attachment, Email

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
_UNREAD_HEADER = "X-AGY-Unread"
_LABELS_HEADER = "X-AGY-Labels"


def _payload_to_text(payload: Message[str, str] | bytes | str | None) -> str:
    """Payload to text.

    Args:
        payload: payload.

    Returns:
        str: Operation result.
    """
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="ignore")
    if isinstance(payload, str):
        return payload
    return ""


def _payload_to_bytes(payload: Message[str, str] | bytes | str | None) -> bytes:
    """Payload to bytes.

    Args:
        payload: payload.

    Returns:
        bytes: Operation result.
    """
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8", errors="ignore")
    return b""


class MockEmailAccount(EmailAccount):
    """
    File-based mock email account.

    Stores emails as .eml files in subdirectories representing folders.
    Directory structure:
        base_path/
            inbox/
                email1.eml
                email2.eml
            sent/
                email3.eml
            drafts/
                email4.eml
    """

    def __init__(
        self, base_path: str | Path, user_email: str = "mock@example.com"
    ) -> None:
        """
        Initialize MockEmailAccount.

        Args:
            base_path: Root directory for email storage
            user_email: Email address for this mock account
        """
        self.base_path = Path(base_path)
        self.user_email = user_email
        self._ensure_folders()

    def _ensure_folders(self) -> None:
        """Ensure default folders exist."""
        default_folders = ["inbox", "sent", "drafts", "trash"]
        for folder in default_folders:
            folder_path = self.base_path / folder
            folder_path.mkdir(parents=True, exist_ok=True)

    def _get_folder_path(self, folder: str) -> Path:
        """Get path for a folder, creating if necessary."""
        folder_path = self.base_path / folder.lower()
        folder_path.mkdir(parents=True, exist_ok=True)
        return folder_path

    def _generate_message_id(self) -> str:
        """Generate a unique message ID."""
        return f"{uuid.uuid4()}@{self.user_email.split('@')[-1]}"

    def _email_to_eml(self, email_obj: Email) -> PythonEmailMessage:
        """Convert Email object to Python EmailMessage (eml format)."""
        msg = PythonEmailMessage()
        msg["From"] = email_obj.sender or self.user_email
        msg["To"] = email_obj.recipient
        msg["Subject"] = email_obj.subject
        msg["Message-ID"] = (
            f"<{email_obj.message_id}>"
            if email_obj.message_id
            else f"<{self._generate_message_id()}>"
        )

        if email_obj.cc:
            msg["Cc"] = email_obj.cc
        if email_obj.reply_to:
            msg["Reply-To"] = email_obj.reply_to

        if email_obj._is_unread is not None:
            msg[_UNREAD_HEADER] = "true" if email_obj._is_unread else "false"
        if email_obj._labels:
            msg[_LABELS_HEADER] = ",".join(email_obj._labels)

        msg.set_content(email_obj.text)

        for att in email_obj.attachments:
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

        return msg

    def _eml_to_email(self, msg: email.message.Message, file_path: Path) -> Email:
        """Convert Python EmailMessage to Email object."""
        subject = msg.get("Subject", "")
        from_addr = msg.get("From", "")
        to_addr = msg.get("To", "")
        cc_addr = msg.get("Cc", "")
        reply_to = msg.get("Reply-To", "")
        message_id = msg.get("Message-ID", "")

        # Extract message_id without angle brackets
        if message_id.startswith("<") and message_id.endswith(">"):
            message_id = message_id[1:-1]

        unread_header = str(msg.get(_UNREAD_HEADER, "")).strip().lower()
        is_unread = None
        if unread_header in {"true", "false"}:
            is_unread = unread_header == "true"
        labels_header = str(msg.get(_LABELS_HEADER, "")).strip()
        labels = [part.strip() for part in labels_header.split(",") if part.strip()]

        # Extract body
        body = ""
        body_type = "text"
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    body = _payload_to_text(part.get_payload(decode=True))
                    break
                elif content_type == "text/html" and not body:
                    body = _payload_to_text(part.get_payload(decode=True))
                    body = re.sub(r"<[^>]+>", "", body)  # Strip HTML
                    body_type = "html"
        else:
            body = _payload_to_text(msg.get_payload(decode=True))

        # Extract attachments
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_disposition() == "attachment":
                    filename = part.get_filename() or "attachment"
                    content = _payload_to_bytes(part.get_payload(decode=True))
                    content_type = part.get_content_type()
                    attachments.append(
                        Attachment(
                            filename=filename,
                            content=content,
                            content_type=content_type,
                        )
                    )

        # Determine folder from path
        folder = file_path.parent.name

        email_obj = Email(
            sender=from_addr,
            recipient=to_addr,
            subject=subject,
            text=body or "",
            cc=cc_addr,
            reply_to=reply_to,
            body_type=body_type,
            message_id=message_id,
            attachments=attachments,
            account=self,
            _is_unread=is_unread,
            _labels=labels,
        )
        email_obj._folder = folder
        return email_obj

    def _save_email(self, email_obj: Email, folder: str) -> str:
        """Save an email to a folder and return the message_id."""
        if not email_obj.message_id:
            email_obj.message_id = self._generate_message_id()

        if email_obj._is_unread is None:
            email_obj._is_unread = folder.lower() not in {"drafts", "sent"}

        msg = self._email_to_eml(email_obj)
        folder_path = self._get_folder_path(folder)

        # Use message_id as filename (sanitized)
        safe_id = re.sub(r"[^\w\-.]", "_", email_obj.message_id)
        file_path = folder_path / f"{safe_id}.eml"

        file_path.write_bytes(msg.as_bytes())
        email_obj._folder = folder
        return email_obj.message_id

    def _find_email_file(self, message_id: str) -> Path | None:
        """Find the .eml file for a message_id."""
        safe_id = re.sub(r"[^\w\-.]", "_", message_id)
        for folder_path in self.base_path.iterdir():
            if folder_path.is_dir():
                file_path = folder_path / f"{safe_id}.eml"
                if file_path.exists():
                    return file_path
        return None

    def _load_email(self, file_path: Path) -> Email | None:
        """Load an email from a .eml file."""
        try:
            with open(file_path, "rb") as f:
                msg = email.message_from_binary_file(f, policy=policy.default)
            return self._eml_to_email(msg, file_path)
        except Exception as exc:
            logger.error("Failed to load email from %s: %s", file_path, exc)
            return None

    def get_emails(
        self,
        *,
        folders: list[str] | None = None,
        max_results: int = 100,
        only_unread: bool = False,
    ) -> list[Email]:
        """Fetch emails from the mock account."""
        target_folders = folders if folders else ["inbox"]
        emails: list[Email] = []

        for folder in target_folders:
            folder_path = self.base_path / folder.lower()
            if not folder_path.exists():
                continue

            for eml_file in folder_path.glob("*.eml"):
                email_obj = self._load_email(eml_file)
                if email_obj and (not only_unread or email_obj._is_unread is not False):
                    emails.append(email_obj)

                if len(emails) >= max_results:
                    break

            if len(emails) >= max_results:
                break

        return emails[:max_results]

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
        # Get all folders if not specified
        if folders:
            target_folders = [f.lower() for f in folders]
        else:
            target_folders = [d.name for d in self.base_path.iterdir() if d.is_dir()]

        matches: list[Email] = []

        for folder in target_folders:
            folder_path = self.base_path / folder
            if not folder_path.exists():
                continue

            for eml_file in folder_path.glob("*.eml"):
                email_obj = self._load_email(eml_file)
                if not email_obj:
                    continue

                # Apply filters
                if email_contains:
                    search_text = email_contains.lower()
                    combined = f"{email_obj.sender} {email_obj.recipient} {email_obj.cc} {email_obj.subject} {email_obj.text}".lower()
                    if search_text not in combined:
                        continue
                else:
                    if (
                        to_contains
                        and to_contains.lower() not in email_obj.recipient.lower()
                    ):
                        continue
                    if (
                        from_contains
                        and from_contains.lower() not in email_obj.sender.lower()
                    ):
                        continue
                    if cc_contains and cc_contains.lower() not in email_obj.cc.lower():
                        continue
                    if (
                        subject_contains
                        and subject_contains.lower() not in email_obj.subject.lower()
                    ):
                        continue
                    if (
                        body_contains
                        and body_contains.lower() not in email_obj.text.lower()
                    ):
                        continue
                    if has_attachments is not None:
                        has_att = len(email_obj.attachments) > 0
                        if has_attachments != has_att:
                            continue

                matches.append(email_obj)
                if len(matches) >= max_results:
                    break

            if len(matches) >= max_results:
                break

        return matches

    def send_email(self, email_obj: Email, *, draft_only: bool = False) -> Email:
        """'Send' an email by saving to sent folder."""
        if self._should_draft_only(draft_only):
            self._log_outgoing_draft_redirect(
                "send",
                draft_only_param=draft_only,
                recipient=email_obj.recipient,
                subject=email_obj.subject,
            )
            email_obj.sender = self.user_email
            email_obj.account = self
            self._save_email(email_obj, "drafts")
            return email_obj
        email_obj.sender = self.user_email
        email_obj.account = self
        self._save_email(email_obj, "sent")
        return email_obj

    def reply_email(
        self,
        email_obj: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list | None = None,
        draft_only: bool = False,
    ) -> Email:
        """Create and 'send' a reply."""
        reply = Email(
            sender=self.user_email,
            recipient=email_obj.sender,
            subject=subject or f"Re: {email_obj.subject}",
            text=f"{text}\n\n--- Original message ---\n{email_obj.text}",
            attachments=list(attachments) if attachments else [],
            account=self,
        )
        if self._should_draft_only(draft_only):
            self._log_outgoing_draft_redirect(
                "reply",
                draft_only_param=draft_only,
                recipient=reply.recipient,
                subject=reply.subject,
            )
            self._save_email(reply, "drafts")
            return reply
        self._save_email(reply, "sent")
        return reply

    def reply_all_email(
        self,
        email_obj: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list | None = None,
        draft_only: bool = False,
    ) -> Email:
        """Create and 'send' a reply-all."""
        all_recipients = ", ".join(filter(None, [email_obj.sender, email_obj.cc]))
        reply = Email(
            sender=self.user_email,
            recipient=all_recipients,
            subject=subject or f"Re: {email_obj.subject}",
            text=f"{text}\n\n--- Original message ---\n{email_obj.text}",
            attachments=list(attachments) if attachments else [],
            account=self,
        )
        if self._should_draft_only(draft_only):
            self._log_outgoing_draft_redirect(
                "reply_all",
                draft_only_param=draft_only,
                recipient=reply.recipient,
                subject=reply.subject,
            )
            self._save_email(reply, "drafts")
            return reply
        self._save_email(reply, "sent")
        return reply

    def forward_email(
        self, email_obj: Email, to: str, *, draft_only: bool = False
    ) -> Email:
        """Create and 'send' a forwarded email."""
        forward = Email(
            sender=self.user_email,
            recipient=to,
            subject=f"FW: {email_obj.subject}",
            text=f"--- Forwarded message ---\n{email_obj.text}",
            attachments=email_obj.attachments.copy(),
            account=self,
        )
        if self._should_draft_only(draft_only):
            self._log_outgoing_draft_redirect(
                "forward",
                draft_only_param=draft_only,
                recipient=forward.recipient,
                subject=forward.subject,
            )
            self._save_email(forward, "drafts")
            return forward
        self._save_email(forward, "sent")
        return forward

    def move_email(self, email_obj: Email, folder: str) -> None:
        """Move an email to a different folder."""
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to move")

        src_file = self._find_email_file(email_obj.message_id)
        if not src_file:
            raise RuntimeError(f"Email with id '{email_obj.message_id}' not found")

        dest_folder = self._get_folder_path(folder)
        dest_file = dest_folder / src_file.name

        shutil.move(str(src_file), str(dest_file))
        email_obj._folder = folder

    def copy_email(self, email_obj: Email, folder: str) -> None:
        """Copy an email to a folder, keeping the original in place."""
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to copy")

        src_file = self._find_email_file(email_obj.message_id)
        if not src_file:
            raise RuntimeError(f"Email with id '{email_obj.message_id}' not found")

        dest_folder = self._get_folder_path(folder)
        dest_file = dest_folder / src_file.name

        shutil.copy2(str(src_file), str(dest_file))

    def delete_email(self, email_obj: Email) -> None:
        """Delete an email (move to trash)."""
        self.move_email(email_obj, "trash")

    def mark_read_email(self, email_obj: Email) -> None:
        """Mark an email as read."""
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to mark read")

        src_file = self._find_email_file(email_obj.message_id)
        if not src_file:
            raise RuntimeError(f"Email with id '{email_obj.message_id}' not found")

        email_obj._is_unread = False
        email_obj._folder = email_obj._folder or src_file.parent.name
        self._save_email(email_obj, email_obj._folder)

    def mark_unread_email(self, email_obj: Email) -> None:
        """Mark an email as unread."""
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to mark unread")

        src_file = self._find_email_file(email_obj.message_id)
        if not src_file:
            raise RuntimeError(f"Email with id '{email_obj.message_id}' not found")

        email_obj._is_unread = True
        email_obj._folder = email_obj._folder or src_file.parent.name
        self._save_email(email_obj, email_obj._folder)

    def add_label_email(self, email_obj: Email, text: str) -> None:
        """Add a mock label to an email and persist it in the .eml file."""
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to add a label")

        src_file = self._find_email_file(email_obj.message_id)
        if not src_file:
            raise RuntimeError(f"Email with id '{email_obj.message_id}' not found")

        if not any(label.lower() == text.lower() for label in email_obj._labels):
            email_obj._labels.append(text)
        email_obj._folder = email_obj._folder or src_file.parent.name
        self._save_email(email_obj, email_obj._folder)

    def has_label_email(self, email_obj: Email, text: str) -> bool:
        """Check whether a mock email has a label."""
        if any(label.lower() == text.lower() for label in email_obj._labels):
            return True
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to check labels")
        src_file = self._find_email_file(email_obj.message_id)
        if not src_file:
            raise RuntimeError(f"Email with id '{email_obj.message_id}' not found")
        loaded = self._load_email(src_file)
        if not loaded:
            return False
        email_obj._labels = loaded._labels
        return any(label.lower() == text.lower() for label in loaded._labels)

    def enrich_email(self, email_obj: Email, content) -> None:
        """Add enrichment content to an email."""
        if not content:
            logger.warning("enrich_email called with no content")
            return

        enrichment_text = (
            content.get("result", str(content))
            if isinstance(content, dict)
            else str(content)
        )

        # Prepend enrichment to body
        email_obj.text = f"[Enrichment]\n{enrichment_text}\n\n{email_obj.text}"

        # Re-save the email
        if email_obj.message_id and email_obj._folder:
            self._save_email(email_obj, email_obj._folder)

    def enrich_email_hidden(self, email_obj: Email, content) -> None:
        """Add hidden enrichment content to an email."""
        raise NotImplementedError(
            "enrich_email_hidden is not supported for MockEmailAccount"
        )

    def create_draft(self, email_obj: Email, folder: str) -> None:
        """Save an email as draft."""
        email_obj.sender = self.user_email
        email_obj.account = self
        self._save_email(email_obj, folder if folder else "drafts")

    def add_email(
        self,
        *,
        folder: str,
        sender: str,
        recipient: str,
        subject: str,
        text: str,
        cc: str = "",
        attachments: list[Attachment] | None = None,
    ) -> Email:
        """
        Add an email to the mock mailbox (useful for test setup).

        Args:
            folder: Target folder
            sender: Sender address
            recipient: Recipient address
            subject: Email subject
            text: Email body
            cc: CC addresses
            attachments: List of attachments

        Returns:
            The created Email object
        """
        email_obj = Email(
            sender=sender,
            recipient=recipient,
            subject=subject,
            text=text,
            cc=cc,
            attachments=attachments or [],
            account=self,
        )
        self._save_email(email_obj, folder)
        return email_obj

    def clear_folder(self, folder: str) -> int:
        """
        Remove all emails from a folder (useful for test cleanup).

        Returns:
            Number of emails deleted
        """
        folder_path = self.base_path / folder.lower()
        if not folder_path.exists():
            return 0

        count = 0
        for eml_file in folder_path.glob("*.eml"):
            eml_file.unlink()
            count += 1
        return count

    def clear_all(self) -> None:
        """Remove all emails from all folders (useful for test cleanup)."""
        for folder_path in self.base_path.iterdir():
            if folder_path.is_dir():
                for eml_file in folder_path.glob("*.eml"):
                    eml_file.unlink()
