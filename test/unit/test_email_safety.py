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


# ---------------------------------------------------------------------------
# validate_recipients (per-address)
# ---------------------------------------------------------------------------


def _allow(domains: list[str], addresses: list[str] | None = None):
    return EmailSafetyValidator(
        allowed_domains=domains, allowed_addresses=addresses or []
    )


def test_validate_recipients_accepts_all_allowed_addresses() -> None:
    v = _allow(["allowed.com"])
    assert v.validate_recipients(
        ["a@allowed.com", " Jane Doe <b@Allowed.com> ", "c@allowed.com "]
    ) == (True, "")


def test_validate_recipients_rejects_if_any_address_disallowed() -> None:
    v = _allow(["allowed.com"])
    is_valid, msg = v.validate_recipients(["a@allowed.com", "x@blocked.com"])
    assert is_valid is False
    assert "x@blocked.com" in msg
    assert "blocked.com" in msg


def test_validate_recipients_rejects_disallowed_first_of_comma_joined() -> None:
    """Regression: the joined string used to be checked by its last domain only."""
    v = _allow(["allowed.com"])
    assert v.validate_recipient("x@blocked.com, a@allowed.com")[0] is True  # legacy
    is_valid, msg = v.validate_recipients(["x@blocked.com, a@allowed.com"])
    assert is_valid is False
    assert "x@blocked.com" in msg


def test_validate_recipients_matches_named_explicit_address() -> None:
    v = _allow([], ["vip@partner.com"])
    assert v.validate_recipients(["VIP <vip@partner.com>"]) == (True, "")


def test_validate_recipients_skips_blank_entries() -> None:
    v = _allow(["allowed.com"])
    assert v.validate_recipients(["a@allowed.com", "", " , "]) == (True, "")


def test_validate_recipients_requires_at_least_one_address() -> None:
    v = _allow(["allowed.com"])
    assert v.validate_recipients([])[0] is False
    assert v.validate_recipients(["", " "])[0] is False


def test_validate_recipients_rejects_invalid_format() -> None:
    v = _allow(["allowed.com"])
    is_valid, msg = v.validate_recipients(["not-an-address"])
    assert is_valid is False
    assert "Invalid email address format" in msg


def test_validate_recipients_accepts_generator() -> None:
    v = _allow(["allowed.com"])
    assert v.validate_recipients(a for a in ["a@allowed.com"])[0] is True


def test_single_address_methods_unchanged() -> None:
    v = _allow(["allowed.com"])
    assert v.validate_forward("a@allowed.com") == (True, "")
    assert v.validate_reply("a@allowed.com") == (True, "")
    assert v.validate_recipient("x@blocked.com")[0] is False
