# CLI & Project Structure

## CLI Commands

### Initialize a New Project

Create a new Agy project from a template. A new directory is created:

```bash
# Minimal template (default) - creates agy_project/
uv run agy init
cd agy_project

# Email routing example with mock account - creates agy_email_routing_mock/
uv run agy init --template email_routing_mock
cd agy_email_routing_mock
```

### Available Templates

**`minimal`** - Basic structure with one classification node

- Simple flow example
- Example context object
- Single instruction file

**`email_routing_mock`** - Email routing with local mock mailbox

- Uses `MockEmailAccount` from `agy.integrations.email`
- Local `.eml` files for testing (no external services needed)
- Classification with confidence-based routing

**`email_routing_imap_smtp`** - Email routing via IMAP/SMTP

- Uses `ImapSmtpEmailAccount` for any standard email provider
- Works with Gmail, Yahoo, custom IMAP servers, etc.

**`email_routing_graph`** - Email routing via Microsoft Graph API

- Uses `GraphEmailAccount` for Microsoft 365 / Office 365
- Supports `email.enrich()` for adding annotations

**`email_routing_gmail`** - Email routing via Gmail API

- Uses `GmailEmailAccount` with OAuth 2.0
- Direct Gmail API access (not IMAP)

**`software_support_jira`** - Jira ticket routing for software support

- Uses `JiraClient` from `agy.integrations.jira`
- Classifies ticket descriptions into support types and routes handling:
  - close invalid tickets
  - answer FAQ-style tickets
  - assign specialist tickets

## Project Structure After `agy init`

### Minimal Template (`uv run agy init`)

After running `agy init`, a new directory `agy_project/` is created:

```text
agy_project/                # New directory created by agy init
├── data/                    # Place your data files here
├── prompts/                 # Instruction files
│   └── example_instruction.md
├── objects/                 # Context object classes
│   ├── __init__.py
│   └── example_context.py
├── example_flow.flowsy      # Simple example flow
├── main.py                  # Entry point to run the flow
└── .env.example             # Environment variables template
```

### Email Routing Mock Template (`uv run agy init --template email_routing_mock`)

After running `agy init --template email_routing_mock`, a new directory
`agy_email_routing_mock/` is created:

```text
agy_email_routing_mock/      # New directory created by agy init
├── mock_mailbox/
│   └── inbox/               # Sample email files
│       ├── coverage_question.eml
│       ├── claim_complete.eml
│       └── ...
├── prompts/
│   └── classify_insurance_email.md
├── objects/
│   ├── __init__.py
│   └── claim_functions.py   # Claim processing functions
├── data/
│   └── claims.csv           # Sample claims data
├── email_routing_flow.flowsy
├── main.py
├── pyproject.toml
└── .env.example
```

The other email routing templates (`email_routing_imap_smtp`,
`email_routing_graph`, `email_routing_gmail`) have a similar structure but use
different email account types and don't include local `.eml` files.

### Jira Support Template (`uv run agy init --template software_support_jira`)

After running `agy init --template software_support_jira`, a new directory
`agy_software_support_jira/` is created:

```text
agy_software_support_jira/     # New directory created by agy init
├── prompts/
│   ├── classify_ticket_type.md
│   └── answer_from_faq.md
├── objects/
│   ├── __init__.py
│   └── support_helpers.py
├── data/
│   └── software_support_faq.md
├── software_support_flow.flowsy
├── main.py
├── pyproject.toml
└── .env.example
```

### Directory Purposes

**`data/`** - Store your data files here

- Supported: PDF, DOCX, XLSX, TXT, HTML, .eml
- Load in flows: `load_files_text("data/your_file.pdf")`
- Relative paths resolve automatically

**`prompts/`** - Instruction markdown files

- Contains instruction parts of prompts (not full prompts)
- Full prompts are composed by Agy with dynamic data
- Reference: `instruction_file="prompts/email_classify_instruction.md"`

**`objects/`** - Context object classes

- Define custom Python classes (e.g., `Email`, `Document`, `User`)
- Used in `context_in` in your flow YAML files
- Example: `context_in: { email: Email }`

**`.flowsy` files** - Flow definitions

- Define workflows in FLOWSY format (Flows. Simple. YAMLish)
- Name pattern: `<flowname>_flow.flowsy`
- Multiple flows per project supported

**`main.py`** - Execution entry point

- Loads and executes flows
- Handles context initialization
- Run with: `python main.py`

## File Path Resolution

Agy uses a fallback strategy to resolve file paths, making YAML flows portable
across different working directories.

### Resolution Order

1. **Absolute paths** - Used as-is
2. **Relative to current working directory** - `./data/file.pdf`
3. **Relative to project root** - Searches up for `pyproject.toml`
4. **Relative to YAML file location** - Same directory as the flow file

### Examples

```yaml
# All of these work, depending on your directory structure:
- load_files_text("data/document.pdf") # Relative to CWD or project root
- load_files_text("/absolute/path/document.pdf") # Absolute path
- load_files_text("./document.pdf") # Same directory as YAML file
```

### Best Practices

- Use **relative paths** from project root: `"data/file.pdf"`
- Place instruction files in `prompts/`: `"prompts/instruction.md"`
- Avoid absolute paths for portability
- Keep data files in `data/` directory

## Environment Setup

Create a `.env` file in your project root:

```bash
# .env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

Load in your code:

```python
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
```

## Next Steps

After initialization:

1. Copy `.env.example` to `.env` and add your API keys
2. Review and customize the flow file (`*.flowsy`)
3. Adjust prompts in the `prompts/` directory as needed
4. Add your data files to `data/`
5. Run your flow: `python main.py`

For detailed flow definition syntax, see [README.md](../README.md).

For built-in actions reference, see
[ACTIONS_REFERENCE.md](ACTIONS_REFERENCE.md).
