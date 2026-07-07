"""Microsoft Graph email account implementation."""

from __future__ import annotations

import base64
import logging
import re
from html import escape
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests

from ._graph_api import GraphAPI
from .account import EmailAccount
from .email import Attachment, Email
from .env_config import env_for
from .html_utils import plain_to_html

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    """As dict.

    Args:
        value: value.

    Returns:
        dict[str, Any]: Operation result.
    """
    return value if isinstance(value, dict) else {}


def _as_str(value: Any, default: str = "") -> str:
    """As str.

    Args:
        value: value.
        default: default.

    Returns:
        str: Operation result.
    """
    return value if isinstance(value, str) else default


def _as_str_list(value: Any) -> list[str]:
    """As list of strings."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


class GraphEmailAccount(EmailAccount):
    """Microsoft Graph-backed email account."""

    PROVIDER_KEY = "graph"

    GRAPH_ROOT = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        *,
        api: GraphAPI | None = None,
        user_email: str | None = None,
        mailbox_type: str = "personal",
    ) -> None:
        """
        Initialize GraphEmailAccount.

        Args:
            api: GraphAPI instance (optional, creates one if not provided)
            user_email: User principal name (email) for the mailbox
            mailbox_type: "personal" or "shared"
        """
        self.api = api or GraphAPI()
        resolved_user_email = (
            user_email
            or env_for("graph", "USER_EMAIL")
            or env_for("graph", "SHARED_MAILBOX_UPN")
            or self.api._mailbox_upn
        )
        self.mailbox_type = mailbox_type

        if not resolved_user_email:
            raise ValueError(
                "Missing user_email. Set GRAPH_USER_EMAIL or GRAPH_SHARED_MAILBOX_UPN "
                "in env (or deprecated USER_EMAIL / SHARED_MAILBOX_UPN)."
            )
        self.user_email: str = resolved_user_email

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for Graph API requests."""
        return self.api._get_headers()

    def _message_url_base(self, folder_id: str | None = None) -> str:
        """Get base URL for messages endpoint."""
        if folder_id:
            return f"{self.GRAPH_ROOT}/users/{self.user_email}/mailFolders/{folder_id}/messages"
        return f"{self.GRAPH_ROOT}/users/{self.user_email}/messages"

    def _graph_message_to_email(self, msg: dict) -> Email:
        """Convert Graph API message dict to Email object."""
        from_addr = ""
        if msg.get("from"):
            from_addr = msg["from"].get("emailAddress", {}).get("address", "")

        to_addresses = []
        if msg.get("toRecipients"):
            to_addresses = [
                r.get("emailAddress", {}).get("address", "")
                for r in msg["toRecipients"]
            ]

        cc_addresses = []
        if msg.get("ccRecipients"):
            cc_addresses = [
                r.get("emailAddress", {}).get("address", "")
                for r in msg["ccRecipients"]
            ]

        reply_to = ""
        if msg.get("replyTo") and msg["replyTo"]:
            reply_to = msg["replyTo"][0].get("emailAddress", {}).get("address", "")

        body_text = ""
        body_type = ""
        if msg.get("body"):
            body_content = msg["body"].get("content", "")
            body_type = msg["body"].get("contentType", "")
            if body_type == "html":
                body_text = re.sub(r"<[^>]+>", "", body_content)
            else:
                body_text = body_content

        email = Email(
            sender=from_addr,
            recipient=", ".join(to_addresses),
            subject=msg.get("subject", ""),
            text=body_text,
            cc=", ".join(cc_addresses),
            reply_to=reply_to,
            body_type=body_type,
            message_id=msg.get("id"),
            account=self,
            _is_unread=not bool(msg.get("isRead", False)),
            _labels=_as_str_list(msg.get("categories")),
        )
        return email

    def get_emails(
        self,
        *,
        folders: list[str] | None = None,
        max_results: int = 100,
        only_unread: bool = False,
    ) -> list[Email]:
        """Fetch emails from the account."""
        headers = self._get_headers()
        folder_list: list[str | None]
        if folders:
            folder_list = list(folders)
        else:
            folder_list = [None]  # None = inbox
        emails: list[Email] = []

        for folder in folder_list:
            folder_id = None
            if folder:
                folder_id = self.api.get_folder_id_by_name(
                    folder_name=folder,
                    mailbox_type=self.mailbox_type,
                    mailbox_upn=self.user_email,
                )
                if not folder_id:
                    logger.warning("Folder '%s' not found, skipping", folder)
                    continue

            base_url = self._message_url_base(folder_id)
            select_fields = (
                "id,subject,from,toRecipients,ccRecipients,replyTo,body,isRead,categories"
            )
            url = f"{base_url}?$select={select_fields}&$orderby=receivedDateTime desc&$top={max_results}"

            if only_unread:
                url += "&$filter=isRead eq false"

            try:
                resp = requests.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
                data = _as_dict(resp.json())
                messages = data.get("value", [])

                for msg in messages:
                    email = self._graph_message_to_email(msg)
                    email._folder = folder
                    emails.append(email)

            except requests.exceptions.RequestException as exc:
                logger.error("Failed to fetch from folder '%s': %s", folder, exc)
                continue

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
        headers = self._get_headers()

        # Build OData filter
        filters: list[str] = []

        if email_contains:
            # General search across all fields
            search_param = f'$search="{email_contains}"'
        else:
            search_param = None
            if from_contains:
                filters.append(
                    f"contains(from/emailAddress/address, '{from_contains}')"
                )
            if subject_contains:
                filters.append(f"contains(subject, '{subject_contains}')")
            if has_attachments is not None:
                filters.append(f"hasAttachments eq {str(has_attachments).lower()}")

        folder_list: list[str | None]
        if folders:
            folder_list = list(folders)
        else:
            folder_list = [None]
        emails: list[Email] = []

        for folder in folder_list:
            folder_id = None
            if folder:
                folder_id = self.api.get_folder_id_by_name(
                    folder_name=folder,
                    mailbox_type=self.mailbox_type,
                    mailbox_upn=self.user_email,
                )
                if not folder_id:
                    continue

            base_url = self._message_url_base(folder_id)
            select_fields = "id,subject,from,toRecipients,ccRecipients,replyTo,body,isRead,hasAttachments,categories"
            url = f"{base_url}?$select={select_fields}&$top={max_results}"

            if search_param:
                url += f"&{search_param}"
            elif filters:
                url += f"&$filter={' and '.join(filters)}"

            try:
                resp = requests.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
                data = _as_dict(resp.json())
                messages = data.get("value", [])

                for msg in messages:
                    # Client-side filtering for has_attachments when using $search
                    if has_attachments is not None and search_param:
                        msg_has_att = msg.get("hasAttachments", False)
                        if msg_has_att != has_attachments:
                            continue

                    email = self._graph_message_to_email(msg)
                    email._folder = folder

                    # Client-side filtering for fields Graph doesn't support
                    if (
                        to_contains
                        and to_contains.lower() not in email.recipient.lower()
                    ):
                        continue
                    if cc_contains and cc_contains.lower() not in email.cc.lower():
                        continue
                    if (
                        body_contains
                        and body_contains.lower() not in email.text.lower()
                    ):
                        continue

                    emails.append(email)

            except requests.exceptions.RequestException as exc:
                logger.error("Failed to search folder '%s': %s", folder, exc)
                continue

        return emails[:max_results]

    def send_email(self, email: Email, *, draft_only: bool = False) -> Email:
        """Send an email via Microsoft Graph."""
        if self._should_draft_only(draft_only):
            self._log_allowlist_bypass_for_draft("send_email")
            self._log_outgoing_draft_redirect(
                "send",
                draft_only_param=draft_only,
                recipient=email.recipient,
                subject=email.subject,
            )
            self.create_draft(email, "drafts")
            return email

        from .email_safety import get_validator

        is_valid, error_msg = get_validator("graph").validate_forward(email.recipient)
        if not is_valid:
            raise RuntimeError(f"Safety check failed: {error_msg}")

        headers = self._get_headers()
        url = f"{self.GRAPH_ROOT}/users/{self.user_email}/sendMail"

        to_recipients = [
            {"emailAddress": {"address": addr.strip()}}
            for addr in email.recipient.split(",")
            if addr.strip()
        ]

        cc_recipients = []
        if email.cc:
            cc_recipients = [
                {"emailAddress": {"address": addr.strip()}}
                for addr in email.cc.split(",")
                if addr.strip()
            ]

        message: dict[str, Any] = {
            "subject": email.subject,
            "body": {
                "contentType": "HTML",
                "content": plain_to_html(email.text),
            },
            "toRecipients": to_recipients,
            "ccRecipients": cc_recipients,
        }

        # Add attachments
        if email.attachments:
            attachments_payload: list[dict[str, str]] = []
            for att in email.attachments:
                attachments_payload.append(
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": att.filename,
                        "contentBytes": base64.b64encode(att.content).decode("utf-8"),
                        "contentType": att.content_type,
                    }
                )
            message["attachments"] = attachments_payload

        payload = {"message": message, "saveToSentItems": "true"}

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 202:
                email.sender = self.user_email
                email.account = self
                return email
            else:
                logger.error(
                    "Failed to send email: HTTP %s: %s",
                    resp.status_code,
                    resp.text[:500],
                )
                raise RuntimeError(f"Failed to send email: HTTP {resp.status_code}")
        except requests.exceptions.RequestException as exc:
            logger.error("Send email request failed: %s", exc)
            raise RuntimeError(f"Failed to send email: {exc}")

    def fetch_attachments(self, email: Email) -> None:
        """
        Fetch attachment content from Microsoft Graph and populate email.attachments.

        get_emails() and find_emails() do not load attachment content by default.
        Call this when attachments are needed (e.g. before forwarding or including
        in a new email).
        """
        if not email.message_id:
            return
        if email.attachments:
            return
        headers = self._get_headers()
        base = f"{self.GRAPH_ROOT}/users/{self.user_email}/messages/{email.message_id}"
        list_url = f"{base}/attachments"
        try:
            resp = requests.get(list_url, headers=headers, timeout=30)
            if resp.status_code != 200:
                return
            data = resp.json() if resp.text else {}
            items = data.get("value") or []
        except Exception:
            return
        for item in items:
            odata_type = item.get("@odata.type", "")
            if odata_type != "#microsoft.graph.fileAttachment":
                continue
            att_id = item.get("id")
            name = item.get("name") or "attachment"
            content_type = item.get("contentType") or "application/octet-stream"
            content_bytes = item.get("contentBytes")
            if content_bytes is None and att_id:
                content_url = f"{base}/attachments/{att_id}/$value"
                try:
                    cr = requests.get(content_url, headers=headers, timeout=30)
                    if cr.status_code == 200:
                        content_bytes = cr.content
                except Exception:
                    continue
            if content_bytes is not None:
                if isinstance(content_bytes, str):
                    content_bytes = base64.b64decode(content_bytes)
                email.attachments.append(
                    Attachment(
                        filename=name,
                        content=content_bytes,
                        content_type=content_type,
                    )
                )

    def reply_email(
        self,
        email: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list[Attachment] | None = None,
        draft_only: bool = False,
    ) -> Email:
        """Reply to the sender of an email."""
        return self._reply(
            email,
            text,
            reply_all=False,
            subject=subject,
            attachments=attachments,
            draft_only=draft_only,
        )

    def reply_all_email(
        self,
        email: Email,
        text: str,
        *,
        subject: str | None = None,
        attachments: list[Attachment] | None = None,
        draft_only: bool = False,
    ) -> Email:
        """Reply to all recipients of an email."""
        return self._reply(
            email,
            text,
            reply_all=True,
            subject=subject,
            attachments=attachments,
            draft_only=draft_only,
        )

    def _reply(
        self,
        email: Email,
        text: str,
        *,
        reply_all: bool,
        subject: str | None = None,
        attachments: list[Attachment] | None = None,
        draft_only: bool = False,
    ) -> Email:
        if not email.message_id:
            raise ValueError("Email.message_id is required to reply")

        op_label = "reply_all" if reply_all else "reply"
        should_draft = self._should_draft_only(draft_only)
        if should_draft:
            self._log_allowlist_bypass_for_draft(f"{op_label}_email")
            self._log_outgoing_draft_redirect(
                op_label,
                draft_only_param=draft_only,
                recipient=email.sender or email.reply_to or "",
                subject=subject or email.subject,
            )
        else:
            from .email_safety import get_validator

            is_valid, error_msg = get_validator("graph").validate_reply(
                email.sender or email.reply_to
            )
            if not is_valid:
                raise RuntimeError(f"Safety check failed for reply: {error_msg}")

        original_raw = email.text or ""
        full_html = f"{plain_to_html(text)}<br/><br/>--- Original message ---<br/>{plain_to_html(original_raw)}"

        graph_attachments: list[dict[str, str]] | None = None
        if attachments:
            graph_attachments = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": att.filename,
                    "contentBytes": base64.b64encode(att.content).decode("utf-8"),
                    "contentType": att.content_type,
                }
                for att in attachments
            ]

        api_method = (
            self.api.create_reply_all_message
            if reply_all
            else self.api.create_reply_message
        )
        reply_id = api_method(
            message_id=email.message_id,
            reply_text=full_html,
            subject=subject,
            attachments=graph_attachments,
            mailbox_type=self.mailbox_type,
            mailbox_upn=self.user_email,
            send=not should_draft,
        )
        if not reply_id:
            raise RuntimeError("Failed to send reply")

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

            is_valid, error_msg = get_validator("graph").validate_forward(to)
            if not is_valid:
                raise RuntimeError(f"Safety check failed for forward: {error_msg}")

        forward_id = self.api.forward_message(
            message_id=email.message_id,
            forward_to=to,
            mailbox_type=self.mailbox_type,
            mailbox_upn=self.user_email,
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
        """Move an email to a folder."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to move")

        folder_id = self.api.get_folder_id_by_name(
            folder_name=folder,
            mailbox_type=self.mailbox_type,
            mailbox_upn=self.user_email,
        )
        if not folder_id:
            raise RuntimeError(f"Folder '{folder}' not found")

        moved_message = self.api.move_message(
            message_id=email.message_id,
            destination_folder_id=folder_id,
            mailbox_type=self.mailbox_type,
            mailbox_upn=self.user_email,
        )
        if not moved_message:
            raise RuntimeError(f"Failed to move email to folder '{folder}'")

        new_message_id = _as_str(moved_message.get("id")) if moved_message else ""
        if not new_message_id:
            raise RuntimeError(
                "Graph move response did not include the moved message id"
            )

        email.message_id = new_message_id
        if "isRead" in moved_message:
            email._is_unread = not bool(moved_message.get("isRead"))

    def copy_email(self, email: Email, folder: str) -> None:
        """Copy an email to a folder, leaving the original in place."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to copy")

        folder_id = self.api.get_folder_id_by_name(
            folder_name=folder,
            mailbox_type=self.mailbox_type,
            mailbox_upn=self.user_email,
        )
        if not folder_id:
            raise RuntimeError(f"Folder '{folder}' not found")

        result = self.api.copy_message(
            message_id=email.message_id,
            destination_folder_id=folder_id,
            mailbox_type=self.mailbox_type,
            mailbox_upn=self.user_email,
        )
        if not result:
            raise RuntimeError(f"Failed to copy email to folder '{folder}'")

    def delete_email(self, email: Email) -> None:
        """Delete an email."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to delete")

        headers = self._get_headers()
        url = f"{self.GRAPH_ROOT}/users/{self.user_email}/messages/{email.message_id}"

        try:
            resp = requests.delete(url, headers=headers, timeout=30)
            if resp.status_code not in (200, 204):
                raise RuntimeError(f"Failed to delete email: HTTP {resp.status_code}")
        except requests.exceptions.RequestException as exc:
            logger.error("Delete email request failed: %s", exc)
            raise RuntimeError(f"Failed to delete email: {exc}")

    def mark_read_email(self, email: Email) -> None:
        """Mark an email as read."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to mark read")

        headers = self._get_headers()
        url = f"{self.GRAPH_ROOT}/users/{self.user_email}/messages/{email.message_id}"

        try:
            resp = requests.patch(
                url,
                headers=headers,
                json={"isRead": True},
                timeout=30,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to mark email read: HTTP {resp.status_code}"
                )
            email._is_unread = False
        except requests.exceptions.RequestException as exc:
            logger.error("Mark read request failed: %s", exc)
            raise RuntimeError(f"Failed to mark email read: {exc}")

    def mark_unread_email(self, email: Email) -> None:
        """Mark an email as unread."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to mark unread")

        headers = self._get_headers()
        url = f"{self.GRAPH_ROOT}/users/{self.user_email}/messages/{email.message_id}"

        try:
            resp = requests.patch(
                url,
                headers=headers,
                json={"isRead": False},
                timeout=30,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to mark email unread: HTTP {resp.status_code}"
                )
            email._is_unread = True
        except requests.exceptions.RequestException as exc:
            logger.error("Mark unread request failed: %s", exc)
            raise RuntimeError(f"Failed to mark email unread: {exc}")

    def add_label_email(self, email: Email, text: str) -> None:
        """Add an Outlook category to an email."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to add a label")

        existing = self.api.get_message_categories(
            email.message_id,
            mailbox_type=self.mailbox_type,
            mailbox_upn=self.user_email,
        )
        if any(label.lower() == text.lower() for label in existing):
            email._labels = existing
            return

        updated = [*existing, text]
        success = self.api.update_message_categories(
            email.message_id,
            updated,
            mailbox_type=self.mailbox_type,
            mailbox_upn=self.user_email,
        )
        if not success:
            raise RuntimeError(f"Failed to add Outlook category {text!r}")
        email._labels = updated

    def has_label_email(self, email: Email, text: str) -> bool:
        """Check whether an email has an Outlook category."""
        if not email.message_id:
            raise ValueError("Email.message_id is required to check labels")

        if any(label.lower() == text.lower() for label in email._labels):
            return True

        labels = self.api.get_message_categories(
            email.message_id,
            mailbox_type=self.mailbox_type,
            mailbox_upn=self.user_email,
        )
        email._labels = labels
        return any(label.lower() == text.lower() for label in labels)

    def enrich_email(self, email: Email, content) -> None:
        """Add visible enrichment content to an email."""
        if not content:
            logger.warning("enrich_email called with no content")
            return
        if not email.message_id:
            raise ValueError("Email.message_id is required to enrich")

        if isinstance(content, dict):
            enrichment_text = content.get("result", str(content))
        else:
            enrichment_text = str(content)

        try:
            enrichment_html = self._get_enrichment_html(enrichment_text)
        except FileNotFoundError:
            logger.error("Enrichment template not found")
            return
        except Exception as exc:
            logger.error("Error loading enrichment template: %s", exc)
            return

        current_body = (
            self.api.get_message_body(
                message_id=email.message_id,
                mailbox_type=self.mailbox_type,
                mailbox_upn=self.user_email,
            )
            or email.text
        )

        enriched_body = enrichment_html + current_body
        success = self.api.update_message_body(
            message_id=email.message_id,
            new_body=enriched_body,
            mailbox_type=self.mailbox_type,
            mailbox_upn=self.user_email,
        )
        if success:
            email.text = enriched_body
        else:
            raise RuntimeError("Failed to update email body with enrichment")

    def enrich_email_hidden(self, email: Email, content) -> None:
        """Add hidden enrichment content to an email."""
        raise NotImplementedError(
            "enrich_email_hidden is not supported for GraphEmailAccount"
        )

    def create_draft(self, email: Email, folder: str) -> None:
        """Save an email as draft in a folder."""
        headers = self._get_headers()

        folder_id = self.api.get_folder_id_by_name(
            folder_name=folder,
            mailbox_type=self.mailbox_type,
            mailbox_upn=self.user_email,
        )
        if not folder_id:
            raise RuntimeError(f"Folder '{folder}' not found")

        to_recipients = [
            {"emailAddress": {"address": addr.strip()}}
            for addr in email.recipient.split(",")
            if addr.strip()
        ]

        message = {
            "subject": email.subject,
            "body": {
                "contentType": "HTML",
                "content": plain_to_html(email.text),
            },
            "toRecipients": to_recipients,
        }

        url = f"{self.GRAPH_ROOT}/users/{self.user_email}/mailFolders/{folder_id}/messages"

        try:
            resp = requests.post(url, headers=headers, json=message, timeout=30)
            if resp.status_code == 201:
                data = _as_dict(resp.json())
                email.message_id = _as_str(data.get("id")) or email.message_id
                email.account = self
            else:
                raise RuntimeError(f"Failed to create draft: HTTP {resp.status_code}")
        except requests.exceptions.RequestException as exc:
            logger.error("Create draft request failed: %s", exc)
            raise RuntimeError(f"Failed to create draft: {exc}")

    # Helpers for enrichment
    @staticmethod
    def _format_enrichment_text(text: str) -> str:
        """Format enrichment text for readability."""
        if not text:
            return text

        formatted = re.sub(r"(\s+)([A-Z][a-zA-Z\s]+:\s+)", r"\n\n\2", text)
        formatted = re.sub(
            r"([^\s])(\s+)([A-Z][a-zA-Z\s]+:\s+)", r"\1\n\n\3", formatted
        )

        closing_patterns = [
            r"([^\n])(\s+)(Mit freundlichen Grüßen)",
            r"([^\n])(\s+)(Kind regards)",
            r"([^\n])(\s+)(Best regards)",
            r"([^\n])(\s+)(Regards)",
        ]
        for pattern in closing_patterns:
            formatted = re.sub(pattern, r"\1\n\n\3", formatted, flags=re.IGNORECASE)

        formatted = re.sub(r"\n{3,}", r"\n\n", formatted)
        lines = [line.rstrip() for line in formatted.split("\n")]
        return "\n".join(lines).strip()

    def _get_enrichment_html(self, enrichment_text: str) -> str:
        """Get enrichment HTML by loading from template file."""
        formatted_text = self._format_enrichment_text(enrichment_text)
        escaped_text = escape(formatted_text)
        html_text = escaped_text.replace("\n", "<br>")

        try:
            template_path = (
                resources.files("agy.templates") / "enrichment_template.html"
            )
        except Exception:
            template_path = (
                Path(__file__).resolve().parents[2]
                / "templates"
                / "enrichment_template.html"
            )
        template = template_path.read_text(encoding="utf-8")
        return template.format(enrichment_text=html_text)
