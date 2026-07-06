"""Helper functions for Jira support ticket routing."""

from __future__ import annotations

from agy.integrations.jira.models import JiraIssue


def sanitize_issue_text(issue: JiraIssue) -> str:
    """Return best available text for classification/answering."""
    text = (issue.description or "").strip()
    if text:
        return text
    return (issue.summary or "").strip()


def format_assignment_comment(ticket_type: str, assignee: str) -> str:
    """Build an audit comment for assignment actions."""
    return (
        f"Ticket was classified as type '{ticket_type}' and assigned to '{assignee}' "
        "for specialist follow-up."
    )
