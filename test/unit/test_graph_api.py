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


_CANONICAL_WELL_KNOWN_FOLDER_NAMES = (
    "archive",
    "clutter",
    "conflicts",
    "conversationhistory",
    "deleteditems",
    "drafts",
    "inbox",
    "junkemail",
    "localfailures",
    "msgfolderroot",
    "outbox",
    "recoverableitemsdeletions",
    "scheduled",
    "searchfolders",
    "sentitems",
    "serverfailures",
    "syncissues",
)


def _make_api() -> GraphAPI:
    return GraphAPI(tenant_id="t", client_id="c", client_secret="s", mailbox_upn="u")


@pytest.mark.parametrize("folder_name", _CANONICAL_WELL_KNOWN_FOLDER_NAMES)
def test_get_folder_by_reference_supports_every_canonical_well_known_name(
    monkeypatch: pytest.MonkeyPatch,
    folder_name: str,
) -> None:
    api = _make_api()
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    captured: dict[str, str] = {}

    def fake_get(url: str, *args, **kwargs):
        captured["url"] = url
        return _resp(
            200,
            data={"id": f"id-{folder_name}", "displayName": folder_name.title()},
        )

    monkeypatch.setattr(requests, "get", fake_get)

    folder = api.get_folder_by_reference(folder_name, mailbox_upn="u")

    assert folder == {
        "id": f"id-{folder_name}",
        "displayName": folder_name.title(),
    }
    assert captured["url"].endswith(f"/mailFolders/{folder_name}")


@pytest.mark.parametrize(
    ("alias", "canonical_name", "display_name"),
    [
        ("sent", "sentitems", "Gesendete Elemente"),
        ("Sent Items", "sentitems", "Gesendete Elemente"),
        ("Gesendete Elemente", "sentitems", "Gesendete Elemente"),
        ("trash", "deleteditems", "Gelöschte Elemente"),
        ("Entwürfe", "drafts", "Entwürfe"),
        ("Postausgang", "outbox", "Postausgang"),
    ],
)
def test_get_folder_by_reference_normalizes_existing_aliases(
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
    canonical_name: str,
    display_name: str,
) -> None:
    api = _make_api()
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    captured: dict[str, str] = {}

    def fake_get(url: str, *args, **kwargs):
        captured["url"] = url
        return _resp(200, data={"id": f"id-{canonical_name}", "displayName": display_name})

    monkeypatch.setattr(requests, "get", fake_get)

    folder = api.get_folder_by_reference(alias, mailbox_upn="u")

    assert folder == {"id": f"id-{canonical_name}", "displayName": display_name}
    assert captured["url"].endswith(f"/mailFolders/{canonical_name}")


def test_get_folder_by_reference_falls_back_to_display_name_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _make_api()
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    responses = [
        _resp(404, text="not found"),
        _resp(
            200,
            data={
                "value": [
                    {"id": "inbox-id", "displayName": "Posteingang"},
                ]
            },
        ),
    ]
    requested_urls: list[str] = []

    def fake_get(url: str, *args, **kwargs):
        requested_urls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(requests, "get", fake_get)

    folder = api.get_folder_by_reference("Posteingang", mailbox_upn="u")

    assert folder == {"id": "inbox-id", "displayName": "Posteingang"}
    assert requested_urls[0].endswith("/mailFolders/inbox")
    assert requested_urls[1].endswith("/mailFolders")
    assert responses == []


def test_get_folder_id_by_name_delegates_and_returns_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _make_api()
    monkeypatch.setattr(
        api,
        "get_folder_by_reference",
        lambda *args, **kwargs: {"id": "folder-1", "displayName": "Deleted Items"},
    )
    assert api.get_folder_id_by_name("trash", mailbox_upn="u") == "folder-1"

    monkeypatch.setattr(api, "get_folder_by_reference", lambda *args, **kwargs: None)
    assert api.get_folder_id_by_name("missing", mailbox_upn="u") is None

    monkeypatch.setattr(
        api,
        "get_folder_by_reference",
        lambda *args, **kwargs: {"displayName": "No Id"},
    )
    assert api.get_folder_id_by_name("broken", mailbox_upn="u") is None


def test_get_folder_id_by_name_applies_alias_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _make_api()
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


def test_get_folder_by_reference_resolves_nested_display_name_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _make_api()
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    responses = [
        _resp(200, data={"value": [{"id": "projects-id", "displayName": "Projects"}]}),
        _resp(200, data={"value": [{"id": "active-id", "displayName": "Active"}]}),
    ]

    def fake_get(url: str, *args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(requests, "get", fake_get)

    folder = api.get_folder_by_reference("Projects/Active", mailbox_upn="u")
    assert folder == {"id": "active-id", "displayName": "Active"}


def test_get_folder_by_reference_follows_graph_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _make_api()
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    page1 = _resp(
        200,
        data={
            "value": [{"id": "other-id", "displayName": "Other"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
        },
    )
    page2 = _resp(
        200,
        data={"value": [{"id": "target-id", "displayName": "Target"}]},
    )
    responses = [page1, page2]

    def fake_get(url: str, *args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(requests, "get", fake_get)

    folder = api.get_folder_by_reference("Target", mailbox_upn="u")
    assert folder == {"id": "target-id", "displayName": "Target"}
    assert responses == []


def test_get_folder_by_reference_returns_none_for_missing_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _make_api()
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _resp(
            200, data={"value": [{"id": "other-id", "displayName": "Other"}]}
        ),
    )
    assert api.get_folder_by_reference("Missing", mailbox_upn="u") is None


def test_get_folder_by_reference_returns_none_on_request_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _make_api()
    monkeypatch.setattr(
        api, "_get_headers", lambda force_refresh_token=False: {"x": "y"}
    )

    def raise_error(*args, **kwargs):
        raise requests.exceptions.RequestException("network down")

    monkeypatch.setattr(requests, "get", raise_error)
    assert api.get_folder_by_reference("Projects", mailbox_upn="u") is None


def test_get_folder_by_reference_rejects_invalid_mailbox_type() -> None:
    api = _make_api()
    with pytest.raises(ValueError, match="Unknown mailbox_type"):
        api.get_folder_by_reference("inbox", mailbox_type="invalid", mailbox_upn="u")


def test_get_folder_by_reference_shared_requires_upn() -> None:
    api = GraphAPI(tenant_id="t", client_id="c", client_secret="s")
    with pytest.raises(ValueError, match="mailbox_upn required for shared mailbox"):
        api.get_folder_by_reference("inbox", mailbox_type="shared")


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
