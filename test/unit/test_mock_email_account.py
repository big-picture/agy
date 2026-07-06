# test/unit/test_mock_email_account.py

"""
Unit tests for MockEmailAccount (file-based email mock).
"""

import tempfile

import pytest

from agy.integrations.email import Email, MockEmailAccount


@pytest.fixture
def mock_account():
    """Create a temporary mock account for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        account = MockEmailAccount(base_path=tmpdir, user_email="test@example.com")
        yield account


class TestMockEmailAccount:
    """Tests for MockEmailAccount."""

    def test_init_creates_default_folders(self, mock_account):
        """Test that default folders are created on init."""
        base_path = mock_account.base_path
        assert (base_path / "inbox").exists()
        assert (base_path / "sent").exists()
        assert (base_path / "drafts").exists()
        assert (base_path / "trash").exists()

    def test_add_email_creates_eml_file(self, mock_account):
        """Test that add_email creates a .eml file."""
        email = mock_account.add_email(
            folder="inbox",
            sender="sender@example.com",
            recipient="test@example.com",
            subject="Test Subject",
            text="Hello, World!",
        )

        assert email.message_id is not None
        assert email.account is mock_account

        # Verify file was created
        inbox_files = list((mock_account.base_path / "inbox").glob("*.eml"))
        assert len(inbox_files) == 1

    def test_get_emails_returns_added_emails(self, mock_account):
        """Test that get_emails returns emails that were added."""
        # Add some emails
        mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="Email from Alice",
            text="Hello from Alice",
        )
        mock_account.add_email(
            folder="inbox",
            sender="bob@example.com",
            recipient="test@example.com",
            subject="Email from Bob",
            text="Hello from Bob",
        )

        emails = mock_account.get_emails(folders=["inbox"])
        assert len(emails) == 2

        subjects = {e.subject for e in emails}
        assert "Email from Alice" in subjects
        assert "Email from Bob" in subjects

    def test_find_emails_filters_by_subject(self, mock_account):
        """Test that find_emails filters by subject."""
        mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="Important Meeting",
            text="Let's meet!",
        )
        mock_account.add_email(
            folder="inbox",
            sender="bob@example.com",
            recipient="test@example.com",
            subject="Lunch Plans",
            text="Let's have lunch",
        )

        emails = mock_account.find_emails(subject_contains="Meeting")
        assert len(emails) == 1
        assert emails[0].subject == "Important Meeting"

    def test_find_emails_filters_by_sender(self, mock_account):
        """Test that find_emails filters by sender."""
        mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="Email 1",
            text="Hello",
        )
        mock_account.add_email(
            folder="inbox",
            sender="bob@example.com",
            recipient="test@example.com",
            subject="Email 2",
            text="Hello",
        )

        emails = mock_account.find_emails(from_contains="alice")
        assert len(emails) == 1
        assert "alice" in emails[0].sender

    def test_find_emails_general_search(self, mock_account):
        """Test that find_emails searches across all fields."""
        mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="Project Update",
            text="The project is going well!",
        )
        mock_account.add_email(
            folder="inbox",
            sender="bob@example.com",
            recipient="test@example.com",
            subject="Weekend Plans",
            text="Let's meet this weekend",
        )

        emails = mock_account.find_emails(email_contains="project")
        assert len(emails) == 1
        assert emails[0].subject == "Project Update"

    def test_send_email_saves_to_sent(self, mock_account):
        """Test that send_email saves to sent folder."""
        email = Email.create(
            to="recipient@example.com",
            subject="Test Send",
            text="Sending this email",
            account=mock_account,
        )

        sent = email.send()
        assert sent.sender == "test@example.com"
        assert sent.message_id is not None

        # Verify in sent folder
        sent_emails = mock_account.get_emails(folders=["sent"])
        assert len(sent_emails) == 1
        assert sent_emails[0].subject == "Test Send"

    def test_reply_email(self, mock_account):
        """Test that reply creates a reply in sent folder."""
        original = mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="Question",
            text="Do you have time?",
        )

        reply = original.reply("Yes, I do!")
        assert "Re:" in reply.subject
        assert reply.recipient == "alice@example.com"
        assert "Yes, I do!" in reply.text

        # Verify reply is in sent
        sent_emails = mock_account.get_emails(folders=["sent"])
        assert len(sent_emails) == 1

    def test_forward_email(self, mock_account):
        """Test that forward creates a forwarded email in sent folder."""
        original = mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="FYI",
            text="Some information",
        )

        forwarded = original.forward("bob@example.com")
        assert "FW:" in forwarded.subject
        assert forwarded.recipient == "bob@example.com"

        # Verify forward is in sent
        sent_emails = mock_account.get_emails(folders=["sent"])
        assert len(sent_emails) == 1

    def test_move_email(self, mock_account):
        """Test that move_email moves email to another folder."""
        email = mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="To be moved",
            text="Move me!",
        )

        email.move("archive")

        # Verify not in inbox
        inbox_emails = mock_account.get_emails(folders=["inbox"])
        assert len(inbox_emails) == 0

        # Verify in archive
        archive_emails = mock_account.get_emails(folders=["archive"])
        assert len(archive_emails) == 1
        assert archive_emails[0].subject == "To be moved"

    def test_delete_email_moves_to_trash(self, mock_account):
        """Test that delete_email moves to trash."""
        email = mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="To delete",
            text="Delete me!",
        )

        mock_account.delete_email(email)

        # Verify not in inbox
        inbox_emails = mock_account.get_emails(folders=["inbox"])
        assert len(inbox_emails) == 0

        # Verify in trash
        trash_emails = mock_account.get_emails(folders=["trash"])
        assert len(trash_emails) == 1

    def test_email_delete_method(self, mock_account):
        """Test email.delete() method."""
        email = mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="To delete via method",
            text="Delete me via email.delete()!",
        )

        # Use email.delete() instead of account.delete_email()
        email.delete()

        # Verify not in inbox
        inbox_emails = mock_account.get_emails(folders=["inbox"])
        assert len(inbox_emails) == 0

        # Verify in trash
        trash_emails = mock_account.get_emails(folders=["trash"])
        assert len(trash_emails) == 1

    def test_mark_unread_restores_email_to_unread_filter(self, mock_account):
        """Test that mark_unread makes an email visible to unread-only queries."""
        email = mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="Mark unread",
            text="Unread me again",
        )
        email._is_unread = False
        mock_account._save_email(email, "inbox")

        assert mock_account.get_emails(folders=["inbox"], only_unread=True) == []

        email.mark_unread()

        unread_emails = mock_account.get_emails(folders=["inbox"], only_unread=True)
        assert len(unread_emails) == 1
        assert unread_emails[0].subject == "Mark unread"

    def test_add_label_persists_and_has_label_reads_it(self, mock_account):
        """Test that labels persist on the mock email object and mailbox copy."""
        email = mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="Label me",
            text="Track me",
        )

        email.add_label("Erledigt")

        assert email.has_label("Erledigt") is True
        inbox_emails = mock_account.get_emails(folders=["inbox"])
        assert len(inbox_emails) == 1
        assert inbox_emails[0].has_label("Erledigt") is True

    def test_clear_folder(self, mock_account):
        """Test that clear_folder removes all emails."""
        mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="Email 1",
            text="Hello",
        )
        mock_account.add_email(
            folder="inbox",
            sender="bob@example.com",
            recipient="test@example.com",
            subject="Email 2",
            text="Hello",
        )

        count = mock_account.clear_folder("inbox")
        assert count == 2

        emails = mock_account.get_emails(folders=["inbox"])
        assert len(emails) == 0

    def test_email_without_account_raises_error(self):
        """Test that email methods raise error without account."""
        email = Email(
            sender="alice@example.com",
            recipient="test@example.com",
            subject="Test",
            text="Hello",
        )

        with pytest.raises(ValueError, match="no bound account"):
            email.send()

    def test_email_create_static_method(self, mock_account):
        """Test Email.create static method."""
        email = Email.create(
            to="recipient@example.com",
            subject="Created Email",
            text="This was created",
            sender="sender@example.com",
            cc="cc@example.com",
            account=mock_account,
        )

        assert email.recipient == "recipient@example.com"
        assert email.subject == "Created Email"
        assert email.text == "This was created"
        assert email.sender == "sender@example.com"
        assert email.cc == "cc@example.com"
        assert email.account is mock_account

    def test_email_create_with_folder_saves_draft(self, mock_account):
        """Test Email.create with folder saves as draft."""
        email = Email.create(
            to="recipient@example.com",
            subject="Draft Email",
            text="This is a draft",
            account=mock_account,
            folder="drafts",
        )

        assert email.message_id is not None

        # Verify in drafts
        drafts = mock_account.get_emails(folders=["drafts"])
        assert len(drafts) == 1
        assert drafts[0].subject == "Draft Email"

    def test_enrich_email(self, mock_account):
        """Test that enrich_email adds content to the email."""
        email = mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="To enrich",
            text="Original content",
        )

        email.enrich("Additional information")

        # Reload and verify
        emails = mock_account.get_emails(folders=["inbox"])
        assert len(emails) == 1
        assert "Enrichment" in emails[0].text
        assert "Additional information" in emails[0].text
        assert "Original content" in emails[0].text

    def test_enrich_email_hidden_raises_not_implemented(self, mock_account):
        """Test that enrich_email_hidden raises NotImplementedError."""
        email = mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="Test email",
            text="Content",
        )

        with pytest.raises(NotImplementedError):
            email.enrich_hidden("Hidden content")

    def test_max_results_limits_output(self, mock_account):
        """Test that max_results limits the number of emails returned."""
        for i in range(10):
            mock_account.add_email(
                folder="inbox",
                sender=f"sender{i}@example.com",
                recipient="test@example.com",
                subject=f"Email {i}",
                text=f"Content {i}",
            )

        emails = mock_account.get_emails(max_results=5)
        assert len(emails) == 5

    def test_copy_email_to_folder(self, mock_account):
        """Test that copy keeps original and places a copy in the target folder."""
        original = mock_account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="test@example.com",
            subject="Copy me",
            text="Hello",
        )

        original.copy("processed")

        # Original still in inbox
        inbox_emails = mock_account.get_emails(folders=["inbox"])
        assert len(inbox_emails) == 1
        assert inbox_emails[0].subject == "Copy me"

        # Copy present in target folder
        processed_emails = mock_account.get_emails(folders=["processed"])
        assert len(processed_emails) == 1
        assert processed_emails[0].subject == "Copy me"

        # original Email object _folder is unchanged
        assert original._folder == "inbox"

    def test_copy_email_no_message_id_raises(self, mock_account):
        """Test that copying an email without message_id raises ValueError."""
        email = Email(
            sender="alice@example.com",
            recipient="test@example.com",
            subject="No ID",
            text="Hello",
            account=mock_account,
        )

        with pytest.raises(ValueError, match="message_id is required to copy"):
            email.copy("processed")
