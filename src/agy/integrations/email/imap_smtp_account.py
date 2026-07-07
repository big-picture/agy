"""IMAP/SMTP email account implementation."""

from __future__ import annotations

import email
import imaplib
import logging
import os
import smtplib
from email.header import decode_header
from email.message import EmailMessage as PythonEmailMessage
from email.message import Message
from email.utils import parseaddr
from typing import TYPE_CHECKING

from .account import EmailAccount
from .email import Attachment, Email
from .html_utils import plain_to_html

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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


def _decode_header_value(value: str | None) -> str:
    """Decode an email header value."""
    if not value:
        return ""
    decoded_parts = decode_header(value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def _get_email_body(msg: email.message.Message) -> tuple[str, str]:
    """Extract body text and type from an email message."""
    body_text = ""
    body_type = "text"

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                payload = _payload_to_bytes(part.get_payload(decode=True))
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_text = payload.decode(charset, errors="replace")
                    body_type = "text"
                    break
            elif content_type == "text/html" and not body_text:
                payload = _payload_to_bytes(part.get_payload(decode=True))
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_text = payload.decode(charset, errors="replace")
                    body_type = "html"
    else:
        payload = _payload_to_bytes(msg.get_payload(decode=True))
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body_text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                body_type = "html"

    return body_text, body_type


class ImapSmtpEmailAccount(EmailAccount):
    """Email account using IMAP for reading and SMTP for sending."""

    PROVIDER_KEY = "imap"

    def __init__(
        self,
        *,
        imap_host: str | None = None,
        imap_port: int | None = None,
        imap_user: str | None = None,
        imap_password: str | None = None,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        use_ssl: bool = True,
    ) -> None:
        """
        Initialize IMAP/SMTP email account.

        Args:
            imap_host: IMAP server hostname (env: IMAP_HOST)
            imap_port: IMAP server port (env: IMAP_PORT, default: 993)
            imap_user: IMAP username/email (env: IMAP_USER)
            imap_password: IMAP password (env: IMAP_PASSWORD)
            smtp_host: SMTP server hostname (env: SMTP_HOST)
            smtp_port: SMTP server port (env: SMTP_PORT, default: 465)
            smtp_user: SMTP username (env: SMTP_USER, defaults to IMAP_USER)
            smtp_password: SMTP password (env: SMTP_PASSWORD, defaults to IMAP_PASSWORD)
            use_ssl: Use SSL connections (default: True)
        """
        self.imap_host = imap_host or os.getenv("IMAP_HOST")
        self.imap_port = imap_port or int(os.getenv("IMAP_PORT", "993"))
        self.imap_user = imap_user or os.getenv("IMAP_USER")
        self.imap_password = imap_password or os.getenv("IMAP_PASSWORD")

        self.smtp_host = smtp_host or os.getenv("SMTP_HOST")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "465"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER") or self.imap_user
        self.smtp_password = (
            smtp_password or os.getenv("SMTP_PASSWORD") or self.imap_password
        )

        self.use_ssl = use_ssl

        if not self.imap_host:
            raise ValueError("IMAP_HOST is required")
        if not self.imap_user:
            raise ValueError("IMAP_USER is required")
        if not self.imap_password:
            raise ValueError("IMAP_PASSWORD is required")
        if not self.smtp_host:
            raise ValueError("SMTP_HOST is required")

        # Keep strongly typed, validated fields for protocol clients.
        self._imap_host: str = self.imap_host
        self._imap_user: str = self.imap_user
        self._imap_password: str = self.imap_password
        self._smtp_host: str = self.smtp_host
        self._smtp_user: str = self.smtp_user or self._imap_user
        self._smtp_password: str = self.smtp_password or self._imap_password
        self.user_email: str = self._imap_user

    def _connect_imap(self) -> imaplib.IMAP4_SSL | imaplib.IMAP4:
        """Create and authenticate IMAP connection."""
        imap: imaplib.IMAP4_SSL | imaplib.IMAP4
        if self.use_ssl:
            imap = imaplib.IMAP4_SSL(self._imap_host, self.imap_port)
        else:
            imap = imaplib.IMAP4(self._imap_host, self.imap_port)
        imap.login(self._imap_user, self._imap_password)
        return imap

    def _connect_smtp(self) -> smtplib.SMTP_SSL | smtplib.SMTP:
        """Create and authenticate SMTP connection."""
        smtp: smtplib.SMTP_SSL | smtplib.SMTP
        if self.use_ssl:
            smtp = smtplib.SMTP_SSL(self._smtp_host, self.smtp_port)
        else:
            smtp = smtplib.SMTP(self._smtp_host, self.smtp_port)
            smtp.starttls()
        smtp.login(self._smtp_user, self._smtp_password)
        return smtp

    def _imap_message_to_email(
        self, msg: email.message.Message, uid: str, folder: str
    ) -> Email:
        """Convert parsed email message to Email object."""
        from_header = _decode_header_value(msg.get("From"))
        to_header = _decode_header_value(msg.get("To"))
        cc_header = _decode_header_value(msg.get("Cc"))
        reply_to_header = _decode_header_value(msg.get("Reply-To"))
        subject = _decode_header_value(msg.get("Subject"))

        _, sender_email = parseaddr(from_header)
        body_text, body_type = _get_email_body(msg)

        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        filename = _decode_header_value(filename)
                        content = _payload_to_bytes(part.get_payload(decode=True))
                        content_type = part.get_content_type()
                        attachments.append(
                            Attachment(
                                filename=filename,
                                content=content,
                                content_type=content_type,
                            )
                        )

        return Email(
            sender=sender_email or from_header,
            recipient=to_header,
            subject=subject,
            text=body_text,
            cc=cc_header,
            reply_to=reply_to_header,
            body_type=body_type,
            message_id=uid,
            attachments=attachments,
            account=self,
            _folder=folder,
        )

    def get_emails(
        self,
        *,
        folders: list[str] | None = None,
        max_results: int = 100,
        only_unread: bool = False,
    ) -> list[Email]:
        """Fetch emails from IMAP server."""
        folders_to_search = folders or ["INBOX"]
        emails = []

        try:
            imap = self._connect_imap()
            try:
                for folder in folders_to_search:
                    try:
                        status, _ = imap.select(folder, readonly=True)
                        if status != "OK":
                            logger.warning("Could not select folder: %s", folder)
                            continue

                        search_criteria = "UNSEEN" if only_unread else "ALL"
                        status, data = imap.uid("search", None, search_criteria)
                        if status != "OK":
                            continue

                        uids = data[0].split()
                        uids = uids[-max_results:] if len(uids) > max_results else uids

                        for uid in reversed(uids):
                            uid_str = uid.decode()
                            status, msg_data = imap.uid("fetch", uid, "(RFC822)")
                            if status != "OK" or not msg_data or not msg_data[0]:
                                continue

                            raw_email = msg_data[0][1]
                            msg = email.message_from_bytes(raw_email)
                            email_obj = self._imap_message_to_email(
                                msg, uid_str, folder
                            )
                            emails.append(email_obj)

                            if len(emails) >= max_results:
                                break

                    except imaplib.IMAP4.error as e:
                        logger.warning("Error accessing folder %s: %s", folder, e)
                        continue

                    if len(emails) >= max_results:
                        break
            finally:
                imap.logout()

        except Exception as e:
            logger.error("Failed to fetch emails via IMAP: %s", e)

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
        folders_to_search = folders or ["INBOX"]
        emails = []

        search_parts = []
        if from_contains:
            search_parts.append(f'FROM "{from_contains}"')
        if to_contains:
            search_parts.append(f'TO "{to_contains}"')
        if cc_contains:
            search_parts.append(f'CC "{cc_contains}"')
        if subject_contains:
            search_parts.append(f'SUBJECT "{subject_contains}"')
        if body_contains:
            search_parts.append(f'BODY "{body_contains}"')
        if email_contains:
            search_parts.append(f'TEXT "{email_contains}"')

        search_criteria = " ".join(search_parts) if search_parts else "ALL"

        try:
            imap = self._connect_imap()
            try:
                for folder in folders_to_search:
                    try:
                        status, _ = imap.select(folder, readonly=True)
                        if status != "OK":
                            continue

                        status, data = imap.uid("search", None, search_criteria)
                        if status != "OK":
                            continue

                        uids = data[0].split()
                        for uid in reversed(uids):
                            uid_str = uid.decode()
                            status, msg_data = imap.uid("fetch", uid, "(RFC822)")
                            if status != "OK" or not msg_data or not msg_data[0]:
                                continue

                            raw_email = msg_data[0][1]
                            msg = email.message_from_bytes(raw_email)
                            email_obj = self._imap_message_to_email(
                                msg, uid_str, folder
                            )

                            if has_attachments is not None:
                                has_att = len(email_obj.attachments) > 0
                                if has_att != has_attachments:
                                    continue

                            emails.append(email_obj)
                            if len(emails) >= max_results:
                                break

                    except imaplib.IMAP4.error as e:
                        logger.warning("Error searching folder %s: %s", folder, e)
                        continue

                    if len(emails) >= max_results:
                        break
            finally:
                imap.logout()

        except Exception as e:
            logger.error("Failed to search emails via IMAP: %s", e)

        return emails[:max_results]

    def _create_email_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        attachments: list[Attachment] | None = None,
    ) -> PythonEmailMessage:
        """Create a Python EmailMessage for sending."""
        msg = PythonEmailMessage()
        msg["From"] = self.user_email
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        msg.set_content(plain_to_html(body), subtype="html")

        if attachments:
            for att in attachments:
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

    def send_email(self, email_obj: Email, *, draft_only: bool = False) -> Email:
        """Send an email via SMTP."""
        if self._should_draft_only(draft_only):
            self._log_allowlist_bypass_for_draft("send_email")
            self._log_outgoing_draft_redirect(
                "send",
                draft_only_param=draft_only,
                recipient=email_obj.recipient,
                subject=email_obj.subject,
            )
            self.create_draft(email_obj, "Drafts")
            return email_obj

        from .email_safety import get_validator

        is_valid, error_msg = get_validator("imap").validate_forward(email_obj.recipient)
        if not is_valid:
            raise RuntimeError(f"Safety check failed: {error_msg}")

        msg = self._create_email_message(
            to=email_obj.recipient,
            subject=email_obj.subject,
            body=email_obj.text,
            cc=email_obj.cc,
            attachments=email_obj.attachments,
        )

        try:
            smtp = self._connect_smtp()
            try:
                smtp.send_message(msg)
            finally:
                smtp.quit()

            email_obj.sender = self.user_email
            email_obj.account = self
            return email_obj

        except Exception as e:
            logger.error("Failed to send email via SMTP: %s", e)
            raise RuntimeError(f"Failed to send email: {e}")

    def reply_email(
        self,
        email_obj: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list | None = None,
        draft_only: bool = False,
    ) -> Email:
        """Reply to an email."""
        return self._reply(
            email_obj,
            text,
            reply_all=False,
            subject=subject,
            attachments=attachments,
            draft_only=draft_only,
        )

    def reply_all_email(
        self,
        email_obj: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list | None = None,
        draft_only: bool = False,
    ) -> Email:
        """Reply-all to an email."""
        return self._reply(
            email_obj,
            text,
            reply_all=True,
            subject=subject,
            attachments=attachments,
            draft_only=draft_only,
        )

    def _reply(
        self,
        email_obj: Email,
        text: str,
        *,
        reply_all: bool,
        subject: str | None = None,
        attachments: list | None = None,
        draft_only: bool = False,
    ) -> Email:
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to reply")

        should_draft = self._should_draft_only(draft_only)
        op_label = "reply_all" if reply_all else "reply"
        reply_to = email_obj.reply_to or email_obj.sender
        if should_draft:
            self._log_allowlist_bypass_for_draft(f"{op_label}_email")
            self._log_outgoing_draft_redirect(
                op_label,
                draft_only_param=draft_only,
                recipient=reply_to,
                subject=subject or email_obj.subject,
            )
        else:
            from .email_safety import get_validator

            is_valid, error_msg = get_validator("imap").validate_reply(reply_to)
            if not is_valid:
                raise RuntimeError(f"Safety check failed for reply: {error_msg}")

        recipients = reply_to
        if reply_all and email_obj.cc:
            recipients = ", ".join(filter(None, [reply_to, email_obj.cc]))

        original_body = email_obj.text or ""
        full_body = f"{text}\n\n--- Original message ---\n{original_body}"
        resolved_subject = subject or f"Re: {email_obj.subject}"

        att_list = list(attachments) if attachments else []
        msg = self._create_email_message(
            to=recipients,
            subject=resolved_subject,
            body=full_body,
            attachments=att_list if should_draft else None,
        )

        try:
            if should_draft:
                self._append_bytes_to_drafts_folder(msg.as_bytes())
                reply = Email(
                    sender=self.user_email,
                    recipient=recipients,
                    subject=resolved_subject,
                    text=text,
                    attachments=att_list,
                    account=self,
                )
                reply._folder = "Drafts"
                return reply

            smtp = self._connect_smtp()
            try:
                smtp.send_message(msg)
            finally:
                smtp.quit()

            reply = Email(
                sender=self.user_email,
                recipient=recipients,
                subject=resolved_subject,
                text=text,
                attachments=att_list,
                account=self,
            )
            return reply

        except Exception as e:
            logger.error("Failed to send reply via SMTP: %s", e)
            raise RuntimeError(f"Failed to send reply: {e}")

    def forward_email(
        self, email_obj: Email, to: str, *, draft_only: bool = False
    ) -> Email:
        """Forward an email."""
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to forward")

        should_draft = self._should_draft_only(draft_only)
        if should_draft:
            self._log_allowlist_bypass_for_draft("forward_email")
            self._log_outgoing_draft_redirect(
                "forward",
                draft_only_param=draft_only,
                recipient=to,
                subject=f"Fwd: {email_obj.subject}",
            )
        else:
            from .email_safety import get_validator

            is_valid, error_msg = get_validator("imap").validate_forward(to)
            if not is_valid:
                raise RuntimeError(f"Safety check failed for forward: {error_msg}")

        forward_body = "---------- Forwarded message ----------\n"
        forward_body += f"From: {email_obj.sender}\n"
        forward_body += f"Subject: {email_obj.subject}\n\n"
        forward_body += email_obj.text or ""

        msg = self._create_email_message(
            to=to,
            subject=f"Fwd: {email_obj.subject}",
            body=forward_body,
            attachments=email_obj.attachments,
        )

        try:
            if should_draft:
                self._append_bytes_to_drafts_folder(msg.as_bytes())
                forward = Email(
                    sender=self.user_email,
                    recipient=to,
                    subject=f"Fwd: {email_obj.subject}",
                    text=forward_body,
                    account=self,
                )
                forward._folder = "Drafts"
                return forward

            smtp = self._connect_smtp()
            try:
                smtp.send_message(msg)
            finally:
                smtp.quit()

            forward = Email(
                sender=self.user_email,
                recipient=to,
                subject=f"Fwd: {email_obj.subject}",
                text=forward_body,
                account=self,
            )
            return forward

        except Exception as e:
            logger.error("Failed to forward email via SMTP: %s", e)
            raise RuntimeError(f"Failed to forward email: {e}")

    def _append_bytes_to_drafts_folder(self, raw_message: bytes) -> None:
        """Append a raw RFC822 message to the IMAP Drafts folder with \\Draft flag."""
        draft_folder = "Drafts"
        try:
            imap = self._connect_imap()
            try:
                append_result = imap.append(
                    draft_folder,
                    "(\\Draft)",
                    "",
                    raw_message,
                )
                if append_result[0] != "OK":
                    raise RuntimeError(
                        f"Failed to save draft to folder: {draft_folder}"
                    )
            finally:
                imap.logout()
        except Exception as e:
            logger.error("Failed to append draft via IMAP: %s", e)
            raise RuntimeError(f"Failed to create draft: {e}")

    def move_email(self, email_obj: Email, folder: str) -> None:
        """Move an email to a folder via IMAP COPY + delete."""
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to move")

        source_folder = email_obj._folder or "INBOX"

        try:
            imap = self._connect_imap()
            try:
                status, _ = imap.select(source_folder)
                if status != "OK":
                    raise RuntimeError(f"Could not select folder: {source_folder}")

                uid = email_obj.message_id
                status, _ = imap.uid("copy", uid, folder)
                if status != "OK":
                    raise RuntimeError(f"Failed to copy email to folder: {folder}")

                imap.uid("store", uid, "+FLAGS", "(\\Deleted)")
                imap.expunge()

                email_obj._folder = folder

            finally:
                imap.logout()

        except Exception as e:
            logger.error("Failed to move email via IMAP: %s", e)
            raise RuntimeError(f"Failed to move email: {e}")

    def copy_email(self, email_obj: Email, folder: str) -> None:
        """Copy an email to a folder via IMAP COPY, leaving the original in place."""
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to copy")

        source_folder = email_obj._folder or "INBOX"

        try:
            imap = self._connect_imap()
            try:
                status, _ = imap.select(source_folder)
                if status != "OK":
                    raise RuntimeError(f"Could not select folder: {source_folder}")

                uid = email_obj.message_id
                status, _ = imap.uid("copy", uid, folder)
                if status != "OK":
                    raise RuntimeError(f"Failed to copy email to folder: {folder}")

            finally:
                imap.logout()

        except Exception as e:
            logger.error("Failed to copy email via IMAP: %s", e)
            raise RuntimeError(f"Failed to copy email: {e}")

    def delete_email(self, email_obj: Email) -> None:
        """Delete an email (move to Trash or mark deleted)."""
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to delete")

        source_folder = email_obj._folder or "INBOX"

        try:
            imap = self._connect_imap()
            try:
                status, _ = imap.select(source_folder)
                if status != "OK":
                    raise RuntimeError(f"Could not select folder: {source_folder}")

                uid = email_obj.message_id
                imap.uid("store", uid, "+FLAGS", "(\\Deleted)")
                imap.expunge()

            finally:
                imap.logout()

        except Exception as e:
            logger.error("Failed to delete email via IMAP: %s", e)
            raise RuntimeError(f"Failed to delete email: {e}")

    def mark_read_email(self, email_obj: Email) -> None:
        """Mark an email as read by setting the IMAP \\Seen flag."""
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to mark read")

        source_folder = email_obj._folder or "INBOX"

        try:
            imap = self._connect_imap()
            try:
                status, _ = imap.select(source_folder)
                if status != "OK":
                    raise RuntimeError(f"Could not select folder: {source_folder}")

                uid = email_obj.message_id
                status, _ = imap.uid("store", uid, "+FLAGS", "(\\Seen)")
                if status != "OK":
                    raise RuntimeError("Failed to set \\Seen flag")

                email_obj._is_unread = False

            finally:
                imap.logout()

        except Exception as e:
            logger.error("Failed to mark email read via IMAP: %s", e)
            raise RuntimeError(f"Failed to mark email read: {e}")

    def mark_unread_email(self, email_obj: Email) -> None:
        """Mark an email as unread by clearing the IMAP \\Seen flag."""
        if not email_obj.message_id:
            raise ValueError("Email.message_id is required to mark unread")

        source_folder = email_obj._folder or "INBOX"

        try:
            imap = self._connect_imap()
            try:
                status, _ = imap.select(source_folder)
                if status != "OK":
                    raise RuntimeError(f"Could not select folder: {source_folder}")

                uid = email_obj.message_id
                status, _ = imap.uid("store", uid, "-FLAGS", "(\\Seen)")
                if status != "OK":
                    raise RuntimeError("Failed to clear \\Seen flag")

                email_obj._is_unread = True

            finally:
                imap.logout()

        except Exception as e:
            logger.error("Failed to mark email unread via IMAP: %s", e)
            raise RuntimeError(f"Failed to mark email unread: {e}")

    def add_label_email(self, email_obj: Email, text: str) -> None:
        """Add a label/category to an email."""
        del email_obj, text
        raise NotImplementedError(
            "add_label_email is not supported for ImapSmtpEmailAccount"
        )

    def has_label_email(self, email_obj: Email, text: str) -> bool:
        """Check whether an email has a label/category."""
        del email_obj, text
        raise NotImplementedError(
            "has_label_email is not supported for ImapSmtpEmailAccount"
        )

    def enrich_email(self, email_obj: Email, content) -> None:
        """Add enrichment content to an email."""
        raise NotImplementedError(
            "enrich_email is not supported for ImapSmtpEmailAccount (IMAP bodies are immutable)"
        )

    def enrich_email_hidden(self, email_obj: Email, content) -> None:
        """Add hidden enrichment content to an email."""
        raise NotImplementedError(
            "enrich_email_hidden is not supported for ImapSmtpEmailAccount"
        )

    def create_draft(self, email_obj: Email, folder: str) -> None:
        """Save an email as draft via IMAP APPEND."""
        msg = self._create_email_message(
            to=email_obj.recipient,
            subject=email_obj.subject,
            body=email_obj.text,
            cc=email_obj.cc,
            attachments=email_obj.attachments,
        )

        draft_folder = folder or "Drafts"

        try:
            imap = self._connect_imap()
            try:
                append_result = imap.append(
                    draft_folder,
                    "(\\Draft)",
                    "",
                    msg.as_bytes(),
                )
                status = append_result[0]
                if status != "OK":
                    raise RuntimeError(
                        f"Failed to save draft to folder: {draft_folder}"
                    )

                email_obj.sender = self.user_email
                email_obj.account = self
                email_obj._folder = draft_folder

            finally:
                imap.logout()

        except Exception as e:
            logger.error("Failed to create draft via IMAP: %s", e)
            raise RuntimeError(f"Failed to create draft: {e}")
