"""Additional branch tests for ImapSmtpEmailAccount helpers."""

from __future__ import annotations

import email
from email.message import EmailMessage

from agy.integrations.email.imap_smtp_account import (
    _decode_header_value,
    _get_email_body,
    _payload_to_bytes,
)


def test_payload_to_bytes_for_string_and_none() -> None:
    assert _payload_to_bytes("hello") == b"hello"
    assert _payload_to_bytes(None) == b""


def test_decode_header_value_handles_encoded() -> None:
    assert "Test" in _decode_header_value("=?utf-8?b?VGVzdA==?=")


def test_get_email_body_prefers_text_plain() -> None:
    msg = EmailMessage()
    msg.set_content("plain body")
    msg.add_alternative("<b>html body</b>", subtype="html")
    parsed = email.message_from_bytes(msg.as_bytes())
    body, body_type = _get_email_body(parsed)
    assert "plain body" in body
    assert body_type == "text"


def test_get_email_body_returns_html_when_no_plain() -> None:
    msg = EmailMessage()
    msg.add_alternative("<b>html only</b>", subtype="html")
    parsed = email.message_from_bytes(msg.as_bytes())
    body, body_type = _get_email_body(parsed)
    assert "html only" in body
    assert body_type == "html"


def test_get_email_body_non_multipart() -> None:
    msg = EmailMessage()
    msg.set_content("single")
    parsed = email.message_from_bytes(msg.as_bytes())
    body, body_type = _get_email_body(parsed)
    assert "single" in body
    assert body_type == "text"


def test_decode_header_value_empty() -> None:
    assert _decode_header_value(None) == ""
