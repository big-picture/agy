# Environment Variables

Central reference for environment variables used by AGY runtime integrations.

## Loading Behavior (`.env`)

- AGY does not globally call `load_dotenv()` for all runtime paths.
- Some entrypoints/examples do load `.env` explicitly.
- Recommendation for app code: call `load_dotenv()` once at startup before
  creating clients/executors.

## LLM Providers

Used by `agy.contrib.llm_call` (`classify`, `respond`, `extract`, `model_call`
paths):

- `OPENAI_API_KEY`
- `AZURE_OPENAI_API_KEY` (legacy fallback: `OPENAI_API_AZURE_KEY`)
- `AZURE_OPENAI_ENDPOINT` (legacy fallback: `OPENAI_AZURE_BASE_URL`)
- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`

If a provider key/endpoint is missing, AGY raises a runtime error when that
provider is used.

## Jira Integration

Used by `JiraClient.from_env()`:

- `JIRA_URL` (for example: `https://company.atlassian.net`)
- `JIRA_TOKEN` (API token)

Both are required when using `from_env()`.

## Email Integration

### Microsoft Graph (`GraphEmailAccount` / `GraphAPI`)

Preferred (provider-prefixed):

- `GRAPH_TENANT_ID` (required)
- `GRAPH_CLIENT_ID` (required)
- `GRAPH_CLIENT_SECRET` (required)
- `GRAPH_USER_EMAIL` (optional, mailbox resolution)
- `GRAPH_SHARED_MAILBOX_UPN` (optional, mailbox resolution)
- `GRAPH_ALLOWED_EMAIL_DOMAINS`, `GRAPH_ALLOWED_EMAIL_ADDRESSES` (safety)
- `GRAPH_EMAIL_DRAFT_ONLY` (optional)

Deprecated fallbacks (still read with `DeprecationWarning`):

- `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`, `USER_EMAIL`, `SHARED_MAILBOX_UPN`

### Gmail (`GmailEmailAccount` / `GmailAPI`)

- `GMAIL_AUTH_MODE` (default: `oauth`)
- `GMAIL_CLIENT_ID` (required)
- `GMAIL_CLIENT_SECRET` (required)
- `GMAIL_TOKEN_FILE` (default: `token.json`)
- `GMAIL_USER` (default: `me`)
- `GMAIL_SCOPES` (optional, space-separated)
- `GMAIL_ALLOWED_EMAIL_DOMAINS`, `GMAIL_ALLOWED_EMAIL_ADDRESSES` (safety)
- `GMAIL_EMAIL_DRAFT_ONLY` (optional)

### IMAP/SMTP (`ImapSmtpEmailAccount`)

- `IMAP_HOST` (required)
- `IMAP_PORT` (default: `993`)
- `IMAP_USER` (required)
- `IMAP_PASSWORD` (required)
- `SMTP_HOST` (required)
- `SMTP_PORT` (default: `465`)
- `SMTP_USER` (default: `IMAP_USER`)
- `SMTP_PASSWORD` (default: `IMAP_PASSWORD`)
- `IMAP_ALLOWED_EMAIL_DOMAINS`, `IMAP_ALLOWED_EMAIL_ADDRESSES` (safety)
- `IMAP_EMAIL_DRAFT_ONLY` (optional)

## Email Safety

Per-provider allowlists via `{GRAPH|GMAIL|IMAP}_ALLOWED_EMAIL_DOMAINS` and
`{GRAPH|GMAIL|IMAP}_ALLOWED_EMAIL_ADDRESSES`. Deprecated global fallbacks:
`ALLOWED_EMAIL_DOMAINS` (default: `big-picture.com`), `ALLOWED_EMAIL_ADDRESSES`.

Draft-only mode: `{PROVIDER}_EMAIL_DRAFT_ONLY` or deprecated global `EMAIL_DRAFT_ONLY`.

These guard send/reply/forward operations (skipped when draft-only saves locally).

## Project Root Override

Used by AGY config path resolution:

- `AGY_PROJECT_ROOT` (optional fallback override)
