"""Contrib actions for searchable RecordSet sources."""

from __future__ import annotations

from typing import Any

from agy.action_type import ActionType
from agy.integrations.email import EmailAccount
from agy.record_sources import search_emails, search_files
from agy.records import RecordSet


def search_emails_action(
    account: EmailAccount,
    query: str | None = None,
    batch_size: int = 10,
    **filters: Any,
) -> RecordSet:
    """Search emails and return a RecordSet for batch-oriented flows."""
    return search_emails(account, query=query, batch_size=batch_size, **filters)


def search_files_action(
    root_path: str = ".",
    query: str | None = None,
    batch_size: int = 10,
    **filters: Any,
) -> RecordSet:
    """Search local files and return a RecordSet for batch-oriented flows."""
    return search_files(
        root_path=root_path,
        query=query,
        batch_size=batch_size,
        **filters,
    )


SEARCH_EMAILS_ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="search_emails",
    kwargs={},
    callable=search_emails_action,
    description="Search emails and return a RecordSet with readable batch methods",
)

SEARCH_FILES_ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="search_files",
    kwargs={},
    callable=search_files_action,
    description="Search files and return a RecordSet with readable batch methods",
)

ACTION_TYPE = SEARCH_EMAILS_ACTION_TYPE
