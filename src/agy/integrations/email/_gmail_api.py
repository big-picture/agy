"""Gmail API utility class for mailbox operations."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import sys
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2 import credentials as user_credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[GMAIL-API] %(message)s",
    stream=sys.stdout,
)
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


# Required Gmail scopes for read/modify/send and label management
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]


class GmailAPI:
    """Utility class for Gmail API operations."""

    def __init__(self):
        """
        Initialize GmailAPI with OAuth2 user credentials from environment.

        Required env:
          - GMAIL_AUTH_MODE=oauth
          - GMAIL_CLIENT_ID
          - GMAIL_CLIENT_SECRET
          - GMAIL_TOKEN_FILE (path to the refreshable token json)

        Optional:
          - GMAIL_USER (defaults to "me")
          - GMAIL_SCOPES (space-separated; defaults to SCOPES)
        """
        auth_mode = os.getenv("GMAIL_AUTH_MODE", "oauth").lower()
        if auth_mode != "oauth":
            raise ValueError("Only OAuth mode is supported. Set GMAIL_AUTH_MODE=oauth.")

        self._user = os.getenv("GMAIL_USER", "me")
        self._scopes = self._resolve_scopes()

        credentials = self._load_oauth_credentials()
        if not credentials:
            raise ValueError("Missing or invalid Gmail OAuth credentials.")

        self._service = build(
            "gmail", "v1", credentials=credentials, cache_discovery=False
        )
        logger.info("GmailAPI initialized in OAuth mode for user: %s", self._user)

    def _resolve_scopes(self) -> list[str]:
        """Return scopes from env or defaults."""
        scopes_env = os.getenv("GMAIL_SCOPES")
        if scopes_env:
            return [s for s in scopes_env.split() if s.strip()]
        return SCOPES

    def _load_oauth_credentials(self):
        """
        Load user OAuth2 credentials from token file (refreshable).

        Required env:
          - GMAIL_CLIENT_ID
          - GMAIL_CLIENT_SECRET
          - GMAIL_TOKEN_FILE (path to token.json produced by the auth helper)
        """
        token_path = os.getenv("GMAIL_TOKEN_FILE", "token.json")
        client_id = os.getenv("GMAIL_CLIENT_ID")
        client_secret = os.getenv("GMAIL_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error(
                "GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET are required for OAuth2 mode."
            )
            return None

        try:
            with open(token_path, encoding="utf-8") as f:
                token_data = json.load(f)
        except Exception as exc:
            logger.error("Failed to read token file '%s': %s", token_path, exc)
            return None

        creds = user_credentials.Credentials.from_authorized_user_info(
            token_data, scopes=self._scopes
        )

        if not creds.valid and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
                logger.info("Refreshed Gmail OAuth token.")
            except Exception as exc:
                logger.error("Failed to refresh Gmail OAuth token: %s", exc)
                return None

        # Ensure client info is present for refresh (if not stored in token file)
        creds._client_id = client_id
        creds._client_secret = client_secret
        return creds

    # ------------------------------------------------------------------ #
    # Label helpers
    # ------------------------------------------------------------------ #
    def _find_label(self, label_name: str) -> tuple[str | None, dict]:
        """Find label by name (case-insensitive)."""
        try:
            labels_response = (
                self._service.users().labels().list(userId=self._user).execute()
            )
            for label in labels_response.get("labels", []):
                if label.get("name", "").lower() == label_name.lower():
                    return label.get("id"), label
        except HttpError as exc:
            logger.error("Failed to list labels: %s", exc)
        return None, {}

    def get_label_id_by_name(
        self, label_name: str, create_if_missing: bool = True
    ) -> str | None:
        """
        Get Gmail label ID by name. Optionally create the label if it does not exist.
        """
        label_id, _ = self._find_label(label_name)
        if label_id:
            return label_id

        if not create_if_missing:
            logger.warning("Label '%s' not found.", label_name)
            return None

        try:
            body = {"name": label_name}
            created = _as_dict(
                self._service.users()
                .labels()
                .create(userId=self._user, body=body)
                .execute()
            )
            label_id = _as_str(created.get("id"))
            logger.info("Created label '%s' with id %s", label_name, label_id)
            return label_id
        except HttpError as exc:
            logger.error("Failed to create label '%s': %s", label_name, exc)
            return None

    # ------------------------------------------------------------------ #
    # Message helpers
    # ------------------------------------------------------------------ #
    def get_message(self, message_id: str) -> dict | None:
        """Retrieve a message in 'full' format."""
        try:
            message = _as_dict(
                self._service.users()
                .messages()
                .get(userId=self._user, id=message_id, format="full")
                .execute()
            )
            return message
        except HttpError as exc:
            logger.error("Failed to fetch message %s: %s", message_id, exc)
            return None

    def get_message_body(self, message_id: str) -> str | None:
        """Extract plain text or HTML body from a message."""
        message = self.get_message(message_id)
        if not message:
            return None

        payload = message.get("payload", {})
        body = self._extract_body(payload)
        if not body:
            logger.warning("No body content found for message %s", message_id)
        return body

    def move_message(self, message_id: str, destination_label: str) -> bool:
        """
        Move (label) a message by adding the destination label and removing INBOX.
        Gmail uses labels instead of folders; removing INBOX simulates a move.
        """
        dest_label_id = self.get_label_id_by_name(destination_label)
        if not dest_label_id:
            return False

        remove_labels: list[str] = []
        if destination_label.lower() != "inbox":
            remove_labels.append("INBOX")

        try:
            body = {
                "addLabelIds": [dest_label_id],
                "removeLabelIds": remove_labels,
            }
            self._service.users().messages().modify(
                userId=self._user, id=message_id, body=body
            ).execute()
            logger.info("Moved message %s to label '%s'", message_id, destination_label)
            return True
        except HttpError as exc:
            logger.error("Failed to move message %s: %s", message_id, exc)
            return False

    def create_reply_message(
        self, message_id: str, reply_text: str, *, send: bool = True
    ) -> str | None:
        """Send a reply in the same thread to the original sender (or save as draft)."""
        message = self.get_message(message_id)
        if not message:
            return None

        headers = {
            h["name"].lower(): h["value"]
            for h in message.get("payload", {}).get("headers", [])
        }
        thread_id = message.get("threadId")
        subject = headers.get("subject", "")
        from_addr = headers.get("from", "")

        email_msg = EmailMessage()
        email_msg["To"] = from_addr
        email_msg["Subject"] = (
            subject if subject.lower().startswith("re:") else f"Re: {subject}"
        )
        if "message-id" in headers:
            email_msg["In-Reply-To"] = headers["message-id"]
            email_msg["References"] = headers["message-id"]
        email_msg.set_content(reply_text, subtype="html")

        raw = base64.urlsafe_b64encode(email_msg.as_bytes()).decode("utf-8")
        body: dict[str, Any] = {"raw": raw, "threadId": thread_id}

        try:
            if not send:
                draft = _as_dict(
                    self._service.users()
                    .drafts()
                    .create(
                        userId=self._user,
                        body={"message": body},
                    )
                    .execute()
                )
                mid = draft.get("message", {}).get("id")
                logger.info("Reply saved as draft, id: %s", mid)
                return _as_str(mid) if mid else None
            sent = _as_dict(
                self._service.users()
                .messages()
                .send(userId=self._user, body=body)
                .execute()
            )
            logger.info("Reply sent, id: %s", sent.get("id"))
            return _as_str(sent.get("id")) or None
        except HttpError as exc:
            logger.error("Failed to send reply: %s", exc)
            return None

    def forward_message(
        self,
        message_id: str,
        forward_to: str,
        forward_text: str | None = None,
        *,
        send: bool = True,
    ) -> str | None:
        """Forward a message to the specified address (or save as draft)."""
        message = self.get_message(message_id)
        if not message:
            return None

        headers = {
            h["name"].lower(): h["value"]
            for h in message.get("payload", {}).get("headers", [])
        }
        subject = headers.get("subject", "")
        original_body = self._extract_body(message.get("payload", {})) or ""
        forward_body = (forward_text + "<br><br>") if forward_text else ""
        forward_body += "--- Forwarded message ---<br>" + original_body

        email_msg = EmailMessage()
        email_msg["To"] = forward_to
        email_msg["Subject"] = f"Fwd: {subject}"
        email_msg.set_content(forward_body, subtype="html")

        raw = base64.urlsafe_b64encode(email_msg.as_bytes()).decode("utf-8")
        body: dict[str, Any] = {"raw": raw}

        try:
            if not send:
                draft = _as_dict(
                    self._service.users()
                    .drafts()
                    .create(userId=self._user, body={"message": body})
                    .execute()
                )
                mid = draft.get("message", {}).get("id")
                logger.info("Forward saved as draft, id: %s", mid)
                return _as_str(mid) if mid else None
            sent = _as_dict(
                self._service.users()
                .messages()
                .send(userId=self._user, body=body)
                .execute()
            )
            logger.info("Forward sent, id: %s", sent.get("id"))
            return _as_str(sent.get("id")) or None
        except HttpError as exc:
            logger.error("Failed to forward message: %s", exc)
            return None

    def send_internal_note(
        self,
        subject: str,
        body_html: str,
        thread_id: str | None = None,
        to_address: str | None = None,
        label_names: list | None = None,
    ) -> str | None:
        """
        Send an internal note (email to self) optionally into an existing thread.
        Used to persist enrichment for Gmail where message bodies are immutable.
        """
        to_addr = to_address or self._user or "me"

        email_msg = EmailMessage()
        email_msg["To"] = to_addr
        email_msg["Subject"] = subject
        email_msg.set_content(body_html, subtype="html")

        raw = base64.urlsafe_b64encode(email_msg.as_bytes()).decode("utf-8")
        body: dict = {"raw": raw}
        if thread_id:
            body["threadId"] = thread_id

        label_ids: list[str] = []
        if label_names:
            for name in label_names:
                lid = self.get_label_id_by_name(name, create_if_missing=True)
                if lid:
                    label_ids.append(lid)
        if label_ids:
            body["labelIds"] = label_ids

        try:
            sent = _as_dict(
                self._service.users()
                .messages()
                .send(userId=self._user, body=body)
                .execute()
            )
            logger.info("Internal note sent, id: %s", sent.get("id"))
            return _as_str(sent.get("id")) or None
        except HttpError as exc:
            logger.error("Failed to send internal note: %s", exc)
            return None

    def update_message_body(self, message_id: str, new_body: str) -> bool:
        """
        Gmail messages are immutable; updating an existing message body is not supported.
        We log and return False so callers can handle gracefully.
        """
        logger.warning("Gmail does not support updating message bodies. Skipping.")
        return False

    # ------------------------------------------------------------------ #
    # Utilities
    # ------------------------------------------------------------------ #
    def _extract_body(self, payload: dict) -> str:
        """Recursively extract the first available HTML or plain text body from a message payload."""
        if not payload:
            return ""

        body_data = payload.get("body", {}).get("data")

        if body_data:
            decoded = base64.urlsafe_b64decode(body_data).decode(
                "utf-8", errors="ignore"
            )
            return decoded

        for part in payload.get("parts", []):
            part_mime = part.get("mimeType", "").lower()
            if part_mime in ("text/html", "text/plain"):
                data = part.get("body", {}).get("data")
                if data:
                    decoded = base64.urlsafe_b64decode(data).decode(
                        "utf-8", errors="ignore"
                    )
                    return decoded
            # Recurse into nested parts
            nested = self._extract_body(part)
            if nested:
                return nested

        return ""


# --------------------------------------------------------------------------- #
# Gmail fetcher (mirrors Graph fetcher behavior)
# --------------------------------------------------------------------------- #


class GmailFetcher:
    """Email fetcher using Gmail API."""

    def __init__(self, user_email: str | None = None):
        """Initialize the object.

        Args:
            user_email: user email.
        """
        load_dotenv()
        self.gmail_api = GmailAPI()
        self.user_email = user_email or self.gmail_api._user
        logger.info("GmailFetcher initialized for user: %s", self.user_email)

    def _message_to_dict(self, message: dict) -> dict:
        """Convert Gmail API message to simple dict format compatible with Email."""
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

        body_text = self.gmail_api._extract_body(message.get("payload", {}))
        if message.get("payload", {}).get("mimeType", "").lower() != "text/html":
            body_text = re.sub(r"<[^>]+>", "", body_text)

        return {
            "message_id": message.get("id", ""),
            "subject": subject,
            "from_address": from_addr,
            "to_addresses": to_addresses,
            "cc_addresses": cc_addresses,
            "reply_to": reply_to,
            "text": body_text,
            "body": body_text,
            "thread_id": message.get("threadId", ""),
        }

    def _list_message_ids(self, only_unread: bool, max_results: int) -> list[str]:
        """List message IDs from the inbox."""
        try:
            query = "in:inbox"
            if only_unread:
                query += " is:unread"

            response = (
                self.gmail_api._service.users()
                .messages()
                .list(
                    userId=self.gmail_api._user,
                    q=query,
                    maxResults=max_results,
                )
                .execute()
            )
            messages = response.get("messages", [])
            return [msg["id"] for msg in messages]
        except Exception as exc:
            logger.error("Failed to list Gmail messages: %s", exc)
            return []

    async def fetch_inbox(
        self,
        folder_id: str | None = None,  # Unused for Gmail
        only_unread: bool = False,
        top: int = 50,
        include_attachments: bool = False,  # Not implemented
    ) -> list[dict]:
        """Fetch emails from Gmail inbox."""
        logger.info(
            "Fetching Gmail messages (unread_only=%s, top=%s)", only_unread, top
        )
        message_ids = self._list_message_ids(only_unread=only_unread, max_results=top)
        logger.info("Found %s message id(s)", len(message_ids))

        email_dicts: list[dict] = []
        for mid in message_ids:
            message = self.gmail_api.get_message(mid)
            if not message:
                continue
            email_dicts.append(self._message_to_dict(message))

        logger.info("Converted %s email(s) to dict format", len(email_dicts))
        return email_dicts


# --------------------------------------------------------------------------- #
# Helper script to obtain Gmail OAuth2 tokens for user-based authentication.
# --------------------------------------------------------------------------- #


def obtain_oauth_token() -> None:
    """
    Desktop flow helper to obtain/refresh token.json.

    Env required:
        GMAIL_CLIENT_ID
        GMAIL_CLIENT_SECRET
        GMAIL_TOKEN_FILE (optional, default: token.json)
        GMAIL_SCOPES (optional, space-separated)
    """
    load_dotenv()
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    token_path = os.getenv("GMAIL_TOKEN_FILE", "token.json")
    scopes_env = os.getenv("GMAIL_SCOPES", "")
    scopes = scopes_env.split() if scopes_env else SCOPES

    if not client_id or not client_secret:
        sys.stderr.write("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in env.\n")
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.stderr.write(
            "google-auth-oauthlib is required: pip install google-auth-oauthlib\n"
        )
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
    try:
        creds = flow.run_local_server(port=0, open_browser=True)
    except AttributeError:
        creds = flow.run_console()

    Path(token_path).write_text(creds.to_json(), encoding="utf-8")
    print(f"Saved Gmail OAuth token to {token_path}")


if __name__ == "__main__":
    obtain_oauth_token()
