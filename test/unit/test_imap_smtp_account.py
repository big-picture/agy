# test/unit/test_imap_smtp_account.py

"""
Unit tests for ImapSmtpEmailAccount.
"""

from unittest.mock import MagicMock, patch

import pytest

from agy.integrations.email import Email, ImapSmtpEmailAccount


class TestImapSmtpAccountInit:
    """Tests for ImapSmtpEmailAccount initialization."""

    def test_init_with_env_variables(self, monkeypatch):
        """Test initialization using environment variables."""
        monkeypatch.setenv("IMAP_HOST", "imap.test.com")
        monkeypatch.setenv("IMAP_PORT", "993")
        monkeypatch.setenv("IMAP_USER", "user@test.com")
        monkeypatch.setenv("IMAP_PASSWORD", "secret")
        monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
        monkeypatch.setenv("SMTP_PORT", "465")

        account = ImapSmtpEmailAccount()

        assert account.imap_host == "imap.test.com"
        assert account.imap_port == 993
        assert account.imap_user == "user@test.com"
        assert account.imap_password == "secret"
        assert account.smtp_host == "smtp.test.com"
        assert account.smtp_port == 465
        assert account.smtp_user == "user@test.com"
        assert account.smtp_password == "secret"
        assert account.user_email == "user@test.com"

    def test_init_with_explicit_parameters(self):
        """Test initialization with explicit parameters."""
        account = ImapSmtpEmailAccount(
            imap_host="imap.example.com",
            imap_port=993,
            imap_user="user@example.com",
            imap_password="password123",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="smtp_user@example.com",
            smtp_password="smtp_password",
        )

        assert account.imap_host == "imap.example.com"
        assert account.imap_port == 993
        assert account.imap_user == "user@example.com"
        assert account.smtp_host == "smtp.example.com"
        assert account.smtp_port == 587
        assert account.smtp_user == "smtp_user@example.com"
        assert account.smtp_password == "smtp_password"

    def test_init_missing_imap_host_raises(self, monkeypatch):
        """Test that missing IMAP_HOST raises ValueError."""
        monkeypatch.delenv("IMAP_HOST", raising=False)

        with pytest.raises(ValueError, match="IMAP_HOST is required"):
            ImapSmtpEmailAccount(
                imap_user="user@test.com",
                imap_password="secret",
                smtp_host="smtp.test.com",
            )

    def test_init_missing_imap_user_raises(self, monkeypatch):
        """Test that missing IMAP_USER raises ValueError."""
        monkeypatch.delenv("IMAP_USER", raising=False)

        with pytest.raises(ValueError, match="IMAP_USER is required"):
            ImapSmtpEmailAccount(
                imap_host="imap.test.com",
                imap_password="secret",
                smtp_host="smtp.test.com",
            )

    def test_init_missing_smtp_host_raises(self, monkeypatch):
        """Test that missing SMTP_HOST raises ValueError."""
        monkeypatch.delenv("SMTP_HOST", raising=False)

        with pytest.raises(ValueError, match="SMTP_HOST is required"):
            ImapSmtpEmailAccount(
                imap_host="imap.test.com",
                imap_user="user@test.com",
                imap_password="secret",
            )


class TestImapSmtpAccountEnrich:
    """Tests for enrich methods (NotImplementedError)."""

    @pytest.fixture
    def account(self):
        """Create account for testing."""
        return ImapSmtpEmailAccount(
            imap_host="imap.test.com",
            imap_user="user@test.com",
            imap_password="secret",
            smtp_host="smtp.test.com",
        )

    def test_enrich_email_raises_not_implemented(self, account):
        """Test that enrich_email raises NotImplementedError."""
        email = Email(
            sender="sender@test.com",
            recipient="user@test.com",
            subject="Test",
            text="Content",
            message_id="123",
            account=account,
        )

        with pytest.raises(NotImplementedError, match="enrich_email is not supported"):
            email.enrich("Some content")

    def test_enrich_email_hidden_raises_not_implemented(self, account):
        """Test that enrich_email_hidden raises NotImplementedError."""
        email = Email(
            sender="sender@test.com",
            recipient="user@test.com",
            subject="Test",
            text="Content",
            message_id="123",
            account=account,
        )

        with pytest.raises(
            NotImplementedError, match="enrich_email_hidden is not supported"
        ):
            email.enrich_hidden("Hidden content")


class TestImapSmtpAccountWithMockedConnections:
    """Tests with mocked IMAP/SMTP connections."""

    @pytest.fixture
    def account(self):
        """Create account for testing."""
        return ImapSmtpEmailAccount(
            imap_host="imap.test.com",
            imap_user="user@test.com",
            imap_password="secret",
            smtp_host="smtp.test.com",
        )

    @patch("agy.integrations.email.imap_smtp_account.imaplib.IMAP4_SSL")
    def test_get_emails_connects_to_imap(self, mock_imap_class, account):
        """Test that get_emails connects to IMAP server."""
        mock_imap = MagicMock()
        mock_imap_class.return_value = mock_imap
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.uid.return_value = ("OK", [b""])

        account.get_emails()

        mock_imap_class.assert_called_once_with("imap.test.com", 993)
        mock_imap.login.assert_called_once_with("user@test.com", "secret")
        mock_imap.logout.assert_called_once()

    @patch("agy.integrations.email.imap_smtp_account.smtplib.SMTP_SSL")
    @patch("agy.integrations.email.email_safety.get_validator")
    def test_send_email_connects_to_smtp(
        self, mock_validator, mock_smtp_class, account
    ):
        """Test that send_email connects to SMTP server."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp
        mock_validator.return_value.validate_forward.return_value = (True, None)

        email = Email(
            recipient="recipient@test.com",
            subject="Test Subject",
            text="Test body",
            account=account,
        )

        account.send_email(email)

        mock_smtp_class.assert_called_once_with("smtp.test.com", 465)
        mock_smtp.login.assert_called_once_with("user@test.com", "secret")
        mock_smtp.send_message.assert_called_once()
        mock_smtp.quit.assert_called_once()

    def test_mark_unread_email_clears_seen_flag(self, account):
        """Test that mark_unread_email clears the IMAP \\Seen flag."""
        mock_imap = MagicMock()
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.uid.return_value = ("OK", [b""])
        account._connect_imap = MagicMock(return_value=mock_imap)
        email = Email(
            sender="sender@test.com",
            recipient="user@test.com",
            subject="Test",
            text="Content",
            message_id="123",
            account=account,
            _folder="INBOX",
        )

        account.mark_unread_email(email)

        mock_imap.select.assert_called_once_with("INBOX")
        mock_imap.uid.assert_called_once_with("store", "123", "-FLAGS", "(\\Seen)")
        mock_imap.logout.assert_called_once()
        assert email._is_unread is True

    def test_reply_email_requires_message_id(self, account):
        """Test that reply_email requires message_id."""
        email = Email(
            sender="sender@test.com",
            recipient="user@test.com",
            subject="Test",
            text="Content",
            account=account,
        )

        with pytest.raises(ValueError, match="message_id is required"):
            account.reply_email(email, "Reply text")

    def test_forward_email_requires_message_id(self, account):
        """Test that forward_email requires message_id."""
        email = Email(
            sender="sender@test.com",
            recipient="user@test.com",
            subject="Test",
            text="Content",
            account=account,
        )

        with pytest.raises(ValueError, match="message_id is required"):
            account.forward_email(email, "forward@test.com")

    def test_move_email_requires_message_id(self, account):
        """Test that move_email requires message_id."""
        email = Email(
            sender="sender@test.com",
            recipient="user@test.com",
            subject="Test",
            text="Content",
            account=account,
        )

        with pytest.raises(ValueError, match="message_id is required"):
            account.move_email(email, "Archive")

    def test_delete_email_requires_message_id(self, account):
        """Test that delete_email requires message_id."""
        email = Email(
            sender="sender@test.com",
            recipient="user@test.com",
            subject="Test",
            text="Content",
            account=account,
        )

        with pytest.raises(ValueError, match="message_id is required"):
            account.delete_email(email)

    def test_mark_unread_email_requires_message_id(self, account):
        """Test that mark_unread_email requires message_id."""
        email = Email(
            sender="sender@test.com",
            recipient="user@test.com",
            subject="Test",
            text="Content",
            account=account,
        )

        with pytest.raises(ValueError, match="message_id is required"):
            account.mark_unread_email(email)
