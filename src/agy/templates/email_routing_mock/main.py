"""Main entry point for the travel insurance email routing flow using MockEmailAccount."""

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from objects import submit_claim, validate_claim

from agy import Flow, FlowExecutor
from agy.action_type import ActionType
from agy.integrations.email import MockEmailAccount

load_dotenv()


async def process_email(
    flow: Flow, email, filename: str, action_types: list[ActionType]
):
    """Process a single email through the flow."""
    print(f"\n\n\n{'=' * 60}")
    print(f"Processing: {filename}")
    print(f"From: {email.sender}")
    print(f"Subject: {email.subject}")
    print(f"{'=' * 60}")

    executor = FlowExecutor(context_in={"email": email}, action_types=action_types)

    result_context = await executor.execute(flow)

    category = result_context.get("category", "N/A")
    confidence = result_context.get("confidence", "N/A")
    success = "✓" if result_context.get("success", False) else "✗"
    error = result_context.get("error_msg", "")
    summary = f"\n✓ {filename}: {success} {category} (conf: {confidence})"
    if error:
        summary += f" - Error: {error}"
    print(summary)


async def main():
    """Execute the email routing flow for all emails in mock_mailbox."""
    action_types = [
        ActionType(
            object_name="global_function",
            method_name="validate_claim",
            callable=validate_claim,
            description="Validate claim data completeness",
        ),
        ActionType(
            object_name="global_function",
            method_name="submit_claim",
            callable=submit_claim,
            description="Submit claim to system",
        ),
    ]

    # Connect to mock email account
    account = MockEmailAccount(
        base_path=Path(__file__).parent / "mock_mailbox",
        user_email="support@acmetravelinsurance.com",
    )

    # Fetch all emails from inbox
    emails = account.get_emails(folders=["inbox"])

    if not emails:
        print("No emails found in mock_mailbox/inbox/")
        return

    print(f"Found {len(emails)} email(s) to process")

    # Validate the flow
    if emails:
        validation_result = Flow.validate(
            "email_routing_flow.flowsy",
            context_in={"email": emails[0]},
            action_types=action_types,
        )
        if not validation_result.is_valid:
            print(f"\n⚠️  Validation failed: {len(validation_result.errors)} error(s)")
            for error in validation_result.errors:
                location_str = f" ({error.location})" if error.location else ""
                print(f"  - {error.message}{location_str}")
            return
        print("Flow validation passed")

    # Load the flow
    flow = Flow.from_flowsy("email_routing_flow.flowsy")

    # Process each email
    for email in emails:
        await process_email(flow, email, email.subject or "Unknown", action_types)

    print(f"\n{'=' * 60}")
    print("All emails processed!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
