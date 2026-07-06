# Email Integration

This guide explains how to integrate email processing into AGY flows, enabling
automated email classification, responses, and routing.

## Overview

The email integration provides:

- **Email Account Connectors**: Microsoft Graph (Office 365), Gmail, generic
  IMAP/SMTP, and a file-based Mock for testing
- **Email Operations**: Fetch, search, send, reply, forward, move, delete, mark unread
- **Flow Integration**: Pass emails as context to AGY flows for automated
  processing

## Quick Start

Install email integration dependencies first:

```bash
uv add agy
```

```python
import asyncio
from agy import Flow
from agy.integrations.email import GraphEmailAccount

async def main():
    # 1. Connect to email account
    account = GraphEmailAccount(user_email="support@company.com")

    # 2. Fetch unread emails
    emails = account.get_emails(only_unread=True, max_results=10)

    # 3. Load the flow
    flow = Flow.from_flowsy("flows/email_routing.flowsy")

    # 4. Process each email with the flow
    for email in emails:
        result = await flow.run(context_in={"email": email})

asyncio.run(main())
```

## Tutorial: Email Classification Flow

This tutorial shows how to build a flow that classifies incoming emails and
either answers questions from a FAQ or sends a standard reply.

### Step 1: Define the Flow

Create `flows/email_routing.flowsy`:

```flowsy
name: Email Routing Flow
description: Classify emails and route to appropriate handlers

context_in:
  email: Email

nodes:
  classify_email:
    actions:
      - show("Classifying email...")
      - category = classify(input_text=email.text, categories=["question", "complaint", "other"])
      - show("Category:", category, "Confidence:", confidence)
    edges:
      - confidence < 0.8: manual_review
      - category == "question": answer_question
      - category == "complaint": handle_complaint
      - default: manual_review

  answer_question:
    actions:
      - show("Generating FAQ response...")
      - faq_data = load_files_text("data/faq.md")
      - response = respond(input_text=email.text, instruction_file="prompts/answer_question.md", augmentation=faq_data)
      - email.reply(response)
      - email.move("processed")
      - show("Question answered and email moved")
    edges:
      - default: end

  handle_complaint:
    actions:
      - show("Sending complaint acknowledgment...")
      - reply_text = "Thank you for your feedback. Our team will review your concern and respond within 24 hours."
      - email.reply(reply_text)
      - email.move("complaints")
      - show("Complaint acknowledged")
    edges:
      - default: end

  manual_review:
    actions:
      - show("Email requires manual review")
      - email.move("manual_review")
    edges:
      - default: end
```

### Step 2: Create the Main Script

Create `main.py`:

```python
import asyncio
from agy import Flow
from agy.integrations.email import GraphEmailAccount

async def process_emails():
    # Connect to email account
    account = GraphEmailAccount(user_email="support@company.com")

    # Fetch unread emails from inbox
    emails = account.get_emails(
        folders=["inbox"],
        only_unread=True,
        max_results=20
    )

    print(f"Found {len(emails)} unread emails")

    # Load flow once
    flow = Flow.from_flowsy("flows/email_routing.flowsy")

    for email in emails:
        print(f"\nProcessing: {email.subject}")

        # Execute the flow with email as context
        result = await flow.run(context_in={"email": email})

        print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(process_emails())
```

### Step 3: Create Supporting Files

*prompts/answer_question.md:*

```markdown
# Answer Customer Question

You are a helpful customer service representative. Answer the customer's
question based on the FAQ data provided. [...]
```

*data/faq.md:*

```markdown
# Frequently Asked Questions

## Shipping

- Standard shipping takes 5-7 business days [...]
```

For complete examples, see the email routing templates:

- [email_routing_mock](../../src/agy/templates/email_routing_mock/) - Local testing
  with mock mailbox
- [email_routing_imap_smtp](../../src/agy/templates/email_routing_imap_smtp/) - Any
  IMAP/SMTP provider
- [email_routing_graph](../../src/agy/templates/email_routing_graph/) - Microsoft
  365 / Office 365
- [email_routing_gmail](../../src/agy/templates/email_routing_gmail/) - Gmail with
  OAuth 2.0

---

## API Reference

### Email Class

The `Email` class represents an email message with bound account methods.

#### Attributes

| Attribute     | Type                   | Description                 |
| ------------- | ---------------------- | --------------------------- |
| `sender`      | `str`                  | Sender email address        |
| `recipient`   | `str`                  | Recipient email address(es) |
| `subject`     | `str`                  | Email subject               |
| `text`        | `str`                  | Email body text             |
| `cc`          | `str`                  | CC recipients               |
| `reply_to`    | `str`                  | Reply-to address            |
| `message_id`  | `str \| None`          | Unique message identifier   |
| `attachments` | `list[Attachment]`     | List of attachments         |
| `account`     | `EmailAccount \| None` | Bound email account         |

#### Methods

| Method                                                                                           | Returns | Description                                                                                                                                              |
| ------------------------------------------------------------------------------------------------ | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Email.create(to, subject, text, sender="", cc="", attachments=None, account=None, folder=None)` | `Email` | Create a new email (class method)                                                                                                                        |
| `send()`                                                                                         | `Email` | Send this email                                                                                                                                          |
| `reply(text, *, subject=None, attachments=None)`                                                 | `Email` | Reply to the sender. `text`: body; `subject`: override reply subject (optional); `attachments`: list of `Attachment` objects (optional)                     |
| `reply_all(text, *, subject=None, attachments=None)`                                             | `Email` | Reply to all recipients. Same parameters as `reply()`.                                                                                                    |
| `forward(to)`                                                                                    | `Email` | Forward this email. `to`: recipient email address (str)                                                                                                  |
| `move(folder)`                                                                                   | `None`  | Move to a folder. `folder`: target folder name (str, e.g. "processed", "archive")                                                                        |
| `delete()`                                                                                       | `None`  | Delete this email (moves to trash)                                                                                                                       |
| `mark_unread()`                                                                                  | `None`  | Mark this email as unread again so it reappears in unread-focused workflows                                                                              |
| `enrich(content)`                                                                                | `None`  | Add visible annotation to email body. `content`: text or dict with 'result' key. Raises `NotImplementedError` for Gmail and IMAP/SMTP (immutable bodies) |
| `enrich_hidden(content)`                                                                         | `None`  | Add hidden annotation. Raises `NotImplementedError` (not supported)                                                                                      |

*Example:*

```python
from agy.integrations.email import Attachment, Email

# Create and send a new email
email = Email.create(
    to="customer@example.com",
    subject="Your Order Confirmation",
    text="Thank you for your order!",
    account=account
)
email.send()

# Reply to sender
email.reply("Thank you for contacting us!")

# Reply with custom subject and attachment
email.reply(
    "See attached report.",
    subject="Updated Report",
    attachments=[Attachment.from_path("report.pdf")],
)

# Reply to all recipients
email.reply_all("Thanks everyone, see my response below.")

# Move email to a folder
email.move("processed")
```

### EmailAccount Class

Abstract base class for email account implementations. All account types
implement these methods.

#### Methods

| Method                                                                                                                                                                                     | Returns       | Description               |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------- | ------------------------- |
| `get_emails(folders=None, max_results=100, only_unread=False)`                                                                                                                             | `list[Email]` | Fetch emails from account |
| `find_emails(folders=None, max_results=100, to_contains=None, from_contains=None, cc_contains=None, subject_contains=None, body_contains=None, has_attachments=None, email_contains=None)` | `list[Email]` | Search for emails         |
| `send_email(email)`                                                                                                                                                                        | `Email`       | Send an email             |
| `mark_unread_email(email)`                                                                                                                                                                 | `None`        | Mark an existing email as unread |

*Example:*

```python
# Fetch unread emails
emails = account.get_emails(only_unread=True, max_results=10)

# Search for emails
results = account.find_emails(
    subject_contains="invoice",
    from_contains="billing@",
    has_attachments=True
)

# Delete an email
account.delete_email(email)

# Mark an email unread again
account.mark_unread_email(email)
```

### Attachment Class

Represents an email attachment.

| Attribute      | Type    | Description         |
| -------------- | ------- | ------------------- |
| `filename`     | `str`   | Attachment filename |
| `content`      | `bytes` | File content        |
| `content_type` | `str`   | MIME type           |

*Example:*

```python
from agy.integrations.email import Attachment

# Create attachment from file
attachment = Attachment.from_path("invoice.pdf")

# Create email with attachments
email = Email.create(
    to="customer@example.com",
    subject="Your Invoice",
    text="Please find your invoice attached.",
    attachments=["invoice.pdf", "receipt.pdf"],
    account=account
)
```

---

## Account Configuration

### GraphEmailAccount (Microsoft 365)

For Microsoft 365 / Office 365 mailboxes using the Microsoft Graph API.

#### Prerequisites

1. Azure AD App Registration with Mail.ReadWrite and Mail.Send permissions
2. Client credentials (tenant ID, client ID, client secret)

### Environment Variables

| Variable             | Required | Description                                    |
| -------------------- | -------- | ---------------------------------------------- |
| `TENANT_ID`          | Yes      | Azure AD tenant ID                             |
| `CLIENT_ID`          | Yes      | Azure AD application (client) ID               |
| `CLIENT_SECRET`      | Yes      | Azure AD application client secret             |
| `USER_EMAIL`         | No       | User principal name (email address)            |
| `SHARED_MAILBOX_UPN` | No       | Shared mailbox UPN (alternative to USER_EMAIL) |

#### Example .env

```env
TENANT_ID=12345678-1234-1234-1234-123456789012
CLIENT_ID=abcdefgh-abcd-abcd-abcd-abcdefghijkl
CLIENT_SECRET=your-client-secret-here
USER_EMAIL=support@company.com
```

#### Usage

```python
from agy.integrations.email import GraphEmailAccount

# Using environment variables
account = GraphEmailAccount()

# Or with explicit parameters
account = GraphEmailAccount(user_email="support@company.com")
```

#### Nested Folders

GraphEmailAccount supports nested folder paths using `/` as separator:

```python
# Top-level folder
emails = account.get_emails(folders=["Inbox"])

# Nested folders (e.g., logistics/logistics_inbox)
emails = account.get_emails(folders=["logistics/logistics_inbox"])

# Multiple nested paths
emails = account.get_emails(folders=[
    "Projects/Active/2024",
    "logistics/processed"
])

# Move to nested folder
email.move("Archive/2024/January")
```

**Supported aliases** (work at any level):

- `sent` → "Sent Items"
- `deleted`, `trash` → "Deleted Items"
- `junk`, `spam` → "Junk Email"
- German: `posteingang`, `gesendete elemente`, `papierkorb`, etc.

---

### GmailEmailAccount

For Gmail accounts using OAuth 2.0 authentication.

#### Prerequisites

1. Google Cloud Project with Gmail API enabled
2. OAuth 2.0 credentials (client ID, client secret)
3. OAuth token file (generated via authorization flow)

#### Environment Variables

| Variable              | Required | Default                    | Description                                  |
| --------------------- | -------- | -------------------------- | -------------------------------------------- |
| `GMAIL_AUTH_MODE`     | No       | `oauth`                    | Authentication mode (only `oauth` supported) |
| `GMAIL_CLIENT_ID`     | Yes      | -                          | Google OAuth 2.0 client ID                   |
| `GMAIL_CLIENT_SECRET` | Yes      | -                          | Google OAuth 2.0 client secret               |
| `GMAIL_TOKEN_FILE`    | Yes      | `token.json`               | Path to OAuth token file                     |
| `GMAIL_USER`          | No       | `me`                       | Gmail user identifier                        |
| `GMAIL_SCOPES`        | No       | gmail.modify, gmail.labels | Space-separated OAuth scopes                 |

#### Example .env

```env
GMAIL_AUTH_MODE=oauth
GMAIL_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-your-secret-here
GMAIL_TOKEN_FILE=path/to/token.json
GMAIL_USER=user@gmail.com
```

#### OAuth Token Setup

To generate the OAuth token file, run:

```python
from agy.integrations.email._gmail_api import obtain_oauth_token
obtain_oauth_token()
```

This opens a browser for authentication and saves the token to
`GMAIL_TOKEN_FILE`.

#### Usage

```python
from agy.integrations.email import GmailEmailAccount

account = GmailEmailAccount()
emails = account.get_emails(only_unread=True)
```

---

### ImapSmtpEmailAccount (Generic IMAP/SMTP)

For any email provider supporting standard IMAP and SMTP protocols.

#### Prerequisites

1. IMAP server access (typically port 993 for SSL)
2. SMTP server access (typically port 465 for SSL or 587 for STARTTLS)
3. Email account credentials

#### Environment Variables

| Variable        | Required | Default       | Description                               |
| --------------- | -------- | ------------- | ----------------------------------------- |
| `IMAP_HOST`     | Yes      | -             | IMAP server hostname                      |
| `IMAP_PORT`     | No       | `993`         | IMAP server port                          |
| `IMAP_USER`     | Yes      | -             | IMAP username (email address)             |
| `IMAP_PASSWORD` | Yes      | -             | IMAP password                             |
| `SMTP_HOST`     | Yes      | -             | SMTP server hostname                      |
| `SMTP_PORT`     | No       | `465`         | SMTP server port                          |
| `SMTP_USER`     | No       | IMAP_USER     | SMTP username (defaults to IMAP_USER)     |
| `SMTP_PASSWORD` | No       | IMAP_PASSWORD | SMTP password (defaults to IMAP_PASSWORD) |

#### Example .env

```env
IMAP_HOST=imap.example.com
IMAP_PORT=993
IMAP_USER=user@example.com
IMAP_PASSWORD=your-password-here
SMTP_HOST=smtp.example.com
SMTP_PORT=465
```

#### Usage

```python
from agy.integrations.email import ImapSmtpEmailAccount

# Using environment variables
account = ImapSmtpEmailAccount()

# Or with explicit parameters
account = ImapSmtpEmailAccount(
    imap_host="imap.example.com",
    imap_user="user@example.com",
    imap_password="password",
    smtp_host="smtp.example.com",
)
emails = account.get_emails(only_unread=True)
```

#### Limitations

- `enrich()` and `enrich_hidden()` raise `NotImplementedError` (IMAP message
  bodies are immutable)

---

### MockEmailAccount (Testing)

File-based mock account for testing. Stores emails as `.eml` files in
subdirectories.

#### No Environment Variables Required

#### Constructor Parameters

| Parameter    | Type          | Default            | Description                      |
| ------------ | ------------- | ------------------ | -------------------------------- |
| `base_path`  | `str \| Path` | Required           | Root directory for email storage |
| `user_email` | `str`         | `mock@example.com` | Email address for this account   |

#### Directory Structure

```text
base_path/
├── inbox/
│   ├── email1.eml
│   └── email2.eml
├── sent/
│   └── email3.eml
├── drafts/
└── trash/
```

#### Usage

```python
from agy.integrations.email import MockEmailAccount

# Create mock account
account = MockEmailAccount(
    base_path="./test_mailbox",
    user_email="test@example.com"
)

# Add test emails
account.add_email(
    folder="inbox",
    sender="customer@example.com",
    recipient="test@example.com",
    subject="Test Email",
    text="This is a test email."
)

# Fetch and process
emails = account.get_emails()

# Cleanup
account.clear_folder("inbox")
```

---

## Safety Configuration

The email integration includes safety checks to prevent sending emails to
unauthorized recipients.

### Environment Variables

| Variable                  | Default           | Description                                          |
| ------------------------- | ----------------- | ---------------------------------------------------- |
| `ALLOWED_EMAIL_DOMAINS`   | `big-picture.com` | Comma-separated list of allowed domains              |
| `ALLOWED_EMAIL_ADDRESSES` | (empty)           | Comma-separated list of explicitly allowed addresses |
| `EMAIL_DRAFT_ONLY`        | (unset)           | If `true`/`1`/`yes`, save sends/replies/forwards as drafts only (no outbound send) |

### Example

```env
ALLOWED_EMAIL_DOMAINS=company.com,partner.com,trusted-vendor.com
ALLOWED_EMAIL_ADDRESSES=external-contact@other.com,vip@special.org
```

Emails can only be sent to recipients matching:

- An address in `ALLOWED_EMAIL_ADDRESSES`, OR
- A domain in `ALLOWED_EMAIL_DOMAINS`

When **draft-only** mode is active (`EMAIL_DRAFT_ONLY` or per-call `draft_only=True` on
`email.send()`, `email.reply()`, `email.reply_all()`, `email.forward()`), messages are
saved as drafts instead of sent; allowlist checks are skipped for those operations so
staging tests can build drafts for any address.

To reset safety settings (e.g., in tests):

```python
from agy.integrations.email.email_safety import reset_validator
reset_validator()
```

---

## See Also

- [Flow Documentation](../agy/FLOW.md) - AGY flow basics
- [Actions Reference](../agy/ACTIONS_REFERENCE.md) - Built-in actions (classify,
  respond, etc.)
- [Jira Integration](JIRA.md) - Object-first Jira integration guide
- Email Routing Templates:
  - [email_routing_mock](../../src/agy/templates/email_routing_mock/) - Local
    testing
  - [email_routing_imap_smtp](../../src/agy/templates/email_routing_imap_smtp/) -
    IMAP/SMTP
  - [email_routing_graph](../../src/agy/templates/email_routing_graph/) - Microsoft
    Graph
  - [email_routing_gmail](../../src/agy/templates/email_routing_gmail/) - Gmail API
