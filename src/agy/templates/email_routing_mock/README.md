# Email Routing Template (Mock Account)

This template demonstrates email routing using AGY flows with a
**MockEmailAccount** for local testing. Emails are stored as `.eml` files in
`mock_mailbox/`.

## What it does

The flow processes travel insurance customer emails and automatically:

- **Classifies** emails into categories: `question`, `new_claim`,
  `wrong_department`, or `unclear`
- **Answers coverage questions** using policy Terms & Conditions via LLM
- **Processes claims** by extracting claim data and validating completeness
- **Routes wrong department emails** to appropriate insurance departments
- **Escalates unclear requests** to human support (with enrichment annotation)

## Getting Started

1. **Set up environment variables**:

   ```bash
   cp .env.example .env
   # Edit .env and add your OPENAI_API_KEY
   ```

2. **Run the flow**:

   ```bash
   python main.py
   ```

   This processes all emails in `mock_mailbox/inbox/` and shows classification
   results.

3. **Add test emails**: Place `.eml` files in `mock_mailbox/inbox/` to test
   different scenarios.

## Project Structure

```text
email_routing_mock/
├── main.py                      # Entry point using MockEmailAccount
├── email_routing_flow.flowsy    # Flow definition
├── .env.example                 # Environment variables template
├── pyproject.toml               # Project configuration
├── mock_mailbox/                # Local email storage
│   └── inbox/                   # Inbox folder with .eml files
│       ├── coverage_question.eml
│       ├── complete_claim.eml
│       └── ...
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

This template uses `MockEmailAccount` from `agy.integrations.email`:

```python
from agy.integrations.email import MockEmailAccount

account = MockEmailAccount(
    base_path="mock_mailbox",
    user_email="support@acmetravelinsurance.com"
)

emails = account.get_emails(folders=["inbox"])
```

The mock account:

- Reads `.eml` files from local directories
- Supports all email operations (reply, forward, move, enrich)
- Perfect for testing without real email credentials

## Sample Emails Included

1. **coverage_question.eml** - Job loss coverage inquiry
2. **complete_claim.eml** - Full claim with all mandatory fields
3. **incomplete_claim.eml** - Claim missing required fields
4. **car_insurance_question.eml** - Auto insurance (routed to car dept)
5. **pet_insurance_question.eml** - Pet insurance (routed to pet dept)
6. **unclear_request.eml** - Vague request → human escalation

## See Also

- [Email Integration Documentation](../../../docs/integrations/EMAIL.md)
- Other email routing templates: `email_routing_imap_smtp`,
  `email_routing_graph`, `email_routing_gmail`
