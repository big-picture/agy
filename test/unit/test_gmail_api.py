"""Unit tests for Gmail API helper module."""

from __future__ import annotations

import base64
from unittest.mock import Mock

import pytest

from agy.integrations.email._gmail_api import GmailAPI, GmailFetcher, _as_dict, _as_str


def test_as_helpers() -> None:
    assert _as_dict({"a": 1}) == {"a": 1}
    assert _as_dict("x") == {}
    assert _as_str("x") == "x"
    assert _as_str(None, "d") == "d"


def test_extract_body_handles_nested_parts() -> None:
    api = GmailAPI.__new__(GmailAPI)
    nested = base64.urlsafe_b64encode(b"hello world").decode()
    payload = {
        "parts": [
            {"mimeType": "application/pdf", "body": {}},
            {
                "mimeType": "multipart/alternative",
                "parts": [{"mimeType": "text/plain", "body": {"data": nested}}],
            },
        ]
    }
    assert api._extract_body(payload) == "hello world"


def test_get_message_body_returns_none_when_message_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = GmailAPI.__new__(GmailAPI)
    monkeypatch.setattr(api, "get_message", lambda _mid: None)
    assert api.get_message_body("id1") is None


def test_get_label_id_by_name_no_create_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = GmailAPI.__new__(GmailAPI)
    monkeypatch.setattr(api, "_find_label", lambda _name: (None, {}))
    assert api.get_label_id_by_name("X", create_if_missing=False) is None


def test_gmail_fetcher_message_to_dict_strips_html() -> None:
    fetcher = GmailFetcher.__new__(GmailFetcher)
    fetcher.gmail_api = Mock()
    fetcher.gmail_api._extract_body.return_value = "<b>Body</b>"
    message = {
        "id": "1",
        "threadId": "t1",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "a@example.com"},
                {"name": "To", "value": "b@example.com"},
                {"name": "Subject", "value": "s"},
            ],
        },
    }
    as_dict = fetcher._message_to_dict(message)
    assert as_dict["message_id"] == "1"
    assert as_dict["from_address"] == "a@example.com"
    assert as_dict["text"] == "Body"


def test_gmail_fetcher_list_message_ids_handles_exception() -> None:
    fetcher = GmailFetcher.__new__(GmailFetcher)
    fetcher.gmail_api = Mock()
    fetcher.gmail_api._user = "me"
    fetcher.gmail_api._service.users().messages().list().execute.side_effect = (
        RuntimeError("boom")
    )
    assert fetcher._list_message_ids(only_unread=False, max_results=5) == []
