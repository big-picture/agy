# Email Example Scripts

Working examples demonstrating AGY email integration.

## Scripts

### 1. `basic_operations.py`
Demonstrates core email operations without LLM:
- Fetch and search emails
- Reply, forward, move, delete
- Create and send new emails

```bash
python basic_operations.py
```

### 2. `main.py`
Full email routing flow with LLM classification:
- Classifies incoming emails (question/complaint/other)
- Routes to appropriate handlers
- Answers questions using FAQ data
- Acknowledges complaints

Requires `OPENAI_API_KEY`:
```bash
export OPENAI_API_KEY='your-key'
python main.py
```

## Structure

```
email_example/
├── main.py                    # Flow-based processing
├── basic_operations.py        # Basic email operations
├── flows/
│   └── email_routing.flowsy   # Email classification flow
├── prompts/
│   └── answer_question.md     # LLM prompt for FAQ answers
└── data/
    └── faq.md                 # Sample FAQ data
```

## Using with Real Email Accounts

Replace `MockEmailAccount` with:
- `GraphEmailAccount` for Microsoft 365 / Outlook
- `GmailEmailAccount` for Gmail

See [docs/integrations/EMAIL.md](../../docs/integrations/EMAIL.md) for setup instructions.
