"""Email integration module.

Public API:
    Email - Email dataclass with bound account methods
    Attachment - Email attachment dataclass
    EmailAccount - Abstract base class for email accounts
    GraphEmailAccount - Microsoft Graph implementation
    GmailEmailAccount - Gmail implementation
    ImapSmtpEmailAccount - Generic IMAP/SMTP implementation
    MockEmailAccount - File-based mock implementation
"""

from __future__ import annotations

from .account import EmailAccount
from .email import Attachment, Email
from .mock_account import MockEmailAccount

# Provider-specific accounts are imported lazily to keep optional dependencies
# (e.g., google-auth) from breaking lightweight imports like MockEmailAccount.
_LAZY_EXPORTS = {
    "GraphEmailAccount": ".graph_account",
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
    "EmailAccount",
    "GraphEmailAccount",
    "GmailEmailAccount",
    "ImapSmtpEmailAccount",
    "MockEmailAccount",
]
