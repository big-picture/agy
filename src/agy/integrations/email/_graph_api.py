"""Microsoft Graph API utility class for mailbox operations."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

from .env_config import get_graph_credentials

# Graph API base URL and scope
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
SCOPE = "https://graph.microsoft.com/.default"

logger = logging.getLogger(__name__)


def _json_dict(resp: requests.Response) -> dict[str, Any]:
    """Json dict.

    Args:
        resp: resp.

    Returns:
        dict[str, Any]: Operation result.
    """
    data = resp.json()
    return data if isinstance(data, dict) else {}


def _json_str(resp: requests.Response, key: str) -> str | None:
    """Json str.

    Args:
        resp: resp.
        key: key.

    Returns:
        str | None: Operation result.
    """
    value = _json_dict(resp).get(key)
    return value if isinstance(value, str) else None


class GraphAPI:
    """Utility class for Microsoft Graph API operations."""

    def __init__(
        self,
        *,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        mailbox_upn: str | None = None,
    ):
        """Initialize GraphAPI with credentials (env defaults allowed)."""
        self._cached_token: str | None = None
        creds = get_graph_credentials()
        self._tenant_id = tenant_id or creds["tenant_id"]
        self._client_id = client_id or creds["client_id"]
        self._client_secret = client_secret or creds["client_secret"]
        self._mailbox_upn = mailbox_upn or creds["mailbox_upn"]

        if not self._tenant_id or not self._client_id or not self._client_secret:
            raise ValueError(
                "Missing required credentials: GRAPH_TENANT_ID, GRAPH_CLIENT_ID, "
                "GRAPH_CLIENT_SECRET (or deprecated TENANT_ID, CLIENT_ID, CLIENT_SECRET)."
            )

    # ------------------------------------------------------------------ Auth
    def _get_access_token(self, force_refresh: bool = False) -> str:
        """Get Graph API access token, using cached token if available."""
        if self._cached_token and not force_refresh:
            logger.info("Using cached Graph access token")
            return self._cached_token

        logger.info("Fetching new Graph access token")
        self._cached_token = self._get_graph_access_token_with_retry()
        return self._cached_token

    def _get_graph_access_token_with_retry(self, max_retries: int = 3) -> str:
        """Fetch Microsoft Graph access token with retry logic."""
        token_url = (
            f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        )
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": SCOPE,
        }

        base_delay = 2.0
        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    "Requesting token (attempt %s/%s)", attempt + 1, max_retries + 1
                )
                response = requests.post(url=token_url, data=data, timeout=10)
                logger.info("Token response status: %s", response.status_code)

                if response.status_code == 200:
                    access_token = _json_str(response, "access_token")
                    if access_token:
                        return access_token
                    raise ValueError("Access token not found in response")

                if attempt < max_retries:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "Token fetch failed, retrying in %.1f seconds", delay
                    )
                    time.sleep(delay)
                else:
                    error_msg = response.text[:500]
                    logger.error(
                        "Failed to fetch token after retries; last error: %s", error_msg
                    )
                    response.raise_for_status()
            except (
                requests.exceptions.RequestException
            ) as exc:  # pragma: no cover - network
                if attempt < max_retries:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "Token request exception, retrying in %.1f seconds: %s",
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                else:
                    logger.error("Failed to fetch token after retries: %s", exc)
                    raise

        raise ValueError("Failed to fetch access token")

    def _get_headers(self, force_refresh_token: bool = False) -> dict[str, str]:
        """Get HTTP headers for Graph API requests."""
        token = self._get_access_token(force_refresh=force_refresh_token)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ Operations
    def move_message(
        self,
        message_id: str,
        destination_folder_id: str,
        *,
        mailbox_type: str = "personal",
        mailbox_upn: str | None = None,
    ) -> dict[str, Any] | None:
        """Move a message to a different folder.

        Graph returns the moved message as a new item. Callers should refresh any
        cached message ID from the returned payload before doing further actions.
        """
        mailbox_upn = mailbox_upn or self._mailbox_upn
        headers = self._get_headers()

        if mailbox_type == "personal":
            if mailbox_upn:
                url = f"{GRAPH_ROOT}/users/{mailbox_upn}/messages/{message_id}/move"
            else:
                url = f"{GRAPH_ROOT}/me/messages/{message_id}/move"
        elif mailbox_type == "shared":
            if not mailbox_upn:
                raise ValueError("mailbox_upn required for shared mailbox")
            url = f"{GRAPH_ROOT}/users/{mailbox_upn}/messages/{message_id}/move"
        else:
            raise ValueError(f"Unknown mailbox_type: {mailbox_type}")

        payload = {"destinationId": destination_folder_id}
        logger.info("Graph move_message → POST %s", url)

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            logger.info("Response status: %s", resp.status_code)
            if resp.status_code == 201:
                return _json_dict(resp)
            _log_error(resp)
            return None
        except (
            requests.exceptions.RequestException
        ) as exc:  # pragma: no cover - network
            logger.error("move_message request exception: %s", exc)
            return None

    def copy_message(
        self,
        message_id: str,
        destination_folder_id: str,
        *,
        mailbox_type: str = "personal",
        mailbox_upn: str | None = None,
    ) -> dict[str, Any] | None:
        """Copy a message to a different folder, leaving the original in place.

        Graph returns the new copy as a new item with a fresh message ID.
        """
        mailbox_upn = mailbox_upn or self._mailbox_upn
        headers = self._get_headers()

        if mailbox_type == "personal":
            if mailbox_upn:
                url = f"{GRAPH_ROOT}/users/{mailbox_upn}/messages/{message_id}/copy"
            else:
                url = f"{GRAPH_ROOT}/me/messages/{message_id}/copy"
        elif mailbox_type == "shared":
            if not mailbox_upn:
                raise ValueError("mailbox_upn required for shared mailbox")
            url = f"{GRAPH_ROOT}/users/{mailbox_upn}/messages/{message_id}/copy"
        else:
            raise ValueError(f"Unknown mailbox_type: {mailbox_type}")

        payload = {"destinationId": destination_folder_id}
        logger.info("Graph copy_message → POST %s", url)

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            logger.info("Response status: %s", resp.status_code)
            if resp.status_code == 201:
                return _json_dict(resp)
            _log_error(resp)
            return None
        except (
            requests.exceptions.RequestException
        ) as exc:  # pragma: no cover - network
            logger.error("copy_message request exception: %s", exc)
            return None

    def create_reply_message(
        self,
        message_id: str,
        reply_text: str,
        *,
        subject: str | None = None,
        attachments: list[dict[str, str]] | None = None,
        mailbox_type: str = "personal",
        mailbox_upn: str | None = None,
        send: bool = True,
    ) -> str | None:
        """Create + send a reply to the sender of an existing email.

        See :meth:`_create_reply` for full parameter docs.
        """
        return self._create_reply(
            message_id,
            reply_text,
            reply_all=False,
            subject=subject,
            attachments=attachments,
            mailbox_type=mailbox_type,
            mailbox_upn=mailbox_upn,
            send=send,
        )

    def create_reply_all_message(
        self,
        message_id: str,
        reply_text: str,
        *,
        subject: str | None = None,
        attachments: list[dict[str, str]] | None = None,
        mailbox_type: str = "personal",
        mailbox_upn: str | None = None,
        send: bool = True,
    ) -> str | None:
        """Create + send a reply-all to an existing email.

        See :meth:`_create_reply` for full parameter docs.
        """
        return self._create_reply(
            message_id,
            reply_text,
            reply_all=True,
            subject=subject,
            attachments=attachments,
            mailbox_type=mailbox_type,
            mailbox_upn=mailbox_upn,
            send=send,
        )

    def _create_reply(
        self,
        message_id: str,
        reply_text: str,
        *,
        reply_all: bool,
        subject: str | None = None,
        attachments: list[dict[str, str]] | None = None,
        mailbox_type: str = "personal",
        mailbox_upn: str | None = None,
        send: bool = True,
    ) -> str | None:
        """Shared implementation for reply and reply-all.

        Workflow: create draft → update body/subject → add attachments → send.

        Args:
            message_id: Graph message ID to reply to.
            reply_text: HTML body for the reply.
            reply_all: ``True`` for createReplyAll, ``False`` for createReply.
            subject: Override the reply subject (default keeps original).
            attachments: File attachments as Graph API dicts (with
                ``@odata.type``, ``name``, ``contentBytes``, ``contentType``).
            mailbox_type: ``"personal"`` or ``"shared"``.
            mailbox_upn: User principal name for the mailbox.
            send: If ``False``, keep the reply as a draft (no ``/send``).

        Returns:
            Draft message ID on success, ``None`` on failure.
        """
        mailbox_upn = mailbox_upn or self._mailbox_upn
        headers = self._get_headers()

        action = "createReplyAll" if reply_all else "createReply"

        if mailbox_type == "personal":
            if mailbox_upn:
                draft_url = (
                    f"{GRAPH_ROOT}/users/{mailbox_upn}/messages/{message_id}/{action}"
                )
                update_base = f"{GRAPH_ROOT}/users/{mailbox_upn}/messages"
            else:
                draft_url = f"{GRAPH_ROOT}/me/messages/{message_id}/{action}"
                update_base = f"{GRAPH_ROOT}/me/messages"
        elif mailbox_type == "shared":
            if not mailbox_upn:
                raise ValueError("mailbox_upn required for shared mailbox")
            draft_url = (
                f"{GRAPH_ROOT}/users/{mailbox_upn}/messages/{message_id}/{action}"
            )
            update_base = f"{GRAPH_ROOT}/users/{mailbox_upn}/messages"
        else:
            raise ValueError(f"Unknown mailbox_type: {mailbox_type}")

        logger.info("Graph %s → POST %s", action, draft_url)

        try:
            # 1) Create reply draft
            resp = requests.post(draft_url, headers=headers, json={}, timeout=30)
            if resp.status_code != 201:
                _log_error(resp, "Failed to create reply draft")
                return None

            reply_id = _json_str(resp, "id")
            if not reply_id:
                logger.error("Reply ID not found in response")
                return None

            update_url = f"{update_base}/{reply_id}"
            send_url = f"{update_base}/{reply_id}/send"

            # 2) Update body (and optionally subject)
            payload: dict[str, Any] = {
                "body": {"contentType": "HTML", "content": reply_text},
            }
            if subject is not None:
                payload["subject"] = subject

            update_resp = requests.patch(
                update_url, headers=headers, json=payload, timeout=30
            )
            if update_resp.status_code != 200:
                _log_error(update_resp, "Failed to update reply draft")
                return reply_id

            # 3) Add attachments
            if attachments:
                att_url = f"{update_url}/attachments"
                for att in attachments:
                    att_resp = requests.post(
                        att_url, headers=headers, json=att, timeout=30
                    )
                    if att_resp.status_code != 201:
                        _log_error(att_resp, f"Failed to attach {att.get('name')}")

            # 4) Send (optional)
            if not send:
                logger.info(
                    "Graph reply draft saved without send (draft_only); message id=%s",
                    reply_id,
                )
                return reply_id
            send_resp = requests.post(send_url, headers=headers, timeout=30)
            if send_resp.status_code == 202:
                return reply_id
            _log_error(send_resp, "Failed to send reply")
            return reply_id

        except (
            requests.exceptions.RequestException
        ) as exc:  # pragma: no cover - network
            logger.error("_create_reply request exception: %s", exc)
            return None

    def forward_message(
        self,
        message_id: str,
        forward_to: str,
        forward_text: str | None = None,
        *,
        mailbox_type: str = "personal",
        mailbox_upn: str | None = None,
        send: bool = True,
    ) -> str | None:
        """Forward a message to a specified address."""
        mailbox_upn = mailbox_upn or self._mailbox_upn
        headers = self._get_headers()

        get_url = _message_url(
            message_id,
            mailbox_type,
            mailbox_upn,
            select="id,subject,from,toRecipients,body",
        )
        try:
            resp = requests.get(get_url, headers=headers, timeout=30)
            if resp.status_code != 200:
                _log_error(resp, "Failed to get message details")
                return None
            message_data = _json_dict(resp)
        except (
            requests.exceptions.RequestException
        ) as exc:  # pragma: no cover - network
            logger.error("forward_message request exception: %s", exc)
            return None

        subject = message_data.get("subject", "")
        original_body = message_data.get("body", {}).get("content", "")
        if forward_text:
            forward_body = (
                f"{forward_text}<br/><br/>--- Forwarded Message ---<br/>{original_body}"
            )
        else:
            forward_body = f"--- Forwarded Message ---<br/>{original_body}"
        forward_subject = f"FW: {subject}" if subject else "FW:"

        create_base = _messages_base(mailbox_type, mailbox_upn)
        if not create_base:
            raise ValueError("mailbox_upn required for shared mailbox")

        payload = {
            "subject": forward_subject,
            "body": {"contentType": "HTML", "content": forward_body},
            "toRecipients": [{"emailAddress": {"address": forward_to}}],
        }

        try:
            create_resp = requests.post(
                create_base, headers=headers, json=payload, timeout=30
            )
            if create_resp.status_code != 201:
                _log_error(create_resp, "Failed to create forward message")
                return None

            forward_id = _json_str(create_resp, "id")
            if not forward_id:
                logger.error("Forward ID missing in response")
                return None

            # Copy attachments
            self._copy_attachments(message_id, forward_id, mailbox_type, mailbox_upn)

            if not send:
                logger.info(
                    "Graph forward draft saved without send (draft_only); message id=%s",
                    forward_id,
                )
                return forward_id

            send_base = _messages_base(mailbox_type, mailbox_upn)
            send_url = f"{send_base}/{forward_id}/send"
            send_resp = requests.post(send_url, headers=headers, timeout=30)
            if send_resp.status_code == 202:
                return forward_id
            _log_error(send_resp, "Failed to send forward")
            return forward_id
        except (
            requests.exceptions.RequestException
        ) as exc:  # pragma: no cover - network
            logger.error("forward_message request exception: %s", exc)
            return None

    def _copy_attachments(
        self,
        source_message_id: str,
        target_message_id: str,
        mailbox_type: str,
        mailbox_upn: str | None,
    ) -> bool:
        """Copy attachments from source message to target message."""
        headers = self._get_headers()

        get_url = _attachments_url(source_message_id, mailbox_type, mailbox_upn)
        try:
            resp = requests.get(get_url, headers=headers, timeout=30)
            if resp.status_code != 200:
                logger.warning("Failed to get attachments from source message")
                return False
            attachments_raw = _json_dict(resp).get("value", [])
            attachments = attachments_raw if isinstance(attachments_raw, list) else []
        except (
            requests.exceptions.RequestException
        ) as exc:  # pragma: no cover - network
            logger.error("copy_attachments request exception: %s", exc)
            return False

        if not attachments:
            logger.info("No attachments to copy")
            return True

        attach_url = _attachments_post_url(target_message_id, mailbox_type, mailbox_upn)
        success_count = 0
        for attachment in attachments:
            attachment_name = attachment.get("name", "unnamed")
            attachment_id = attachment.get("id")

            content_url = _attachment_content_url(
                source_message_id, attachment_id, mailbox_type, mailbox_upn
            )
            try:
                content_resp = requests.get(content_url, headers=headers, timeout=30)
                if content_resp.status_code != 200:
                    logger.warning(
                        "Failed to get content for attachment: %s", attachment_name
                    )
                    continue
                content_bytes = content_resp.content
            except requests.exceptions.RequestException:  # pragma: no cover - network
                logger.warning(
                    "Failed to fetch attachment content: %s", attachment_name
                )
                continue

            import base64

            content_base64 = base64.b64encode(content_bytes).decode("utf-8")
            content_type = attachment.get("contentType", "application/octet-stream")
            attachment_payload = {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": attachment_name,
                "contentBytes": content_base64,
                "contentType": content_type,
            }

            try:
                attach_resp = requests.post(
                    attach_url, headers=headers, json=attachment_payload, timeout=30
                )
                if attach_resp.status_code == 201:
                    success_count += 1
                else:
                    logger.warning(
                        "Failed to attach %s. HTTP %s",
                        attachment_name,
                        attach_resp.status_code,
                    )
            except (
                requests.exceptions.RequestException
            ) as exc:  # pragma: no cover - network
                logger.warning(
                    "Attachment post failed for %s: %s", attachment_name, exc
                )

        logger.info("Copied %s/%s attachment(s)", success_count, len(attachments))
        return success_count == len(attachments)

    def get_folder_id_by_name(
        self,
        folder_name: str,
        *,
        mailbox_type: str = "personal",
        mailbox_upn: str | None = None,
    ) -> str | None:
        """
        Get folder ID by folder name or path.

        Supports:
        - Simple names: "Inbox", "Sent Items", "logistics"
        - Nested paths: "logistics/logistics_inbox", "Projects/Active/2024"
        - Aliases: "sent" → "Sent Items", "trash" → "Deleted Items"

        Args:
            folder_name: Folder name or path (use "/" for nested folders)
            mailbox_type: "personal" or "shared"
            mailbox_upn: User principal name for the mailbox

        Returns:
            Folder ID or None if not found
        """
        mailbox_upn = mailbox_upn or self._mailbox_upn
        headers = self._get_headers()

        # Well-known folder names supported directly by Graph API (language-independent).
        # Using these bypasses display-name search, which avoids issues with localized
        # folder names (e.g. German "Posteingang" vs English "Inbox").
        well_known_folder_map = {
            "inbox": "inbox",
            "posteingang": "inbox",
            "sent items": "sentitems",
            "sent": "sentitems",
            "gesendete elemente": "sentitems",
            "deleted items": "deleteditems",
            "deleted": "deleteditems",
            "trash": "deleteditems",
            "gelöschte elemente": "deleteditems",
            "papierkorb": "deleteditems",
            "drafts": "drafts",
            "entwürfe": "drafts",
            "junk email": "junkemail",
            "junk": "junkemail",
            "junk-e-mail": "junkemail",
            "spam": "junkemail",
            "outbox": "outbox",
            "postausgang": "outbox",
        }

        # Determine base URL
        if mailbox_type == "personal":
            if mailbox_upn:
                base_url = f"{GRAPH_ROOT}/users/{mailbox_upn}/mailFolders"
            else:
                base_url = f"{GRAPH_ROOT}/me/mailFolders"
        elif mailbox_type == "shared":
            if not mailbox_upn:
                raise ValueError("mailbox_upn required for shared mailbox")
            base_url = f"{GRAPH_ROOT}/users/{mailbox_upn}/mailFolders"
        else:
            raise ValueError(f"Unknown mailbox_type: {mailbox_type}")

        # For simple (non-nested) well-known folder names, resolve directly via the
        # Graph well-known folder endpoint — no display-name listing needed.
        path_parts = folder_name.split("/")
        if len(path_parts) == 1:
            wk = well_known_folder_map.get(folder_name.lower())
            if wk:
                try:
                    resp = requests.get(f"{base_url}/{wk}", headers=headers, timeout=30)
                    if resp.status_code == 200:
                        return resp.json().get("id")
                    # Fall through to display-name search if well-known lookup fails
                except requests.exceptions.RequestException:
                    pass

        current_folder_id = None

        for i, part in enumerate(path_parts):
            if current_folder_id is None:
                url = base_url
            else:
                url = f"{base_url}/{current_folder_id}/childFolders"

            try:
                # Fetch all pages — Graph API defaults to 10 items per page
                folders: list[dict] = []
                next_url: str | None = url
                while next_url:
                    resp = requests.get(next_url, headers=headers, timeout=30)
                    if resp.status_code != 200:
                        _log_error(resp, f"Failed to get folders at level {i}")
                        return None
                    data = resp.json()
                    folders.extend(data.get("value", []))
                    next_url = data.get("@odata.nextLink")

                found = False
                for folder in folders:
                    display_name = folder.get("displayName", "")
                    if display_name.lower() == part.lower():
                        current_folder_id = folder.get("id")
                        found = True
                        break

                if not found:
                    path_so_far = "/".join(path_parts[: i + 1])
                    logger.warning(
                        "Folder '%s' not found in path '%s' (looking for '%s')",
                        part,
                        path_so_far,
                        folder_name,
                    )
                    return None

            except requests.exceptions.RequestException as exc:
                logger.error("get_folder_id_by_name request exception: %s", exc)
                return None

        return current_folder_id

    def update_message_body(
        self,
        message_id: str,
        new_body: str,
        *,
        mailbox_type: str = "personal",
        mailbox_upn: str | None = None,
    ) -> bool:
        """Update the body of a message."""
        mailbox_upn = mailbox_upn or self._mailbox_upn
        headers = self._get_headers()

        url = _message_url(message_id, mailbox_type, mailbox_upn)
        payload = {"body": {"contentType": "HTML", "content": new_body}}

        try:
            resp = requests.patch(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                return True
            _log_error(resp, "Failed to update message body")
            return False
        except (
            requests.exceptions.RequestException
        ) as exc:  # pragma: no cover - network
            logger.error("update_message_body request exception: %s", exc)
            return False

    def get_message_body(
        self,
        message_id: str,
        *,
        mailbox_type: str = "personal",
        mailbox_upn: str | None = None,
    ) -> str | None:
        """Get the body content of a message (HTML)."""
        mailbox_upn = mailbox_upn or self._mailbox_upn
        headers = self._get_headers()

        url = _message_url(message_id, mailbox_type, mailbox_upn, select="body")
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                _log_error(resp, "Failed to get message body")
                return None
            body_obj = _json_dict(resp).get("body")
            if isinstance(body_obj, dict):
                content = body_obj.get("content")
                if isinstance(content, str):
                    return content
            return ""
        except (
            requests.exceptions.RequestException
        ) as exc:  # pragma: no cover - network
            logger.error("get_message_body request exception: %s", exc)
            return None

    def get_message_categories(
        self,
        message_id: str,
        *,
        mailbox_type: str = "personal",
        mailbox_upn: str | None = None,
    ) -> list[str]:
        """Get the categories currently assigned to a message."""
        mailbox_upn = mailbox_upn or self._mailbox_upn
        headers = self._get_headers()

        url = _message_url(message_id, mailbox_type, mailbox_upn, select="categories")
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                _log_error(resp, "Failed to get message categories")
                return []
            categories = _json_dict(resp).get("categories")
            if not isinstance(categories, list):
                return []
            return [value for value in categories if isinstance(value, str)]
        except (
            requests.exceptions.RequestException
        ) as exc:  # pragma: no cover - network
            logger.error("get_message_categories request exception: %s", exc)
            return []

    def update_message_categories(
        self,
        message_id: str,
        categories: list[str],
        *,
        mailbox_type: str = "personal",
        mailbox_upn: str | None = None,
    ) -> bool:
        """Replace the categories assigned to a message."""
        mailbox_upn = mailbox_upn or self._mailbox_upn
        headers = self._get_headers()
        url = _message_url(message_id, mailbox_type, mailbox_upn)
        payload = {"categories": categories}

        try:
            resp = requests.patch(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                return True
            _log_error(resp, "Failed to update message categories")
            return False
        except (
            requests.exceptions.RequestException
        ) as exc:  # pragma: no cover - network
            logger.error("update_message_categories request exception: %s", exc)
            return False



# --------------------------------------------------------------------------- helpers
def _log_error(resp: requests.Response, prefix: str | None = None) -> None:
    """Log error.

    Args:
        resp: resp.
        prefix: prefix.
    """
    msg = prefix or "Graph API error"
    try:
        data = resp.json()
        logger.error(
            "%s. HTTP %s: %s", msg, resp.status_code, json.dumps(data, indent=2)
        )
    except Exception:
        logger.error("%s. HTTP %s: %s", msg, resp.status_code, resp.text[:500])


def _messages_base(mailbox_type: str, mailbox_upn: str | None) -> str | None:
    """Messages base.

    Args:
        mailbox_type: mailbox type.
        mailbox_upn: mailbox upn.

    Returns:
        str | None: Operation result.
    """
    if mailbox_type == "personal":
        return (
            f"{GRAPH_ROOT}/users/{mailbox_upn}/messages"
            if mailbox_upn
            else f"{GRAPH_ROOT}/me/messages"
        )
    if mailbox_type == "shared":
        if not mailbox_upn:
            return None
        return f"{GRAPH_ROOT}/users/{mailbox_upn}/messages"
    raise ValueError(f"Unknown mailbox_type: {mailbox_type}")




def _message_url(
    message_id: str,
    mailbox_type: str,
    mailbox_upn: str | None,
    select: str | None = None,
) -> str:
    """Message url.

    Args:
        message_id: message id.
        mailbox_type: mailbox type.
        mailbox_upn: mailbox upn.
        select: select.

    Returns:
        str: Operation result.
    """
    base = _messages_base(mailbox_type, mailbox_upn)
    if base is None:
        raise ValueError("mailbox_upn required for shared mailbox")
    url = f"{base}/{message_id}"
    if select:
        url += f"?$select={select}"
    return url


def _attachments_url(
    message_id: str, mailbox_type: str, mailbox_upn: str | None
) -> str:
    """Attachments url.

    Args:
        message_id: message id.
        mailbox_type: mailbox type.
        mailbox_upn: mailbox upn.

    Returns:
        str: Operation result.
    """
    base = _messages_base(mailbox_type, mailbox_upn)
    if base is None:
        raise ValueError("mailbox_upn required for shared mailbox")
    return f"{base}/{message_id}/attachments"


def _attachments_post_url(
    message_id: str, mailbox_type: str, mailbox_upn: str | None
) -> str:
    """Attachments post url.

    Args:
        message_id: message id.
        mailbox_type: mailbox type.
        mailbox_upn: mailbox upn.

    Returns:
        str: Operation result.
    """
    return _attachments_url(message_id, mailbox_type, mailbox_upn)


def _attachment_content_url(
    message_id: str, attachment_id: str, mailbox_type: str, mailbox_upn: str | None
) -> str:
    """Attachment content url.

    Args:
        message_id: message id.
        attachment_id: attachment id.
        mailbox_type: mailbox type.
        mailbox_upn: mailbox upn.

    Returns:
        str: Operation result.
    """
    base = _messages_base(mailbox_type, mailbox_upn)
    if base is None:
        raise ValueError("mailbox_upn required for shared mailbox")
    return f"{base}/{message_id}/attachments/{attachment_id}/$value"
