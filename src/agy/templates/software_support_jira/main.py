"""Main entry point for Jira software support ticket routing."""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from objects import format_assignment_comment, sanitize_issue_text

from agy import Flow, FlowExecutor
from agy.action_type import ActionType
from agy.integrations.jira import JiraClient

load_dotenv()


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


async def main() -> None:
    """Run ticket processing for one Jira issue."""
    issue_key = _required_env("JIRA_ISSUE_KEY")
    close_transition = os.getenv("JIRA_CLOSE_TRANSITION", "Done")
    assignee_a = _required_env("JIRA_ASSIGNEE_A")

    jira = JiraClient.from_env()

    action_types = [
        ActionType(
            object_name="global_function",
            method_name="sanitize_issue_text",
            callable=sanitize_issue_text,
            description="Returns best ticket text from description or summary.",
        ),
        ActionType(
            object_name="global_function",
            method_name="format_assignment_comment",
            callable=format_assignment_comment,
            description="Builds an audit comment for Jira assignment.",
        ),
    ]

    context_in = {
        "jira": jira,
        "issue_key": issue_key,
        "close_transition": close_transition,
        "assignee_a": assignee_a,
    }

    validation = Flow.validate(
        "software_support_flow.flowsy",
        context_in=context_in,
        action_types=action_types,
    )
    if not validation.is_valid:
        print(f"Validation failed with {len(validation.errors)} error(s):")
        for error in validation.errors:
            location = f" ({error.location})" if error.location else ""
            print(f"  - {error.message}{location}")
        return

    flow = Flow.from_flowsy("software_support_flow.flowsy")
    executor = FlowExecutor(context_in=context_in, action_types=action_types)
    result_context = await executor.execute(flow)

    print("Processing complete")
    print("success:", result_context.get("success"))
    print("result:", result_context.get("result"))
    if result_context.get("error_msg"):
        print("error_msg:", result_context.get("error_msg"))


if __name__ == "__main__":
    asyncio.run(main())
