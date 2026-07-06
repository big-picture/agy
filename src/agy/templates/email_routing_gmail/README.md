# Email Routing Template (Gmail)

This template demonstrates email routing using AGY flows with
**GmailEmailAccount** using OAuth 2.0 authentication.

## What it does

The flow processes travel insurance customer emails and automatically:

- **Classifies** emails into categories: `question`, `new_claim`,
  `wrong_department`, or `unclear`
- **Answers coverage questions** using policy Terms & Conditions via LLM
- **Processes claims** by extracting claim data and validating completeness
- **Routes wrong department emails** to appropriate insurance departments
- **Escalates unclear requests** to human support

## Getting Started

1. **Set up Google Cloud Project**:
   - Go to <https://console.cloud.google.com>
   - Create a new project or select existing
   - Enable the Gmail API
   - Go to APIs & Services > Credentials
   - Create OAuth 2.0 Client ID (Desktop app)
   - Download the credentials

2. **Set up environment variables**:

   ```bash
   cp .env.example .env
   # Edit .env and add your credentials:
   # - OPENAI_API_KEY
   # - GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET
   # - GMAIL_USER
   # - ALLOWED_EMAIL_DOMAINS
   ```

3. **Run the flow** (first run will open browser for OAuth):

   ```bash
   python main.py
   ```

   On first run, a browser window opens for Google authentication. After
   approval, the token is saved to `GMAIL_TOKEN_FILE`.

## Project Structure

```text
email_routing_gmail/
├── main.py                      # Entry point using GmailEmailAccount
├── email_routing_flow.flowsy    # Flow definition (no email.enrich)
├── .env.example                 # Environment variables template
├── pyproject.toml               # Project configuration
├── prompts/                     # LLM instruction prompts
│   ├── classify_insurance_email.md
│   ├── answer_terms_question.md
│   └── extract_claim_data.md
├── data/                        # Reference data
│   └── Travel_Insurance_Terms.md
└── objects/                     # Python modules
    ├── __init__.py
    └── claim_functions.py       # validate_claim, submit_claim
```

## Email Account

This template uses `GmailEmailAccount` from `agy.integrations.email`:

```python
from agy.integrations.email import GmailEmailAccount

# Credentials from environment variables
account = GmailEmailAccount()

emails = account.get_emails(only_unread=True)
```

## Limitations

- `email.enrich()` is not available (Gmail message bodies are immutable)
- Requires OAuth authentication (browser-based on first run)
- Uses Gmail labels instead of folders for `email.move()`

## OAuth Token Setup

To generate the OAuth token file manually:

```python
from agy.integrations.email._gmail_api import obtain_oauth_token
obtain_oauth_token()
```

This opens a browser for authentication and saves the token to
`GMAIL_TOKEN_FILE`.

## See Also

- [Email Integration Documentation](../../../docs/integrations/EMAIL.md)
- Other email routing templates: `email_routing_mock`,
  `email_routing_imap_smtp`, `email_routing_graph`
