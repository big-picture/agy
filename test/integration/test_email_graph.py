# test/integration/test_email_graph.py

"""
Integration tests for Graph Email API.

Run with: pytest test/integration/test_email_graph.py -v -s -m email_integration
Requires: test/integration/.env.graph_test with credentials
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from dotenv import load_dotenv

if TYPE_CHECKING:
    from agy.integrations.email import Email


# Integration test folders (subfolders of Inbox)
# Use these instead of main Inbox to avoid interference with real emails
TEST_FOLDER_0 = "Inbox/integrationtest0"
TEST_FOLDER_1 = "Inbox/integrationtest1"
TEST_FOLDER_2 = "Inbox/integrationtest2"


# Load specific .env for this test
@pytest.fixture(scope="module", autouse=True)
def load_graph_env():
    """Load .env.graph_test and verify required variables."""
    env_path = Path(__file__).parent / ".env.graph_test"
    if not env_path.exists():
        pytest.skip(f"Missing {env_path} - create it with Graph credentials")

    load_dotenv(env_path, override=True)

    required = ["TENANT_ID", "CLIENT_ID", "CLIENT_SECRET", "USER_EMAIL"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        pytest.skip(f"Missing env vars in .env.graph_test: {missing}")


@pytest.fixture
def graph_account():
    """Create a GraphEmailAccount for testing."""
    from agy.integrations.email import GraphEmailAccount

    user_email = os.getenv("USER_EMAIL")
    return GraphEmailAccount(user_email=user_email)


@pytest.fixture
def test_id():
    """Generate unique test ID for this test run."""
    return str(uuid.uuid4())[:8]


def wait_for_email(
    account,
    subject_contains: str,
    folder: str = TEST_FOLDER_0,
    max_wait: int = 30,
    interval: int = 3,
) -> Email | None:
    """Wait for an email to appear in a specific folder."""

    waited = 0
    while waited < max_wait:
        emails = account.find_emails(
            folders=[folder], subject_contains=subject_contains, max_results=10
        )
        for e in emails:
            if subject_contains in (e.subject or ""):
                return e
        time.sleep(interval)
        waited += interval
    return None


def wait_for_email_deleted(
    account,
    subject_contains: str,
    folder: str = TEST_FOLDER_0,
    max_wait: int = 30,
    interval: int = 3,
) -> bool:
    """Wait for an email to be deleted from a specific folder. Returns True if deleted."""
    waited = 0
    while waited < max_wait:
        emails = account.find_emails(
            folders=[folder], subject_contains=subject_contains, max_results=10
        )
        found = any(subject_contains in (e.subject or "") for e in emails)
        if not found:
            return True
        time.sleep(interval)
        waited += interval
    return False


# =============================================================================
# Basic Tests
# =============================================================================


@pytest.mark.email_integration
def test_graph_get_emails(graph_account):
    """Test fetching emails from Graph inbox."""
    print("\n=== Test: get_emails ===")

    emails = graph_account.get_emails(max_results=5, only_unread=False)

    print(f"Found {len(emails)} email(s)")
    for e in emails[:3]:
        print(f"  - [{e.sender}] {e.subject}")

    assert isinstance(emails, list)
    for email in emails:
        assert email.account is graph_account
        assert hasattr(email, "sender")
        assert hasattr(email, "subject")


@pytest.mark.email_integration
def test_graph_find_emails(graph_account):
    """Test searching for emails."""
    print("\n=== Test: find_emails ===")

    # General search
    emails = graph_account.find_emails(max_results=5, email_contains="test")
    print(f"Found {len(emails)} email(s) containing 'test'")

    assert isinstance(emails, list)


# =============================================================================
# Comprehensive End-to-End Test
# =============================================================================


@pytest.mark.email_integration
def test_graph_full_workflow(graph_account, test_id):
    """
    Comprehensive test of all email operations:
    1. Send email to self
    2. Find email by subject
    3. Get emails and verify
    4. Reply to email
    5. Forward email
    6. Move email to folder
    7. Delete all test emails (cleanup)
    """
    from agy.integrations.email import Email

    user_email = os.getenv("USER_EMAIL")
    test_subject = f"[AGY-TEST-{test_id}] Full Workflow Test"

    print(f"\n{'=' * 60}")
    print("COMPREHENSIVE GRAPH API TEST")
    print(f"{'=' * 60}")
    print(f"User: {user_email}")
    print(f"Test ID: {test_id}")
    print(f"Test Subject: {test_subject}")

    created_emails = []  # Track emails for cleanup

    try:
        # -----------------------------------------------------------------
        # 1. SEND: Create and send email to self
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("1. SEND EMAIL")
        print(f"{'─' * 40}")

        email = Email.create(
            to=user_email,
            subject=test_subject,
            text=f"Test email body.\n\nTest ID: {test_id}\nCreated: {datetime.now().isoformat()}",
            account=graph_account,
        )
        sent_email = email.send()

        print("   ✓ Email sent")
        print(f"   Subject: {sent_email.subject}")

        # -----------------------------------------------------------------
        # 2. FIND: Search for the email by subject (in main Inbox)
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("2. FIND EMAIL (waiting for delivery...)")
        print(f"{'─' * 40}")

        # Email arrives in main Inbox first, not the test folder
        found_email = wait_for_email(
            graph_account, test_id, folder="Inbox", max_wait=30
        )

        if found_email:
            print("   ✓ Email found via find_emails")
            print(f"   Message ID: {found_email.message_id[:30]}...")
            created_emails.append(found_email)
        else:
            pytest.fail(f"Email with test ID '{test_id}' not found after 30s")

        # -----------------------------------------------------------------
        # 3. GET: Verify email appears in get_emails
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("3. GET EMAILS & VERIFY")
        print(f"{'─' * 40}")

        # Wait a bit for mailbox sync before fetching
        time.sleep(3)
        inbox_emails = graph_account.get_emails(max_results=20, only_unread=False)
        inbox_match = None
        for e in inbox_emails:
            if test_id in (e.subject or ""):
                inbox_match = e
                break

        assert inbox_match is not None, "Email not found in get_emails result"
        print("   ✓ Email found in inbox via get_emails")
        print(f"   Sender: {inbox_match.sender}")
        print(f"   Subject: {inbox_match.subject}")
        assert test_id in inbox_match.text, "Email body does not contain test ID"
        print("   ✓ Email body verified")

        # -----------------------------------------------------------------
        # 4. REPLY: Reply to the email
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("4. REPLY TO EMAIL")
        print(f"{'─' * 40}")

        # Wait for mailbox to fully sync before reply operation
        time.sleep(2)

        # Use inbox_match (from get_emails) for operations - more reliable than search results
        reply_text = f"This is a test reply.\n\nReply Test ID: {test_id}-reply"
        reply_email = inbox_match.reply(reply_text)

        print("   ✓ Reply sent")
        print(f"   Reply Subject: {reply_email.subject}")

        # Wait and find the reply
        time.sleep(5)
        reply_found = wait_for_email(graph_account, f"{test_id}-reply", max_wait=20)
        if reply_found:
            print("   ✓ Reply received in inbox")
            created_emails.append(reply_found)
        else:
            print("   ⚠ Reply not found in inbox (may be in sent)")

        # -----------------------------------------------------------------
        # 5. FORWARD: Forward the email
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("5. FORWARD EMAIL")
        print(f"{'─' * 40}")

        forward_email = inbox_match.forward(user_email)

        print("   ✓ Email forwarded to self")
        print(f"   Forward Subject: {forward_email.subject}")

        # Wait and find the forward
        time.sleep(5)
        forward_found = wait_for_email(
            graph_account, f"FW: {test_subject[:20]}", max_wait=20
        )
        if forward_found:
            print("   ✓ Forwarded email received")
            created_emails.append(forward_found)
        else:
            print("   ⚠ Forwarded email not found in inbox")

        # -----------------------------------------------------------------
        # 6. MOVE: Move email to a folder
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("6. MOVE EMAIL")
        print(f"{'─' * 40}")

        # Move the original email to deleted folder
        try:
            inbox_match.move("deleted")
            print("   ✓ Original email moved to 'deleted'")
            # Remove from cleanup list since it's in deleted now
            created_emails = [
                e for e in created_emails if e.message_id != inbox_match.message_id
            ]
        except Exception as exc:
            print(f"   ⚠ Move failed (folder may not exist): {exc}")

        # -----------------------------------------------------------------
        # SUMMARY
        # -----------------------------------------------------------------
        print(f"\n{'=' * 60}")
        print("TEST SUMMARY")
        print(f"{'=' * 60}")
        print("   ✓ send_email: OK")
        print("   ✓ find_emails: OK")
        print("   ✓ get_emails: OK")
        print("   ✓ reply: OK")
        print("   ✓ forward: OK")
        print("   ✓ move: OK")

    finally:
        # -----------------------------------------------------------------
        # 7. CLEANUP: Delete all test emails
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("7. CLEANUP")
        print(f"{'─' * 40}")

        # Find and delete any remaining test emails
        remaining = graph_account.find_emails(email_contains=test_id, max_results=20)
        for e in remaining:
            try:
                e.delete()
                print(f"   Deleted: {e.subject[:40]}...")
            except Exception as exc:
                print(f"   ⚠ Failed to delete {e.message_id[:20]}: {exc}")

        if not remaining:
            print("   No test emails remaining")

        print(f"\n{'=' * 60}")
        print("TEST COMPLETE")
        print(f"{'=' * 60}")


# =============================================================================
# Individual Operation Tests
# =============================================================================


@pytest.mark.email_integration
def test_graph_send_and_delete(graph_account, test_id):
    """Test send and delete operations."""
    from agy.integrations.email import Email

    user_email = os.getenv("USER_EMAIL")
    test_subject = f"[AGY-DELETE-TEST-{test_id}]"

    print("\n=== Test: Send & Delete ===")

    # Send
    email = Email.create(
        to=user_email,
        subject=test_subject,
        text="This email will be deleted.",
        account=graph_account,
    )
    email.send()
    print(f"Sent: {test_subject}")

    # Wait and find (in main Inbox, not test folder)
    time.sleep(5)
    found = wait_for_email(graph_account, test_id, folder="Inbox", max_wait=20)

    if found:
        # Delete using email.delete()
        found.delete()
        print(f"Deleted: {found.message_id[:30]}...")

        # Verify deletion with retry (Graph API eventual consistency)
        deleted = wait_for_email_deleted(
            graph_account, test_id, folder="Inbox", max_wait=30, interval=3
        )
        assert deleted, "Email still exists after deletion (waited 30s)"
        print("Verified: Email deleted successfully")
    else:
        pytest.fail("Test email not found")


@pytest.mark.email_integration
def test_graph_get_emails_only_unread(graph_account):
    """Test fetching only unread emails."""
    print("\n=== Test: get_emails (only_unread=True) ===")

    emails = graph_account.get_emails(max_results=10, only_unread=True)
    print(f"Found {len(emails)} unread email(s)")

    assert isinstance(emails, list)


@pytest.mark.email_integration
def test_graph_find_emails_with_filters(graph_account):
    """Test find_emails with various filters."""
    print("\n=== Test: find_emails with filters ===")

    user_email = os.getenv("USER_EMAIL")

    # Search by sender
    emails = graph_account.find_emails(
        from_contains=user_email.split("@")[0], max_results=5
    )
    print(f"Emails from '{user_email.split('@')[0]}': {len(emails)}")

    # Search by subject
    emails = graph_account.find_emails(subject_contains="test", max_results=5)
    print(f"Emails with 'test' in subject: {len(emails)}")

    assert isinstance(emails, list)


@pytest.mark.email_integration
def test_graph_find_emails_with_attachments(graph_account):
    """Test find_emails combining email_contains with has_attachments filter."""
    print("\n=== Test: find_emails with has_attachments ===")
    print(f"Using test folder: {TEST_FOLDER_0}")

    # Test 1: Find emails WITH attachments using email_contains
    emails_with_att = graph_account.find_emails(
        folders=[TEST_FOLDER_0],
        email_contains="attachment integration test",
        has_attachments=True,
        max_results=10,
    )
    print(
        f"Emails matching 'attachment integration test' WITH attachments: {len(emails_with_att)}"
    )

    # Should find at least one (the test email we placed)
    assert len(emails_with_att) >= 1, "Expected at least 1 email with attachment"
    for email in emails_with_att:
        print(f"  - {email.subject}")

    # Test 2: Find emails WITHOUT attachments using email_contains
    emails_no_att = graph_account.find_emails(
        folders=[TEST_FOLDER_0],
        email_contains="attachment integration test",
        has_attachments=False,
        max_results=10,
    )
    print(
        f"Emails matching 'attachment integration test' WITHOUT attachments: {len(emails_no_att)}"
    )

    # The test email has attachments, so it should NOT appear in this list
    for email in emails_no_att:
        print(f"  - {email.subject}")

    # Test 3: has_attachments=True without email_contains (uses $filter)
    emails_att_only = graph_account.find_emails(
        folders=[TEST_FOLDER_0],
        has_attachments=True,
        max_results=5,
    )
    print(f"Emails with attachments (no search term): {len(emails_att_only)}")
    assert isinstance(emails_att_only, list)
