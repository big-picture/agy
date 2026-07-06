"""Business objects for Jira integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class JiraTransition:
    """A possible workflow transition for an issue."""

    name: str
    to_status: str = "?"


@dataclass(slots=True)
class JiraComment:
    """A Jira issue comment."""

    id: str
    body: str
    created: str = ""
    author: str | None = None


@dataclass(slots=True)
class JiraIssue:
    """A compact Jira issue business object used in flows."""

    key: str
    summary: str = ""
    status: str = ""
    issuetype: str = ""
    assignee: str | None = None
    reporter: str | None = None
    description: str = ""
    labels: list[str] = field(default_factory=list)
    extra_fields: dict[str, Any] = field(default_factory=dict)
    _jira_client: Any | None = field(default=None, repr=False, compare=False)

    def _bind_client(self, jira_client: Any) -> JiraIssue:
        """Bind an internal Jira client for issue-level operations."""
        self._jira_client = jira_client
        return self

    def add_comment(self, body: str) -> JiraComment:
        """Add a comment to this issue using the bound Jira client."""
        if self._jira_client is None:
            raise ValueError(
                "JiraIssue is not bound to a JiraClient. "
                "Use JiraClient.get_issue()/search_issues()/create_issue() first."
            )
        return self._jira_client.add_comment(self.key, body)

    def get_comments(self) -> list[JiraComment]:
        """Return issue comments in reverse chronological order (newest first)."""
        if self._jira_client is None:
            raise ValueError(
                "JiraIssue is not bound to a JiraClient. "
                "Use JiraClient.get_issue()/search_issues()/create_issue() first."
            )
        comments: list[JiraComment] = self._jira_client.get_comments(self.key)
        return sorted(comments, key=lambda c: c.created or "", reverse=True)

    def append_to_description(self, text: str, position: str = "BOTTOM") -> JiraIssue:
        """Append text to this issue's description at TOP or BOTTOM."""
        if self._jira_client is None:
            raise ValueError(
                "JiraIssue is not bound to a JiraClient. "
                "Use JiraClient.get_issue()/search_issues()/create_issue() first."
            )
        return self._jira_client.append_to_description(
            self.key, text=text, position=position
        )

    def add_subtask(
        self,
        headline: str,
        description: str = "",
        issue_type: str = "Sub-task",
    ) -> JiraIssue:
        """Create a Jira sub-task under this issue."""
        if self._jira_client is None:
            raise ValueError(
                "JiraIssue is not bound to a JiraClient. "
                "Use JiraClient.get_issue()/search_issues()/create_issue() first."
            )
        return self._jira_client.add_subtask(
            self.key,
            headline=headline,
            description=description,
            issue_type=issue_type,
        )

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        field_mapping: dict[str, str] | None = None,
    ) -> JiraIssue:
        """Build JiraIssue (or subclass) from Jira-like `{key, fields}` data."""
        from .client import _issue_from_dict

        return _issue_from_dict(data, field_mapping=field_mapping, issue_cls=cls)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        data: dict[str, Any] = {
            "key": self.key,
            "summary": self.summary,
            "status": self.status,
            "issuetype": self.issuetype,
            "assignee": self.assignee,
            "reporter": self.reporter,
            "description": self.description,
            "labels": self.labels,
        }
        if self.extra_fields:
            data["extra_fields"] = self.extra_fields
        return data
