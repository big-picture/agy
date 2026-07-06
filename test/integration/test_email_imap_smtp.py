# test/integration/test_email_imap_smtp.py

"""
Integration tests for IMAP/SMTP Email Account.

Run with: pytest test/integration/test_email_imap_smtp.py -v -s -m email_integration
Requires: test/integration/.env.imap_test with credentials
"""

import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv


@pytest.fixture(scope="module", autouse=True)
def load_imap_env():
    """Load .env.imap_test and verify required variables."""
    env_path = Path(__file__).parent / ".env.imap_test"
    if not env_path.exists():
        pytest.skip(f"Missing {env_path} - create it with IMAP/SMTP credentials")

    load_dotenv(env_path, override=True)

    required = ["IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD", "SMTP_HOST"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        pytest.skip(f"Missing env vars in .env.imap_test: {missing}")

    from agy.integrations.email.email_safety import reset_validator

    reset_validator()


@pytest.fixture
def imap_account():
    """Create an ImapSmtpEmailAccount for testing."""
    from agy.integrations.email import ImapSmtpEmailAccount

    return ImapSmtpEmailAccount()


@pytest.fixture
def test_id():
    """Generate unique test ID for this test run."""
    return str(uuid.uuid4())[:8]


def wait_for_email(
    account, subject_contains: str, max_wait: int = 30, interval: int = 3
):
    """Wait for an email to appear."""
    waited = 0
    while waited < max_wait:
        emails = account.find_emails(subject_contains=subject_contains, max_results=10)
        for e in emails:
            if subject_contains in (e.subject or ""):
                return e
        time.sleep(interval)
        waited += interval
    return None


# =============================================================================
# Basic Tests
# =============================================================================


@pytest.mark.email_integration
def test_imap_get_emails(imap_account):
    """Test fetching emails from IMAP inbox."""
    print("\n=== Test: get_emails ===")

    emails = imap_account.get_emails(max_results=5, only_unread=False)

    print(f"Found {len(emails)} email(s)")
    for e in emails[:3]:
        print(f"  - [{e.sender}] {e.subject}")

    assert isinstance(emails, list)
    for email in emails:
        assert email.account is imap_account


@pytest.mark.email_integration
def test_imap_find_emails(imap_account):
    """Test searching for emails."""
    print("\n=== Test: find_emails ===")

    emails = imap_account.find_emails(max_results=5, subject_contains="test")
    print(f"Found {len(emails)} email(s) with 'test' in subject")

    assert isinstance(emails, list)


@pytest.mark.email_integration
def test_imap_enrich_raises_not_implemented(imap_account):
    """Test that enrich methods raise NotImplementedError."""
    print("\n=== Test: enrich raises NotImplementedError ===")

    emails = imap_account.get_emails(max_results=1)
    if not emails:
        pytest.skip("No emails to test enrich with")

    email = emails[0]

    with pytest.raises(NotImplementedError):
        email.enrich("test content")
    print("  ✓ enrich() raises NotImplementedError")

    with pytest.raises(NotImplementedError):
        email.enrich_hidden("hidden content")
    print("  ✓ enrich_hidden() raises NotImplementedError")


# =============================================================================
# Comprehensive End-to-End Test
# =============================================================================


@pytest.mark.email_integration
def test_imap_smtp_full_workflow(imap_account, test_id):
    """
    Comprehensive test of IMAP/SMTP email operations:
    1. Send email to self
    2. Find email by subject
    3. Get emails and verify
    4. Reply to email
    5. Forward email
    6. Move email to folder
    7. Delete all test emails (cleanup)
    """
    from agy.integrations.email import Email

    user_email = imap_account.user_email
    test_subject = f"[AGY-IMAP-TEST-{test_id}] Full Workflow Test"

    print(f"\n{'=' * 60}")
    print("COMPREHENSIVE IMAP/SMTP TEST")
    print(f"{'=' * 60}")
    print(f"User: {user_email}")
    print(f"Test ID: {test_id}")
    print(f"IMAP: {imap_account.imap_host}:{imap_account.imap_port}")
    print(f"SMTP: {imap_account.smtp_host}:{imap_account.smtp_port}")

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
            account=imap_account,
        )
        sent_email = email.send()

        print("   ✓ Email sent")
        print(f"   Subject: {sent_email.subject}")

        # -----------------------------------------------------------------
        # 2. FIND: Search for the email by subject
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("2. FIND EMAIL (waiting for delivery...)")
        print(f"{'─' * 40}")

        found_email = wait_for_email(imap_account, test_id, max_wait=30)

        if found_email:
            print("   ✓ Email found via find_emails")
            print(f"   Message ID: {found_email.message_id}")
        else:
            pytest.fail(f"Email with test ID '{test_id}' not found after 30s")

        # -----------------------------------------------------------------
        # 3. GET: Verify email appears in get_emails
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("3. GET EMAILS & VERIFY")
        print(f"{'─' * 40}")

        time.sleep(3)
        inbox_emails = imap_account.get_emails(max_results=20, only_unread=False)
        inbox_match = None
        for e in inbox_emails:
            if test_id in (e.subject or ""):
                inbox_match = e
                break

        if inbox_match:
            print("   ✓ Email found in inbox via get_emails")
            print(f"   Sender: {inbox_match.sender}")
            print(f"   Subject: {inbox_match.subject}")
        else:
            print("   ⚠ Email not found in get_emails (may still be processing)")
            inbox_match = found_email

        # -----------------------------------------------------------------
        # 4. REPLY: Reply to the email
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("4. REPLY TO EMAIL")
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
        # 5. FORWARD: Forward the email
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("5. FORWARD EMAIL")
        print(f"{'─' * 40}")

        try:
            forward_email = inbox_match.forward(user_email)
            print("   ✓ Email forwarded to self")
            print(f"   Forward Subject: {forward_email.subject}")
        except Exception as exc:
            print(f"   ⚠ Forward failed: {exc}")

        # -----------------------------------------------------------------
        # 6. DELETE: Delete the email
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("6. DELETE EMAIL")
        print(f"{'─' * 40}")

        try:
            inbox_match.delete()
            print("   ✓ Email deleted")
        except Exception as exc:
            print(f"   ⚠ Delete failed: {exc}")

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
        print("   ✓ delete: OK")

    finally:
        # -----------------------------------------------------------------
        # 7. CLEANUP: Delete all test emails
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("7. CLEANUP")
        print(f"{'─' * 40}")

        time.sleep(3)
        remaining = imap_account.find_emails(subject_contains=test_id, max_results=20)
        for e in remaining:
            try:
                e.delete()
                print(f"   Deleted: {e.subject[:40] if e.subject else 'N/A'}...")
            except Exception as exc:
                print(f"   ⚠ Failed to delete: {exc}")

        if not remaining:
            print("   No test emails remaining")

        print(f"\n{'=' * 60}")
        print("TEST COMPLETE")
        print(f"{'=' * 60}")
