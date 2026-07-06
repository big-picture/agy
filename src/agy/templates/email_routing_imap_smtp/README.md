# Email Routing Template (IMAP/SMTP)

This template demonstrates email routing using AGY flows with
**ImapSmtpEmailAccount** for any email provider supporting standard IMAP and
SMTP protocols.

## What it does

The flow processes travel insurance customer emails and automatically:

- **Classifies** emails into categories: `question`, `new_claim`,
  `wrong_department`, or `unclear`
- **Answers coverage questions** using policy Terms & Conditions via LLM
- **Processes claims** by extracting claim data and validating completeness
- **Routes wrong department emails** to appropriate insurance departments
- **Escalates unclear requests** to human support

## Getting Started

1. **Set up environment variables**:

   ```bash
   cp .env.example .env
   # Edit .env and add your credentials:
   # - OPENAI_API_KEY
   # - IMAP_HOST, IMAP_USER, IMAP_PASSWORD
   # - SMTP_HOST (SMTP_USER/PASSWORD optional, defaults to IMAP)
   # - ALLOWED_EMAIL_DOMAINS (safety setting)
   ```

2. **For Gmail**: Create an App Password at
   <https://myaccount.google.com/apppasswords>

   ```env
   IMAP_HOST=imap.gmail.com
   SMTP_HOST=smtp.gmail.com
   ```

3. **Run the flow**:

   ```bash
   python main.py
   ```

   This fetches unread emails and processes them through the flow.

## Project Structure

```text
email_routing_imap_smtp/
├── main.py                      # Entry point using ImapSmtpEmailAccount
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

This template uses `ImapSmtpEmailAccount` from `agy.integrations.email`:

```python
from agy.integrations.email import ImapSmtpEmailAccount

# Credentials from environment variables
account = ImapSmtpEmailAccount()

# Or with explicit parameters
account = ImapSmtpEmailAccount(
    imap_host="imap.gmail.com",
    imap_user="your-email@gmail.com",
    imap_password="your-app-password",
    smtp_host="smtp.gmail.com",
)

emails = account.get_emails(only_unread=True)
```

## Limitations

- `email.enrich()` is not available (IMAP message bodies are immutable)
- Requires network access to email servers

## Common IMAP/SMTP Settings

| Provider        | IMAP Host             | IMAP Port | SMTP Host           | SMTP Port |
| --------------- | --------------------- | --------- | ------------------- | --------- |
| Gmail           | imap.gmail.com        | 993       | smtp.gmail.com      | 465       |
| Outlook/Hotmail | outlook.office365.com | 993       | smtp.office365.com  | 587       |
| Yahoo           | imap.mail.yahoo.com   | 993       | smtp.mail.yahoo.com | 465       |

## See Also

- [Email Integration Documentation](../../../docs/integrations/EMAIL.md)
- Other email routing templates: `email_routing_mock`, `email_routing_graph`,
  `email_routing_gmail`
