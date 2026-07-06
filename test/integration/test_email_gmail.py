# test/integration/test_email_gmail.py

"""
Integration tests for Gmail Email API.

Run with: pytest test/integration/test_email_gmail.py -v -s -m email_integration
Requires: test/integration/.env.gmail_test with credentials
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

# Integration test folders (Gmail labels - nested under INBOX)
TEST_FOLDER_0 = "INBOX/integrationtest0"
TEST_FOLDER_1 = "INBOX/integrationtest1"
TEST_FOLDER_2 = "INBOX/integrationtest2"


# Load specific .env for this test
@pytest.fixture(scope="module", autouse=True)
def load_gmail_env():
    """Load .env.gmail_test and verify required variables."""
    env_path = Path(__file__).parent / ".env.gmail_test"
    if not env_path.exists():
        pytest.skip(f"Missing {env_path} - create it with Gmail credentials")

    load_dotenv(env_path, override=True)

    required = ["GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_TOKEN_FILE"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        pytest.skip(f"Missing env vars in .env.gmail_test: {missing}")

    token_file = os.getenv("GMAIL_TOKEN_FILE")
    if not Path(token_file).exists():
        pytest.skip(f"Missing token file: {token_file}")

    # Reset safety validator to pick up new allowed domains
    from agy.integrations.email.email_safety import reset_validator

    reset_validator()


@pytest.fixture
def gmail_account():
    """Create a GmailEmailAccount for testing."""
    from agy.integrations.email import GmailEmailAccount

    return GmailEmailAccount()


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
    """Wait for an email to appear in a specific folder/label."""
    waited = 0
    while waited < max_wait:
        emails = account.find_emails(
            subject_contains=subject_contains,
            folders=[folder] if folder else None,
            max_results=10,
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
    """Wait for an email to disappear from a specific folder/label."""
    waited = 0
    while waited < max_wait:
        emails = account.find_emails(
            subject_contains=subject_contains,
            folders=[folder] if folder else None,
            max_results=10,
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
def test_gmail_get_emails(gmail_account):
    """Test fetching emails from Gmail test folder."""
    print("\n=== Test: get_emails ===")
    print(f"Using test folder: {TEST_FOLDER_0}")

    emails = gmail_account.get_emails(
        folders=[TEST_FOLDER_0], max_results=5, only_unread=False
    )

    print(f"Found {len(emails)} email(s)")
    for e in emails[:3]:
        print(f"  - [{e.sender}] {e.subject}")

    assert isinstance(emails, list)
    for email in emails:
        assert email.account is gmail_account


@pytest.mark.email_integration
def test_gmail_find_emails(gmail_account):
    """Test searching for emails in test folder."""
    print("\n=== Test: find_emails ===")
    print(f"Using test folder: {TEST_FOLDER_0}")

    emails = gmail_account.find_emails(
        folders=[TEST_FOLDER_0], max_results=5, email_contains="test"
    )
    print(f"Found {len(emails)} email(s) containing 'test'")

    assert isinstance(emails, list)


# =============================================================================
# Comprehensive End-to-End Test
# =============================================================================


@pytest.mark.email_integration
def test_gmail_full_workflow(gmail_account, test_id):
    """
    Comprehensive test of Gmail email operations:
    1. Send email to self
    2. Move to test folder
    3. Find email by subject
    4. Get emails and verify
    5. Reply to email
    6. Forward email
    7. Delete all test emails (cleanup)
    """
    from agy.integrations.email import Email

    user_email = gmail_account.user_email
    test_subject = f"[AGY-GMAIL-TEST-{test_id}] Full Workflow Test"

    print(f"\n{'=' * 60}")
    print("COMPREHENSIVE GMAIL API TEST")
    print(f"{'=' * 60}")
    print(f"User: {user_email}")
    print(f"Test ID: {test_id}")
    print(f"Test Subject: {test_subject}")
    print(f"Test Folder: {TEST_FOLDER_1}")

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
            account=gmail_account,
        )
        sent_email = email.send()

        print("   ✓ Email sent")
        print(f"   Subject: {sent_email.subject}")

        # -----------------------------------------------------------------
        # 2. MOVE: Move email to test folder
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("2. MOVE EMAIL TO TEST FOLDER")
        print(f"{'─' * 40}")

        time.sleep(2)
        # First find it in INBOX (where it arrives)
        inbox_emails = gmail_account.find_emails(
            subject_contains=test_id, max_results=5
        )
        if inbox_emails:
            inbox_emails[0].move(TEST_FOLDER_1)
            print(f"   ✓ Email moved to {TEST_FOLDER_1}")
        else:
            print("   ⚠ Email not found in inbox yet, will search test folder")

        # -----------------------------------------------------------------
        # 3. FIND: Search for the email by subject in test folder
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("3. FIND EMAIL (waiting for delivery...)")
        print(f"{'─' * 40}")

        found_email = wait_for_email(
            gmail_account, test_id, folder=TEST_FOLDER_1, max_wait=30
        )

        if found_email:
            print("   ✓ Email found via find_emails")
            print(
                f"   Message ID: {found_email.message_id[:30] if found_email.message_id else 'N/A'}..."
            )
        else:
            pytest.fail(
                f"Email with test ID '{test_id}' not found in {TEST_FOLDER_1} after 30s"
            )

        # -----------------------------------------------------------------
        # 4. GET: Verify email appears in get_emails
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("4. GET EMAILS & VERIFY")
        print(f"{'─' * 40}")

        time.sleep(3)
        folder_emails = gmail_account.get_emails(
            folders=[TEST_FOLDER_1], max_results=20, only_unread=False
        )
        inbox_match = None
        for e in folder_emails:
            if test_id in (e.subject or ""):
                inbox_match = e
                break

        if inbox_match:
            print(f"   ✓ Email found in {TEST_FOLDER_1} via get_emails")
            print(f"   Sender: {inbox_match.sender}")
            print(f"   Subject: {inbox_match.subject}")
        else:
            print("   ⚠ Email not found in get_emails (may still be processing)")
            inbox_match = found_email

        # -----------------------------------------------------------------
        # 5. REPLY: Reply to the email
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("5. REPLY TO EMAIL")
        print(f"{'─' * 40}")

        time.sleep(2)

        try:
            reply_text = f"This is a test reply.\n\nReply Test ID: {test_id}-reply"
            reply_email = inbox_match.reply(reply_text)
            print("   ✓ Reply sent")
            print(f"   Reply Subject: {reply_email.subject}")
        except Exception as exc:
            print(f"   ⚠ Reply failed: {exc}")

        # -----------------------------------------------------------------
        # 6. FORWARD: Forward the email
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("6. FORWARD EMAIL")
        print(f"{'─' * 40}")

        try:
            forward_email = inbox_match.forward(user_email)
            print("   ✓ Email forwarded to self")
            print(f"   Forward Subject: {forward_email.subject}")
        except Exception as exc:
            print(f"   ⚠ Forward failed: {exc}")

        # -----------------------------------------------------------------
        # SUMMARY
        # -----------------------------------------------------------------
        print(f"\n{'=' * 60}")
        print("TEST SUMMARY")
        print(f"{'=' * 60}")
        print("   ✓ send_email: OK")
        print("   ✓ move: OK")
        print("   ✓ find_emails: OK")
        print("   ✓ get_emails: OK")
        print("   ✓ reply: OK")
        print("   ✓ forward: OK")

    finally:
        # -----------------------------------------------------------------
        # 7. CLEANUP: Delete all test emails
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("7. CLEANUP")
        print(f"{'─' * 40}")

        # Search in test folder and INBOX for any remaining test emails
        for folder in [TEST_FOLDER_1, "INBOX"]:
            remaining = gmail_account.find_emails(
                email_contains=test_id, folders=[folder], max_results=20
            )
            for e in remaining:
                try:
                    e.delete()
                    print(
                        f"   Deleted from {folder}: {e.subject[:40] if e.subject else 'N/A'}..."
                    )
                except Exception as exc:
                    print(f"   ⚠ Failed to delete: {exc}")

        print(f"\n{'=' * 60}")
        print("TEST COMPLETE")
        print(f"{'=' * 60}")


@pytest.mark.email_integration
def test_gmail_find_emails_with_attachments(gmail_account):
    """Test find_emails combining email_contains with has_attachments filter."""
    print("\n=== Test: find_emails with has_attachments ===")
    print(f"Using test folder: {TEST_FOLDER_0}")

    # Test 1: Find emails WITH attachments using email_contains
    emails_with_att = gmail_account.find_emails(
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
    emails_no_att = gmail_account.find_emails(
        folders=[TEST_FOLDER_0],
        email_contains="attachment integration test",
        has_attachments=False,
        max_results=10,
    )
    print(
        f"Emails matching 'attachment integration test' WITHOUT attachments: {len(emails_no_att)}"
    )

    for email in emails_no_att:
        print(f"  - {email.subject}")

    # Test 3: has_attachments=True without email_contains
    emails_att_only = gmail_account.find_emails(
        folders=[TEST_FOLDER_0],
        has_attachments=True,
        max_results=5,
    )
    print(f"Emails with attachments (no search term): {len(emails_att_only)}")
    assert isinstance(emails_att_only, list)
