"""Email integration module.

Public API:
    Email - Email dataclass with bound account methods
    Attachment - Email attachment dataclass
    EmailBodyType - Body format of Email.text (text or html)
    EmailAccount - Abstract base class for email accounts
    EmailSendError - Base outbound error (subclass of RuntimeError)
    EmailTransientError - Retryable outbound error (status_code, retry_after)
    EmailPermanentError - Non-retryable outbound error (status_code)
    EmailSafetyError - Recipient rejected by the safety allowlist
    GraphEmailAccount - Microsoft Graph implementation
    GraphWellKnownFolder - Microsoft Graph system folder names
    GmailEmailAccount - Gmail implementation
    ImapSmtpEmailAccount - Generic IMAP/SMTP implementation
    MockEmailAccount - File-based mock implementation
"""

from __future__ import annotations

from .account import EmailAccount
from .email import Attachment, Email, EmailBodyType
from .errors import (
    EmailPermanentError,
    EmailSafetyError,
    EmailSendError,
    EmailTransientError,
)
from .mock_account import MockEmailAccount

# Provider-specific accounts are imported lazily to keep optional dependencies
# (e.g., google-auth) from breaking lightweight imports like MockEmailAccount.
_LAZY_EXPORTS = {
    "GraphEmailAccount": ".graph_account",
    "GraphWellKnownFolder": "._graph_api",
    "GmailEmailAccount": ".gmail_account",
    "ImapSmtpEmailAccount": ".imap_smtp_account",
}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        import importlib

        module = importlib.import_module(_LAZY_EXPORTS[name], __name__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Email",
    "Attachment",
    "EmailBodyType",
    "EmailAccount",
    "EmailSendError",
    "EmailTransientError",
    "EmailPermanentError",
    "EmailSafetyError",
    "GraphEmailAccount",
    "GraphWellKnownFolder",
    "GmailEmailAccount",
    "ImapSmtpEmailAccount",
    "MockEmailAccount",
]
