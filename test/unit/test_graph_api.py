"""Unit tests for GraphAPI helper module."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from agy.integrations.email._graph_api import (
    GraphAPI,
    _json_dict,
    _json_str,
    _messages_base,
)


def _resp(status: int, data: dict | list | None = None, text: str = "") -> Mock:
    resp = Mock()
    resp.status_code = status
    resp.text = text
    resp.json.return_value = data if data is not None else {}
    return resp


def test_json_helpers_handle_non_dict_payload() -> None:
    resp = _resp(200, data=["x"])
    assert _json_dict(resp) == {}
    assert _json_str(resp, "access_token") is None


def test_init_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TENANT_ID", raising=False)
    monkeypatch.delenv("CLIENT_ID", raising=False)
    monkeypatch.delenv("CLIENT_SECRET", raising=False)
    with pytest.raises(ValueError, match="Missing required credentials"):
        GraphAPI()


def test_get_access_token_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    api = GraphAPI(tenant_id="t", client_id="c", client_secret="s", mailbox_upn="u")
    api._cached_token = "cached"
    assert api._get_access_token() == "cached"


def test_get_graph_access_token_with_retry_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = GraphAPI(tenant_id="t", client_id="c", client_secret="s")
    calls = [_resp(500, text="error"), _resp(200, data={"access_token": "token123"})]
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: calls.pop(0))
    monkeypatch.setattr("time.sleep", lambda *_: None)
    assert api._get_graph_access_token_with_retry(max_retries=2) == "token123"


def test_move_message_returns_none_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = GraphAPI(tenant_id="t", client_id="c", client_secret="s", mailbox_upn="u")
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    monkeypatch.setattr(
        requests, "post", lambda *args, **kwargs: _resp(400, text="bad")
    )
    assert (
        api.move_message("m1", "dest", mailbox_type="personal", mailbox_upn="u") is None
    )


def test_move_message_returns_moved_message_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = GraphAPI(tenant_id="t", client_id="c", client_secret="s", mailbox_upn="u")
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: _resp(201, data={"id": "moved-1", "isRead": False}),
    )
    assert api.move_message("m1", "dest", mailbox_type="personal", mailbox_upn="u") == {
        "id": "moved-1",
        "isRead": False,
    }


def test_get_folder_id_by_name_applies_alias_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = GraphAPI(tenant_id="t", client_id="c", client_secret="s", mailbox_upn="u")
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _resp(
            200,
            data={"id": "folder-1", "displayName": "Deleted Items"},
        ),
    )
    assert api.get_folder_id_by_name("trash", mailbox_upn="u") == "folder-1"


def test_get_message_body_success_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    api = GraphAPI(tenant_id="t", client_id="c", client_secret="s", mailbox_upn="u")
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _resp(200, data={"body": {"content": "ok"}}),
    )
    assert api.get_message_body("m1", mailbox_upn="u") == "ok"

    monkeypatch.setattr(
        requests, "get", lambda *args, **kwargs: _resp(500, text="oops")
    )
    assert api.get_message_body("m1", mailbox_upn="u") is None


def test_get_message_categories_success(monkeypatch: pytest.MonkeyPatch) -> None:
    api = GraphAPI(tenant_id="t", client_id="c", client_secret="s", mailbox_upn="u")
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _resp(
            200, data={"categories": ["Existing", "Erledigt"]}
        ),
    )
    assert api.get_message_categories("m1", mailbox_upn="u") == [
        "Existing",
        "Erledigt",
    ]


def test_update_message_categories_success(monkeypatch: pytest.MonkeyPatch) -> None:
    api = GraphAPI(tenant_id="t", client_id="c", client_secret="s", mailbox_upn="u")
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    monkeypatch.setattr(
        requests, "patch", lambda *args, **kwargs: _resp(200, data={})
    )
    assert api.update_message_categories("m1", ["Erledigt"], mailbox_upn="u") is True


def test_messages_base_shared_requires_upn() -> None:
    assert _messages_base("shared", None) is None
    with pytest.raises(ValueError):
        _messages_base("invalid", None)
