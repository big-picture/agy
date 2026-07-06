"""Tests for object-first Jira integration (atlassian-python-api backend)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from agy.action_executor import ActionExecutor, ActionRegistry
from agy.ast_parser import parse_action_with_ast
from agy.integrations.jira import JiraClient, JiraComment, JiraIssue
from agy.integrations.jira.client import _issue_from_dict


def _issue_dict(
    key: str = "PROJ-1",
    summary: str = "Test summary",
    status: str = "Open",
    labels: list[str] | None = None,
    description: str = "",
) -> dict[str, Any]:
    """Build issue as dict (atlassian get_issue style)."""
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "status": {"name": status},
            "issuetype": {"name": "Task"},
            "assignee": {"displayName": "Alice"},
            "reporter": {"displayName": "bob"},
            "description": description,
            "labels": labels or [],
        },
    }


def test_jira_issue_from_dict_populates_extra_fields_without_mapping() -> None:
    """Unmapped, non-None custom fields are collected in extra_fields."""
    issue_data = _issue_dict("PROJ-99", "Has custom fields", "Open")
    issue_data["fields"]["customfield_10010"] = "partner-x"
    issue_data["fields"]["customfield_10011"] = 42
    issue_data["fields"]["customfield_10012"] = None

    issue = _issue_from_dict(issue_data)

    assert issue.extra_fields["customfield_10010"] == "partner-x"
    assert issue.extra_fields["customfield_10011"] == 42
    assert "customfield_10012" not in issue.extra_fields


def test_jira_issue_from_dict_with_mapping_uses_canonical_extra_keys() -> None:
    """Mapping renames custom field keys in extra_fields."""
    issue_data = _issue_dict("PROJ-100", "Mapped fields", "Open")
    issue_data["fields"]["customfield_17107"] = "Kurt Rothschild GmbH"

    issue = _issue_from_dict(
        issue_data, field_mapping={"customfield_17107": "tsp_name"}
    )

    assert issue.extra_fields["tsp_name"] == "Kurt Rothschild GmbH"
    assert "customfield_17107" not in issue.extra_fields


@dataclass(slots=True)
class _MappedIssue(JiraIssue):
    tsp_name: str = ""


def test_jira_issue_from_dict_with_subclass_routes_mapped_attr() -> None:
    """Mapped canonical key is assigned to matching subclass attribute."""
    issue_data = _issue_dict("PROJ-101", "Subclass", "Open")
    issue_data["fields"]["customfield_17107"] = "Transport Partner"
    issue_data["fields"]["customfield_17103"] = "[Link|http://example.com]"

    issue = _issue_from_dict(
        issue_data,
        field_mapping={"customfield_17107": "tsp_name"},
        issue_cls=_MappedIssue,
    )

    assert issue.tsp_name == "Transport Partner"
    assert issue.extra_fields["customfield_17103"] == "[Link|http://example.com]"
    assert "customfield_17107" not in issue.extra_fields


def test_jira_issue_classmethod_from_dict_supports_subclass_mapping() -> None:
    """JiraIssue.from_dict() should return subclass instance when called on subclass."""
    issue_data = _issue_dict("PROJ-102", "From dict", "Open")
    issue_data["fields"]["customfield_17107"] = "Partner A"

    issue = _MappedIssue.from_dict(
        issue_data, field_mapping={"customfield_17107": "tsp_name"}
    )

    assert isinstance(issue, _MappedIssue)
    assert issue.tsp_name == "Partner A"


@pytest.mark.asyncio
async def test_jira_get_issue_via_ast_context_object() -> None:
    """Jira object methods can be executed through AST actions."""
    issue = _issue_dict("CCM-1438", "Fix login", "In Progress", ["backend", "auth"])
    fake_client = MagicMock()
    fake_client.get_issue.return_value = issue
    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )

    executor = ActionExecutor(ActionRegistry())
    context: dict[str, Any] = {"jira": jira}

    action_call = parse_action_with_ast("issue = jira.get_issue('CCM-1438')")
    await executor.execute(action_call, context)

    assert context["success"] is True
    assert context["issue"].key == "CCM-1438"
    assert context["issue"].summary == "Fix login"
    assert context["issue"].status == "In Progress"
    assert context["issue"].labels == ["backend", "auth"]


def test_jira_from_env_missing_raises() -> None:
    """Missing JIRA env vars should raise a clear error."""
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("JIRA_URL", raising=False)
        mp.delenv("JIRA_TOKEN", raising=False)
        with pytest.raises(ValueError, match="JIRA_URL and JIRA_TOKEN"):
            JiraClient.from_env()


def test_jira_transitions_mapping_dict_and_object() -> None:
    """Transitions are normalized for both dict and object API shapes."""
    fake_client = MagicMock()
    fake_client.get_issue_transitions.return_value = [
        {"name": "Start", "id": 21, "to": "In Progress"},
        {"name": "Finish", "id": 31, "to": "Done"},
        {"name": "Unknown", "id": 41, "to": None},
    ]

    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    transitions = jira.transitions("PROJ-1")

    assert len(transitions) == 3
    assert transitions[0].name == "Start"
    assert transitions[0].to_status == "In Progress"
    assert transitions[1].name == "Finish"
    assert transitions[1].to_status == "Done"
    assert transitions[2].to_status == "?"


def test_jira_create_issue_without_description() -> None:
    """Description is optional and not sent when omitted."""
    fake_client = MagicMock()
    fake_client.create_issue.return_value = {"key": "PROJ-2"}
    fake_client.get_issue.return_value = _issue_dict("PROJ-2", "New task", "Open")

    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    created = jira.create_issue(project="PROJ", summary="New task", issuetype="Task")

    assert created.key == "PROJ-2"
    call_fields = fake_client.create_issue.call_args.kwargs["fields"]
    assert "description" not in call_fields
    assert call_fields["project"] == {"key": "PROJ"}
    assert call_fields["summary"] == "New task"


def test_jira_create_issue_with_extra_fields() -> None:
    """Arbitrary extra fields are forwarded to Jira."""
    fake_client = MagicMock()
    fake_client.create_issue.return_value = {"key": "PROJ-3"}
    fake_client.get_issue.return_value = _issue_dict("PROJ-3", "Extra", "Open")

    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    jira.create_issue(
        project="PROJ",
        summary="Extra",
        issuetype="Task",
        labels=["backend"],
        custom_field=123,
    )

    call_fields = fake_client.create_issue.call_args.kwargs["fields"]
    assert call_fields["labels"] == ["backend"]
    assert call_fields["custom_field"] == 123


def test_jira_update_issue_no_payload_skips_update() -> None:
    """No update payload should not call issue_update."""
    fake_client = MagicMock()
    fake_client.get_issue.return_value = _issue_dict("PROJ-1", "Base", "Open")

    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    updated = jira.update_issue("PROJ-1")

    assert updated.key == "PROJ-1"
    fake_client.issue_update.assert_not_called()


def test_jira_update_issue_combines_fields() -> None:
    """Provided fields and convenience args are merged."""
    fake_client = MagicMock()
    fake_client.get_issue.return_value = _issue_dict("PROJ-1", "New", "Open")

    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    jira.update_issue(
        "PROJ-1", fields={"labels": ["x"]}, summary="New", description="Body"
    )

    fake_client.issue_update.assert_called_once_with(
        "PROJ-1", {"labels": ["x"], "summary": "New", "description": "Body"}
    )


def test_jira_assign_transition_and_delete_delegate() -> None:
    """Assign, transition and delete call atlassian API. Transition by name resolved to ID."""
    fake_client = MagicMock()
    fake_client.get_issue.return_value = _issue_dict("PROJ-1", "Base", "Open")
    fake_client.get_issue_transitions.return_value = [
        {"id": 31, "name": "Done", "to": "Done"}
    ]

    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    jira.assign("PROJ-1", "alice")
    jira.transition("PROJ-1", "Done")
    jira.delete_issue("PROJ-1")

    fake_client.assign_issue.assert_called_once_with("PROJ-1", "alice")
    fake_client.set_issue_status_by_transition_id.assert_called_once_with("PROJ-1", 31)
    fake_client.delete_issue.assert_called_once_with("PROJ-1")


def test_jira_transition_with_screen_payload_posts_full_body() -> None:
    """Transition with fields/update uses POST /transitions; does not use set_issue_status_by_transition_id."""
    fake_client = MagicMock()
    fake_client.resource_url.return_value = "https://jira.example.com/rest/api/2"
    fake_client.get_issue_transitions.return_value = [
        {"id": 42, "name": "Send E-Mail", "to": "In Progress"}
    ]

    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    jira.transition(
        "PROJ-1",
        "Send E-Mail",
        fields={"customfield_11221": "partner@example.com"},
        update={"comment": [{"add": {"body": "Plain mail body"}}]},
    )

    fake_client.set_issue_status_by_transition_id.assert_not_called()
    fake_client.post.assert_called_once()
    pos_args, kw = fake_client.post.call_args
    assert pos_args and "PROJ-1/transitions" in pos_args[0]
    assert kw["data"] == {
        "transition": {"id": 42},
        "fields": {"customfield_11221": "partner@example.com"},
        "update": {"comment": [{"add": {"body": "Plain mail body"}}]},
    }


def test_jira_transition_by_id_passthrough() -> None:
    """Numeric transition is passed through as ID without calling get_issue_transitions."""
    fake_client = MagicMock()

    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    jira.transition("PROJ-1", "31")

    fake_client.set_issue_status_by_transition_id.assert_called_once_with("PROJ-1", 31)
    fake_client.get_issue_transitions.assert_not_called()


def test_jira_transition_name_not_found_raises() -> None:
    """Transition by unknown name raises ValueError with available names."""
    fake_client = MagicMock()
    fake_client.get_issue_transitions.return_value = [
        {"id": 21, "name": "In Progress", "to": "In Progress"}
    ]

    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    with pytest.raises(
        ValueError, match="Transition 'Done' not found.*Available:.*In Progress"
    ):
        jira.transition("PROJ-1", "Done")


def test_jira_add_comment_returns_business_object() -> None:
    """add_comment returns JiraComment; atlassian returns dict."""
    fake_client = MagicMock()
    fake_client.issue_add_comment.return_value = {
        "id": "12345",
        "body": "Hello",
        "created": "2026-03-24T10:00:00.000+0000",
        "author": {"displayName": "Alice"},
    }

    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    result = jira.add_comment("PROJ-1", "Hello")

    assert isinstance(result, JiraComment)
    assert result.id == "12345"
    assert result.body == "Hello"
    assert result.created == "2026-03-24T10:00:00.000+0000"
    assert result.author == "Alice"


def test_jira_get_comments_returns_sorted_business_objects() -> None:
    """get_comments returns JiraComment list sorted by created descending."""
    fake_client = MagicMock()
    fake_client.issue_get_comments.return_value = {
        "comments": [
            {"id": "1", "body": "old", "created": "2026-03-24T09:00:00.000+0000"},
            {
                "id": "2",
                "body": "new",
                "created": "2026-03-24T10:00:00.000+0000",
            },
        ]
    }
    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )

    comments = jira.get_comments("PROJ-1")

    assert [c.id for c in comments] == ["2", "1"]
    assert all(isinstance(c, JiraComment) for c in comments)


def test_jira_issue_comment_methods_delegate_to_bound_client() -> None:
    """Issue-level add_comment/get_comments use bound client and sort newest first."""
    fake_client = MagicMock()
    fake_client.get_issue.return_value = _issue_dict("PROJ-10", "Issue", "Open")
    fake_client.issue_add_comment.return_value = {
        "id": "123",
        "body": "From issue",
        "created": "2026-03-24T11:00:00.000+0000",
    }
    fake_client.issue_get_comments.return_value = {
        "comments": [
            {"id": "11", "body": "older", "created": "2026-03-24T10:00:00.000+0000"},
            {"id": "12", "body": "newer", "created": "2026-03-24T12:00:00.000+0000"},
        ]
    }
    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    issue = jira.get_issue("PROJ-10")

    new_comment = issue.add_comment("From issue")
    comments = issue.get_comments()

    assert new_comment.id == "123"
    assert [c.id for c in comments] == ["12", "11"]
    fake_client.issue_add_comment.assert_called_once_with("PROJ-10", "From issue")
    fake_client.issue_get_comments.assert_called_once_with("PROJ-10")


def test_jira_issue_comment_methods_require_bound_client() -> None:
    """Issue-level comment methods should fail for unbound JiraIssue instances."""
    issue = JiraIssue(key="PROJ-404")

    with pytest.raises(ValueError, match="not bound to a JiraClient"):
        issue.add_comment("x")
    with pytest.raises(ValueError, match="not bound to a JiraClient"):
        issue.get_comments()
    with pytest.raises(ValueError, match="not bound to a JiraClient"):
        issue.append_to_description("x")
    with pytest.raises(ValueError, match="not bound to a JiraClient"):
        issue.add_subtask("Subtask title")


def test_jira_issue_append_to_description_bottom_default() -> None:
    """Description text is appended at bottom by default."""
    fake_client = MagicMock()
    fake_client.get_issue.side_effect = [
        _issue_dict("PROJ-20", "Issue", "Open", description="Existing"),
        _issue_dict("PROJ-20", "Issue", "Open", description="Existing\n\nAppended"),
    ]
    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    issue = JiraIssue(key="PROJ-20")._bind_client(jira)

    updated = issue.append_to_description("Appended")

    fake_client.issue_update.assert_called_once_with(
        "PROJ-20", {"description": "Existing\n\nAppended"}
    )
    assert updated.description == "Existing\n\nAppended"


def test_jira_issue_append_to_description_top() -> None:
    """Description text is prepended when position is TOP."""
    fake_client = MagicMock()
    fake_client.get_issue.side_effect = [
        _issue_dict("PROJ-21", "Issue", "Open", description="Existing"),
        _issue_dict("PROJ-21", "Issue", "Open", description="Prepended\n\nExisting"),
    ]
    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    issue = JiraIssue(key="PROJ-21")._bind_client(jira)

    updated = issue.append_to_description("Prepended", position="TOP")

    fake_client.issue_update.assert_called_once_with(
        "PROJ-21", {"description": "Prepended\n\nExisting"}
    )
    assert updated.description == "Prepended\n\nExisting"


def test_jira_issue_add_subtask_uses_parent_and_default_issue_type() -> None:
    """Sub-task creation sends Jira parent linkage and default issue type."""
    fake_client = MagicMock()
    fake_client.create_issue.return_value = {"key": "PROJ-301"}
    fake_client.get_issue.return_value = _issue_dict("PROJ-301", "Child", "Open")
    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    issue = JiraIssue(key="PROJ-300")._bind_client(jira)

    child = issue.add_subtask("Child issue", description="Child description")

    assert child.key == "PROJ-301"
    call_fields = fake_client.create_issue.call_args.kwargs["fields"]
    assert call_fields["project"] == {"key": "PROJ"}
    assert call_fields["summary"] == "Child issue"
    assert call_fields["issuetype"] == {"name": "Sub-task"}
    assert call_fields["description"] == "Child description"
    assert call_fields["parent"] == {"key": "PROJ-300"}


def test_jira_issue_add_subtask_accepts_subtask_alias() -> None:
    """Alias 'subtask' is normalized to Jira's 'Sub-task' issue type."""
    fake_client = MagicMock()
    fake_client.create_issue.return_value = {"key": "PROJ-401"}
    fake_client.get_issue.return_value = _issue_dict("PROJ-401", "Child", "Open")
    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )
    issue = JiraIssue(key="PROJ-400")._bind_client(jira)

    issue.add_subtask("Child issue", issue_type="subtask")

    call_fields = fake_client.create_issue.call_args.kwargs["fields"]
    assert call_fields["issuetype"] == {"name": "Sub-task"}


def test_jira_search_issues_defaults() -> None:
    """Search uses jql with start/limit; returns list from response['issues']."""
    fake_client = MagicMock()
    fake_client.jql.return_value = {"issues": []}
    jira = JiraClient(
        server_url="https://jira.example.com", token="token", client=fake_client
    )

    result = jira.search_issues("assignee = currentUser()")

    assert result == []
    fake_client.jql.assert_called_once_with(
        "assignee = currentUser()", start=0, limit=50
    )
