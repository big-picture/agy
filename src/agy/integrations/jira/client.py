"""Thin wrapper around atlassian-python-api (atlassian.Jira) for flow usage.

All methods delegate to the underlying atlassian client; only response shape is
converted to AGY domain models (JiraIssue, JiraTransition, JiraComment).
"""

from __future__ import annotations

import os
from dataclasses import fields as dataclass_fields
from typing import Any

from .models import JiraComment, JiraIssue, JiraTransition

_KNOWN_FIELDS = frozenset(
    {
        "summary",
        "status",
        "issuetype",
        "assignee",
        "reporter",
        "description",
        "labels",
    }
)

_RESERVED_ISSUE_ATTRS = frozenset(
    {
        "key",
        "summary",
        "status",
        "issuetype",
        "assignee",
        "reporter",
        "description",
        "labels",
        "extra_fields",
    }
)


def _issue_from_dict(
    data: dict[str, Any],
    *,
    field_mapping: dict[str, str] | None = None,
    issue_cls: type[JiraIssue] = JiraIssue,
    jira_client: JiraClient | None = None,
) -> JiraIssue:
    """Build JiraIssue from atlassian get_issue response (dict with key, fields)."""
    key = data.get("key", "")
    fields = data.get("fields") or {}
    summary = (fields.get("summary") or "").strip()
    status = ""
    if isinstance(fields.get("status"), dict):
        status = (fields.get("status") or {}).get("name", "")
    it = fields.get("issuetype")
    issuetype = it.get("name", "") if isinstance(it, dict) else ""
    assignee = None
    a = fields.get("assignee")
    if isinstance(a, dict):
        assignee = a.get("displayName") or a.get("name") or ""
    reporter = None
    r = fields.get("reporter")
    if isinstance(r, dict):
        reporter = r.get("displayName") or r.get("name") or ""
    description = (fields.get("description") or "").strip()
    raw_labels = fields.get("labels")
    labels = [str(v) for v in raw_labels] if isinstance(raw_labels, list) else []

    cls_field_names = {f.name for f in dataclass_fields(issue_cls)}
    extra_fields: dict[str, Any] = {}
    mapped_init_kwargs: dict[str, Any] = {}

    for raw_key, value in fields.items():
        if raw_key in _KNOWN_FIELDS or value is None:
            continue

        canonical = field_mapping.get(raw_key, raw_key) if field_mapping else raw_key

        # Never allow custom mappings to override core attributes.
        if canonical in _RESERVED_ISSUE_ATTRS:
            extra_fields[raw_key] = value
            continue

        if canonical in cls_field_names:
            mapped_init_kwargs[canonical] = value
        else:
            extra_fields[canonical] = value

    issue = issue_cls(
        key=key,
        summary=summary,
        status=status,
        issuetype=issuetype,
        assignee=assignee or None,
        reporter=reporter or None,
        description=description,
        labels=labels,
        extra_fields=extra_fields,
        **mapped_init_kwargs,
    )
    if jira_client is not None and hasattr(issue, "_bind_client"):
        issue._bind_client(jira_client)
    return issue


def _transition_from_dict(t: dict[str, Any]) -> JiraTransition:
    """Build JiraTransition from atlassian get_issue_transitions item (dict with name, id, to)."""
    name = str(t.get("name", ""))
    to_val = t.get("to")
    to_status = (
        to_val
        if isinstance(to_val, str)
        else (to_val.get("name", "?") if isinstance(to_val, dict) else "?")
    )
    return JiraTransition(name=name, to_status=to_status)


def _comment_from_dict(raw: dict[str, Any]) -> JiraComment:
    """Build JiraComment from atlassian comment payload dict."""
    author = raw.get("author")
    author_name: str | None = None
    if isinstance(author, dict):
        author_name = (
            author.get("displayName")
            or author.get("name")
            or author.get("emailAddress")
            or None
        )
    created = raw.get("created")
    created_str = str(created) if created is not None else ""
    return JiraComment(
        id=str(raw.get("id", "")),
        body=str(raw.get("body", "")),
        created=created_str,
        author=author_name,
    )


class JiraClient:
    """Thin wrapper around atlassian.Jira; exposes flow-friendly methods returning AGY models."""

    def __init__(
        self,
        *,
        server_url: str,
        token: str,
        user: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not server_url or not token:
            raise ValueError("server_url and token must be set")
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.user = (user or "").strip() or None
        self._client = client

    @classmethod
    def from_env(cls) -> JiraClient:
        url = os.getenv("JIRA_URL")
        token = os.getenv("JIRA_TOKEN")
        if not url or not token:
            raise ValueError(
                "JIRA_URL and JIRA_TOKEN must be set before using Jira integration."
            )
        return cls(
            server_url=url,
            token=token,
            user=(os.getenv("JIRA_USER") or "").strip() or None,
        )

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from atlassian import Jira
        except ImportError as exc:
            raise ValueError(
                "Jira integration requires 'atlassian-python-api', which is part "
                "of the standard agy install."
            ) from exc
        if self.user:
            self._client = Jira(
                url=self.server_url,
                username=self.user,
                password=self.token,
                cloud=True,
            )
        else:
            self._client = Jira(
                url=self.server_url,
                token=self.token,
                cloud=False,
            )
        return self._client

    def get_issue(self, issue_key: str) -> JiraIssue:
        raw = self._get_client().get_issue(issue_key)
        issue = _issue_from_dict(raw if isinstance(raw, dict) else {}, jira_client=self)
        return issue

    def transitions(self, issue_key: str) -> list[JiraTransition]:
        raw = self._get_client().get_issue_transitions(issue_key)
        return [_transition_from_dict(t) for t in (raw or []) if isinstance(t, dict)]

    def search_issues(
        self,
        jql_str: str,
        max_results: int = 50,
        start_at: int = 0,
    ) -> list[JiraIssue]:
        result = self._get_client().jql(jql_str, start=start_at, limit=max_results)
        issues = result.get("issues", []) if isinstance(result, dict) else []
        return [
            _issue_from_dict(i, jira_client=self) for i in issues if isinstance(i, dict)
        ]

    def create_issue(
        self,
        project: str,
        summary: str,
        issuetype: str,
        description: str | None = None,
        **fields: Any,
    ) -> JiraIssue:
        payload = {
            "project": {"key": project},
            "summary": summary,
            "issuetype": {"name": issuetype},
        }
        if description is not None:
            payload["description"] = description
        for k, v in fields.items():
            if k not in ("project", "summary", "issuetype", "description"):
                payload[k] = v
        raw = self._get_client().create_issue(fields=payload)
        key = raw.get("key") if isinstance(raw, dict) else None
        return (
            self.get_issue(key)
            if key
            else _issue_from_dict(
                raw if isinstance(raw, dict) else {}, jira_client=self
            )
        )

    def transition(
        self,
        issue_key: str,
        transition: str | int,
        *,
        fields: dict[str, Any] | None = None,
        update: dict[str, Any] | None = None,
    ) -> None:
        """Run a workflow transition. Optional ``fields`` / ``update`` are sent on the same POST as
        ``transition`` (Jira transition screens). When both are empty/absent, delegates to
        ``set_issue_status_by_transition_id`` for backward compatibility.
        """
        c = self._get_client()
        trans_id: int
        if isinstance(transition, int):
            trans_id = transition
        else:
            tid = str(transition).strip()
            if tid.isdigit():
                trans_id = int(tid)
            else:
                found: int | None = None
                for t in c.get_issue_transitions(issue_key) or []:
                    if isinstance(t, dict) and t.get("name") == tid:
                        raw_id = t.get("id")
                        if raw_id is not None:
                            found = int(raw_id)
                            break
                if found is None:
                    names = [
                        t.get("name", "?")
                        for t in (c.get_issue_transitions(issue_key) or [])
                        if isinstance(t, dict)
                    ]
                    raise ValueError(f"Transition {transition!r} not found. Available: {names}")
                trans_id = found

        has_screen = bool(fields) or bool(update)
        if has_screen:
            base_url = c.resource_url("issue")
            url = f"{base_url}/{issue_key}/transitions"
            data: dict[str, Any] = {"transition": {"id": trans_id}}
            if fields:
                data["fields"] = fields
            if update:
                data["update"] = update
            c.post(url, data=data)
        else:
            c.set_issue_status_by_transition_id(issue_key, trans_id)

    def assign(self, issue_key: str, assignee: str | None) -> None:
        self._get_client().assign_issue(issue_key, assignee)

    def get_comments(self, issue_key: str) -> list[JiraComment]:
        raw = self._get_client().issue_get_comments(issue_key)
        raw_comments = []
        if isinstance(raw, dict):
            raw_comments = raw.get("comments", [])
        elif isinstance(raw, list):
            raw_comments = raw

        comments = [
            _comment_from_dict(comment)
            for comment in raw_comments
            if isinstance(comment, dict)
        ]
        return sorted(comments, key=lambda c: c.created or "", reverse=True)

    def delete_comment(self, issue_key: str, comment_id: str | int) -> None:
        c = self._get_client()
        base = c.resource_url("issue")
        c.delete(f"{base}/{issue_key}/comment/{comment_id}")

    def add_comment(self, issue_key: str, body: str) -> JiraComment:
        raw = self._get_client().issue_add_comment(issue_key, body)
        if not isinstance(raw, dict):
            return JiraComment(id="", body=body)
        comment = _comment_from_dict(raw)
        if not comment.body:
            comment.body = body
        return comment

    def append_to_description(
        self,
        issue_key: str,
        *,
        text: str,
        position: str = "BOTTOM",
    ) -> JiraIssue:
        """Append text to issue description at top or bottom."""
        position_normalized = position.strip().upper()
        if position_normalized not in {"TOP", "BOTTOM"}:
            raise ValueError("position must be 'TOP' or 'BOTTOM'")

        current = self.get_issue(issue_key)
        current_description = current.description.strip()
        text_to_append = text.strip()
        if not text_to_append:
            return current

        if not current_description:
            merged = text_to_append
        elif position_normalized == "TOP":
            merged = f"{text_to_append}\n\n{current_description}"
        else:
            merged = f"{current_description}\n\n{text_to_append}"

        return self.update_issue(issue_key, description=merged)

    def add_subtask(
        self,
        issue_key: str,
        *,
        headline: str,
        description: str = "",
        issue_type: str = "Sub-task",
    ) -> JiraIssue:
        """Create a sub-task under a parent issue."""
        summary = headline.strip()
        if not summary:
            raise ValueError("headline must not be empty")

        issue_type_normalized = issue_type.strip()
        compact = (
            issue_type_normalized.replace("-", "").replace("_", "").replace(" ", "")
        )
        if compact.lower() == "subtask":
            issue_type_normalized = "Sub-task"
        if not issue_type_normalized:
            issue_type_normalized = "Sub-task"

        project_key = issue_key.split("-", 1)[0].strip()
        if not project_key:
            raise ValueError("issue_key must include a Jira project key prefix")

        return self.create_issue(
            project=project_key,
            summary=summary,
            issuetype=issue_type_normalized,
            description=description or "",
            parent={"key": issue_key},
        )

    def update_issue(
        self,
        issue_key: str,
        fields: dict[str, Any] | None = None,
        summary: str | None = None,
        description: str | None = None,
    ) -> JiraIssue:
        c = self._get_client()
        updates = dict(fields) if fields else {}
        if summary is not None:
            updates["summary"] = summary
        if description is not None:
            updates["description"] = description
        if updates:
            c.issue_update(issue_key, updates)
        return self.get_issue(issue_key)

    def delete_issue(self, issue_key: str) -> None:
        self._get_client().delete_issue(issue_key)
