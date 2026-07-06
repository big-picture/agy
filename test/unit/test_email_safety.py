"""Unit tests for email safety validator."""

from __future__ import annotations

from agy.integrations.email.email_safety import EmailSafetyValidator


def test_extract_domain_from_bracketed_address() -> None:
    assert (
        EmailSafetyValidator.extract_domain("John Doe <john@big-picture.com>")
        == "big-picture.com"
    )


def test_validate_recipient_rejects_disallowed_domain() -> None:
    v = EmailSafetyValidator(allowed_domains=["allowed.com"], allowed_addresses=[])
    is_valid, msg = v.validate_recipient("a@blocked.com")
    assert is_valid is False
    assert "not allowed" in msg


def test_validate_recipient_accepts_allowed_address() -> None:
    v = EmailSafetyValidator(allowed_domains=[], allowed_addresses=["special@x.com"])
    is_valid, msg = v.validate_recipient("special@x.com")
    assert is_valid is True
    assert msg == ""
