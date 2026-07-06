#!/usr/bin/env python3
"""
Email Processing Example

This script demonstrates how to process emails with AGY flows using MockEmailAccount.
Run from the scripts/email_example directory:

    cd scripts/email_example
    python main.py

Requires OPENAI_API_KEY environment variable for LLM calls.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from agy import Flow, FlowExecutor  # noqa: E402
from agy.integrations.email import MockEmailAccount  # noqa: E402


def setup_test_mailbox(base_path: Path) -> MockEmailAccount:
    """Create a mock mailbox with test emails."""
    account = MockEmailAccount(base_path=base_path, user_email="support@example.com")

    # Add a question email
    account.add_email(
        folder="inbox",
        sender="customer1@example.com",
        recipient="support@example.com",
        subject="Shipping question",
        text="Hi, how long does standard shipping take? And is there free shipping available?",
    )

    # Add a complaint email
    account.add_email(
        folder="inbox",
        sender="customer2@example.com",
        recipient="support@example.com",
        subject="Order problem",
        text="I'm very unhappy with my order. The package arrived damaged and I want a refund immediately!",
    )

    # Add an unclear email
    account.add_email(
        folder="inbox",
        sender="customer3@example.com",
        recipient="support@example.com",
        subject="Hello",
        text="Hi there, just wanted to check in.",
    )

    return account


async def process_emails():
    """Main function to process emails with AGY flow."""

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. LLM calls will fail.")
        print("Set it with: export OPENAI_API_KEY='your-key'")
        print()

    # Create temporary mailbox
    with tempfile.TemporaryDirectory() as tmpdir:
        mailbox_path = Path(tmpdir)

        print("=" * 60)
        print("EMAIL PROCESSING EXAMPLE")
        print("=" * 60)

        # Setup mailbox with test emails
        account = setup_test_mailbox(mailbox_path)

        # Fetch emails from inbox
        emails = account.get_emails(folders=["inbox"])
        print(f"\nFound {len(emails)} emails in inbox\n")

        # Get flow path and change to script directory
        script_dir = Path(__file__).parent
        flow_path = script_dir / "flows" / "email_routing.flowsy"

        original_cwd = os.getcwd()
        os.chdir(script_dir)

        try:
            # Load the flow once
            flow = Flow.from_flowsy(str(flow_path))

            for i, email in enumerate(emails, 1):
                print("-" * 60)
                print(f"Processing email {i}/{len(emails)}")
                print(f"  From: {email.sender}")
                print(f"  Subject: {email.subject}")
                print(f"  Text: {email.text[:100]}...")
                print()

                # Create executor with email as context
                executor = FlowExecutor(context_in={"email": email})

                # Execute the flow
                try:
                    result_context = await executor.execute(flow)
                    category = result_context.get("category", "N/A")
                    confidence = result_context.get("confidence", "N/A")
                    print(f"\n  Result: category={category}, confidence={confidence}")
                except Exception as e:
                    print(f"\n  Error: {e}")

                print()
        finally:
            os.chdir(original_cwd)

        # Show final mailbox state
        print("=" * 60)
        print("FINAL MAILBOX STATE")
        print("=" * 60)

        for folder in ["inbox", "processed", "complaints", "manual_review", "sent"]:
            folder_emails = account.get_emails(folders=[folder])
            if folder_emails:
                print(f"\n{folder.upper()} ({len(folder_emails)} emails):")
                for e in folder_emails:
                    print(f"  - {e.subject}")


if __name__ == "__main__":
    asyncio.run(process_emails())
