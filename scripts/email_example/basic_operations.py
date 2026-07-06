#!/usr/bin/env python3
"""
Basic Email Operations Example

Demonstrates core email operations with MockEmailAccount:
- Fetching emails
- Searching emails
- Creating and sending emails
- Replying and forwarding
- Moving and deleting

Run: python basic_operations.py
"""

import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from agy.integrations.email import Email, MockEmailAccount  # noqa: E402


def demo_basic_operations():
    """Demonstrate basic email operations."""

    with tempfile.TemporaryDirectory() as tmpdir:
        mailbox_path = Path(tmpdir)

        # Create account
        account = MockEmailAccount(base_path=mailbox_path, user_email="me@example.com")

        print("=" * 60)
        print("BASIC EMAIL OPERATIONS DEMO")
        print("=" * 60)

        # --- 1. Add test emails ---
        print("\n1. CREATING TEST EMAILS")

        account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="me@example.com",
            subject="Meeting tomorrow",
            text="Can we meet at 10am tomorrow?",
        )

        account.add_email(
            folder="inbox",
            sender="bob@example.com",
            recipient="me@example.com",
            subject="Project update",
            text="The project is on track.",
        )

        account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="me@example.com",
            subject="Lunch?",
            text="Want to grab lunch today?",
        )

        print("Created 3 test emails in inbox")

        # --- 2. Get emails ---
        print("\n2. FETCHING EMAILS")

        emails = account.get_emails(folders=["inbox"])
        print(f"Found {len(emails)} emails in inbox:")
        for e in emails:
            print(f"  - From: {e.sender}, Subject: {e.subject}")

        # --- 3. Search emails ---
        print("\n3. SEARCHING EMAILS")

        # Search by sender
        alice_emails = account.find_emails(from_contains="alice")
        print(f"Emails from 'alice': {len(alice_emails)}")
        for e in alice_emails:
            print(f"  - {e.subject}")

        # Search by subject
        meeting_emails = account.find_emails(subject_contains="meeting")
        print(f"\nEmails with 'meeting' in subject: {len(meeting_emails)}")

        # --- 4. Reply to an email ---
        print("\n4. REPLYING TO EMAIL")

        meeting_email = meeting_emails[0]
        meeting_email.reply("Yes, 10am works for me!")
        print(f"Replied to: {meeting_email.subject}")

        # --- 5. Forward an email ---
        print("\n5. FORWARDING EMAIL")

        project_email = account.find_emails(subject_contains="project")[0]
        project_email.forward("manager@example.com")
        print(f"Forwarded '{project_email.subject}' to manager@example.com")

        # --- 6. Move email ---
        print("\n6. MOVING EMAIL")

        lunch_email = account.find_emails(subject_contains="lunch")[0]
        lunch_email.move("archive")
        print(f"Moved '{lunch_email.subject}' to archive")

        # --- 7. Create and send new email ---
        print("\n7. CREATING AND SENDING EMAIL")

        new_email = Email.create(
            to="team@example.com",
            subject="Weekly sync",
            text="Reminder: Weekly sync call today at 3pm.",
            account=account,
        )
        new_email.send()
        print(f"Sent new email: {new_email.subject}")

        # --- 8. Delete email ---
        print("\n8. DELETING EMAIL")

        inbox_emails = account.get_emails(folders=["inbox"])
        if inbox_emails:
            email_to_delete = inbox_emails[0]
            email_to_delete.delete()
            print(f"Deleted: {email_to_delete.subject}")

        # --- Final state ---
        print("\n" + "=" * 60)
        print("FINAL MAILBOX STATE")
        print("=" * 60)

        for folder in ["inbox", "sent", "archive", "trash"]:
            folder_emails = account.get_emails(folders=[folder])
            if folder_emails:
                print(f"\n{folder.upper()} ({len(folder_emails)}):")
                for e in folder_emails:
                    print(f"  - {e.subject}")


if __name__ == "__main__":
    demo_basic_operations()
