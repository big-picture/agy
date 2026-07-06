"""Shared HTML/text helpers for email integrations."""

from __future__ import annotations

import html


def plain_to_html(text: str) -> str:
    """Escape and preserve paragraph breaks for plain text bodies."""
    escaped = html.escape((text or "").replace("\r\n", "\n"))
    escaped = escaped.replace("\n\n", "<br/><br/>")
    escaped = escaped.replace("\n", "<br/>")
    return escaped
