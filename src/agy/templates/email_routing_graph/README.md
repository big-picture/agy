# Email Routing Template (Microsoft Graph)

This template demonstrates email routing using AGY flows with
**GraphEmailAccount** for Microsoft 365 / Office 365 mailboxes.

## What it does

The flow processes travel insurance customer emails and automatically:

- **Classifies** emails into categories: `question`, `new_claim`,
  `wrong_department`, or `unclear`
- **Answers coverage questions** using policy Terms & Conditions via LLM
- **Processes claims** by extracting claim data and validating completeness
- **Routes wrong department emails** to appropriate insurance departments
- **Escalates unclear requests** to human support (with enrichment annotation)

## Getting Started

1. **Set up Azure App Registration**:
   - Go to <https://portal.azure.com> > Azure Active Directory > App
     registrations
   - Create a new registration
   - Add API permissions: `Mail.ReadWrite`, `Mail.Send`
   - Create a client secret

2. **Set up environment variables**:

   ```bash
   cp .env.example .env
   # Edit .env and add your credentials:
   # - OPENAI_API_KEY
   # - TENANT_ID, CLIENT_ID, CLIENT_SECRET
   # - USER_EMAIL
   # - ALLOWED_EMAIL_DOMAINS
   ```

3. **Run the flow**:

   ```bash
   python main.py
   ```

   This fetches unread emails and processes them through the flow.

## Project Structure

```text
email_routing_graph/
├── main.py                      # Entry point using GraphEmailAccount
├── email_routing_flow.flowsy    # Flow definition (with email.enrich)
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

This template uses `GraphEmailAccount` from `agy.integrations.email`:

```python
from agy.integrations.email import GraphEmailAccount

# Credentials from environment variables
account = GraphEmailAccount()

# Or with explicit user email
account = GraphEmailAccount(user_email="support@company.com")

emails = account.get_emails(only_unread=True)
```

## Features

- Full support for `email.enrich()` (modifies email body with annotations)
- Access to shared mailboxes
- Native folder support (not labels like Gmail)

## Required Azure Permissions

Your App Registration needs these Microsoft Graph API permissions:

- `Mail.Read` - Read emails
- `Mail.ReadWrite` - Move/modify emails
- `Mail.Send` - Send emails

Grant admin consent for these permissions in the Azure Portal.

## See Also

- [Email Integration Documentation](../../../docs/integrations/EMAIL.md)
- Other email routing templates: `email_routing_mock`,
  `email_routing_imap_smtp`, `email_routing_gmail`
