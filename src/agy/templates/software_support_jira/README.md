# Software Support Jira Template

This template demonstrates Jira ticket routing with AGY flows for a software
support use case.

## What it does

For one ticket (`JIRA_ISSUE_KEY`), the flow:

- Fetches the issue from Jira
- Classifies the issue description into support types:
  - `invalid_request`
  - `faq_resolvable`
  - `needs_specialist`
- Handles routing:
  - `invalid_request`: close as invalid/misdirected ticket
  - `faq_resolvable`: answer directly from FAQ and add response as Jira comment
  - `needs_specialist` (or low confidence): assign to specialist `A`

## Getting started

1. Copy env file and fill required values:

   ```bash
   cp .env.example .env
   ```

2. Run:

   ```bash
   python main.py
   ```

## Project structure

```text
software_support_jira/
├── main.py
├── software_support_flow.flowsy
├── .env.example
├── pyproject.toml
├── prompts/
│   ├── classify_ticket_type.md
│   └── answer_from_faq.md
├── data/
│   └── software_support_faq.md
└── objects/
    ├── __init__.py
    └── support_helpers.py
```

## Important env variables

- `OPENAI_API_KEY`
- `JIRA_URL`
- `JIRA_TOKEN`
- `JIRA_ISSUE_KEY`
- `JIRA_CLOSE_TRANSITION` (default: `Done`)
- `JIRA_ASSIGNEE_A`

## Notes

- `JiraClient.from_env()` requires `JIRA_URL` and `JIRA_TOKEN`.
- Closing depends on your Jira workflow transition names.
- FAQ responses are written as ticket comments.
