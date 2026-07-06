# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Stochastic `requests:` entries can now be Python expressions, including
  f-strings, evaluated with the current flow context before `agent.run(...)`.

### Changed

- Stochastic agents now implement `run(...)` as their execution method. FLOWSY
  keeps `requests:` as the list of natural-language instructions passed to the
  agent.

## [0.8.1] - 2026-06-03

### Fixed

- Switched record enums to `StrEnum` to satisfy the project-wide CI Ruff check
  on Python 3.11+.

## [0.8.0] - 2026-06-03

### Added

- **RecordSet batch screening foundation**:
  - Added neutral `Record`, `RecordSet`, `RecordSource`, `SearchQuery`,
    `RecordType` and `SourceType` models for batch-oriented search results.
  - Added `EmailRecordSource` and `search_emails(...)` as a contrib action that
    projects existing `Email` objects into searchable records.
  - Added `FileRecordSource` and `search_files(...)` as a contrib action for
    searchable local file batches with lazy full-text loading.
  - Added readable batch methods: `get_current_batch()`, `get_next_batch()`,
    `has_next_batch()` and `load_full(...)`.
- **Final fallback edge shorthand**:
  - The last edge in a node may now omit `True:` and use only the target name,
    e.g. `- default_handler`.
  - Non-final fallback shorthand edges are rejected to keep routing order
    explicit and safe.

### Changed

- **MyPy package discovery**:
  - Enabled explicit package bases and set `mypy_path = "."` to avoid local
    namespace duplication when running `mypy agy/`.
- **Flow validation context contracts**:
  - `Flow.validate(..., context_in=...)` now accepts classes as the preferred
    validation contract while preserving instance-based validation for
    backwards compatibility.
  - Class-based validation checks methods plus attributes declared via
    annotations, dataclass fields or Pydantic model fields.

### Documentation

- Documented final-edge fallback shorthand in README, FLOW and FLOWSY parsing
  references.
- Documented stochastic node syntax in FLOW, FLOWSY parsing and action
  reference docs.
- Documented class-based validation as the preferred validation pattern before
  running the same flow over many object instances.
- Added a TODO for a future `src/`-layout migration.

## [0.7.0] - 2026-06-02

### Added

- **Stochastic FLOWSY nodes**:
  - Added `type: stochastic` nodes that delegate natural-language `requests`
    to an agent object from `context_in`.
  - Added `AgentRequestResult` normalization for agent outputs, messages,
    success state, errors and raw payloads.
  - Stochastic nodes now participate in the same edge routing semantics as
    deterministic nodes.

### Changed

- **`extract()` robustness**:
  - Enhanced value extraction with type normalization and sentinel handling.

### Documentation

- Documented stochastic node syntax and agent return normalization in README.

### Tests

- Added parser, runtime, validation and error-routing coverage for stochastic
  nodes.

## [0.6.14] - 2026-04-23

### Added

- **`email.copy(folder)`** — server-side copy to a folder, keeping the original in place:
  - `MockEmailAccount`: copies the `.eml` file to the destination folder.
  - `GraphEmailAccount`: uses the native Graph API `/messages/{id}/copy` endpoint.
  - `GmailEmailAccount`: adds the destination label without removing existing labels.
  - `ImapSmtpEmailAccount`: uses the IMAP `COPY` command without deleting the source.

## [0.6.13] - 2026-04-15

### Added

- **Email label / category API** for all account types:
  - `email.add_label(text)` — adds an Outlook category (Graph), Gmail label, or mock label.
  - `email.has_label(text)` — checks whether an email carries a given label/category.
  - Supported across `GraphEmailAccount`, `GmailEmailAccount`, `MockEmailAccount`.
  - `ImapSmtpEmailAccount` raises `NotImplementedError` (IMAP has no native label concept).

## [0.6.12] - 2026-03-28

### Added

- **Draft-only mode** for email send/reply/reply_all/forward (Leo Vogel):
  - Per-call parameter `draft_only=True` or global via `EMAIL_DRAFT_ONLY=true` env var.
  - Saves message as draft instead of sending across all account types (Graph, Gmail, IMAP/SMTP, Mock).
- **`mark_unread()` / `mark_read()`** for all email account types (Leo Vogel):
  - Mark emails as read or unread (Graph, Gmail, IMAP/SMTP, Mock).
- **`move_email()` returns moved message** for Graph accounts (Leo Vogel):
  - `move_message` in Graph API now returns the moved message payload.
- **Transition screen fields** for Jira transitions (Thomas Bergmann):
  - `transition(issue_key, transition, *, fields=None, update=None)` now supports
    passing field values and update payloads for Jira transition screens
    (e.g. required `resolution` when closing an issue).

### Documentation

- Documented `fields` and `update` parameters for `JiraClient.transition()` with examples.

### Changed

- Ruff formatting fixes across the codebase (Leo Vogel).
- Updated mypy configuration to exclude non-package scripts (Thomas Bergmann).

## [0.6.11] - 2026-03-28

### Added

- **Sub-flow calls** (`run_flow`):
  - Call another `.flowsy` flow or re-enter the current flow at a specific node.
  - Sub-flow runs with its own isolated context; result returned to caller.
- **Batch processing** (`run_flow_batch`):
  - Run a sub-flow once per element in a list (sequential or parallel).
  - Supports `mode="sequential"` / `"parallel"` and `on_error="continue"` / `"fail_fast"`.
  - Each iteration gets its own fresh, isolated context.
- **Runtime flow context** (`contextvars`):
  - `FlowExecutor` exposes the current flow and action_types via `contextvars` so sub-flow actions can access them at runtime.

### Tests

- Added 10 tests for `run_flow` and `run_flow_batch`:
  - External `.flowsy` sub-flow call, same-flow node call, error on missing args.
  - Sequential and parallel batch, fail-fast, continue-on-error, empty list.
  - Context isolation between sub-flow iterations and parent flow.

### Documentation

- Added sub-flow and batch processing sections to README, FLOW.md, ACTIONS_REFERENCE.md, and cursor rules.

## [0.6.10] - 2026-03-26

### Added

- **JiraIssue description append API**:
  - Added `JiraIssue.append_to_description(text, position="BOTTOM")`.
  - Supports `TOP` and `BOTTOM` placement with Jira description updates.
- **JiraIssue sub-task API**:
  - Added `JiraIssue.add_subtask(headline, description="", issue_type="Sub-task")`.
  - Creates child issues using Jira-native `parent={"key": ...}` linkage.
  - Normalizes alias input like `"subtask"` to Jira issue type `"Sub-task"`.

### Tests

- Added Jira integration tests for:
  - description append behavior (`TOP` and default `BOTTOM`),
  - sub-task payload and parent linkage,
  - issue-type alias normalization,
  - unbound `JiraIssue` error handling for new methods.

### Documentation

- Updated Jira integration docs with examples and behavior for:
  - `append_to_description(...)`
  - `add_subtask(...)`

## [0.6.9] - 2026-03-24

### Added

- **Issue-level Jira comment API**:
  - `JiraIssue.add_comment(text)` delegates to Jira and returns `JiraComment`.
  - `JiraIssue.get_comments()` returns `list[JiraComment]` sorted reverse-chronologically (newest first).
  - `JiraComment` now includes `created` and optional `author`.
- **Issue-client binding**:
  - Issues returned by `JiraClient` are now bound to their source client to enable issue-level comment operations.

### Changed

- **Jira comments typing**:
  - `JiraClient.get_comments(issue_key)` now returns typed `list[JiraComment]` instead of raw dictionaries.
  - Comment parsing now maps raw payloads to business objects consistently.

### Fixed

- **Flow end-target parsing/validation/runtime**:
  - Node names starting with `end` (e.g. `end_review`) are no longer treated as `end()` termination.
  - Only `end` and `end(...)` are recognized as termination targets.

### Documentation

- Updated Jira integration docs with issue-level comment usage, sorting semantics, and `JiraComment` fields.

### Tests

- Added/updated Jira integration tests for issue-level comment delegation and newest-first sorting.
- Added regression tests ensuring `end_*` node names are resolved as regular nodes in parser/validation paths.

## [0.6.8] - 2026-03-24

### Added

- **Jira issue field mapping API**:
  - `_issue_from_dict(...)` now supports optional `field_mapping` and `issue_cls`.
  - Added `JiraIssue.from_dict(...)` classmethod for direct model/subclass construction from `{key, fields}` payloads.

### Changed

- **Jira custom fields handling**:
  - Non-core Jira fields are now preserved in `JiraIssue.extra_fields` (skipping `None` values).
  - Mapped canonical field names are routed to subclass attributes when matching dataclass fields; otherwise stored in `extra_fields`.
  - Core attributes (`key`, `summary`, `status`, `issuetype`, `assignee`, `reporter`, `description`, `labels`, `extra_fields`) are protected from accidental overwrite by mappings.

### Tests

- Added Jira integration tests for:
  - `extra_fields` population without mapping,
  - canonical-key mapping behavior,
  - subclass attribute routing,
  - `JiraIssue.from_dict(...)` subclass instantiation.

## [0.6.7] - 2026-03-19

### Changed

- **Jira backend migration**: Switched `JiraClient` from `jira` to `atlassian-python-api`.
  - Installation profile changed from `--extra jira` to `--extra atlassian`.
  - Jira docs and examples updated accordingly.
- **Jira transitions**: `JiraClient.transition(issue_key, transition)` now accepts either transition IDs or transition names.
  - Names are resolved against available transitions for the issue.
  - Validation error now includes available transition names when no match is found.
- **JiraIssue model**: Added `labels` as a first-class field (`list[str]`) and mapped it from Jira `fields.labels`.

### Fixed

- **ActionExecutor error propagation**: Preserves the original action exception message when merging `end()` context after a failed action.
  - Prevents masking root-cause errors with generic handler messages.
  - Improves API/debug visibility for failure paths.

### Tests

- Updated Jira integration test coverage for the migrated backend and transition name support.
- Verified `ActionExecutor` unit tests for failure-path behavior (`error_msg` handling) remain green.

## [0.6.6] - 2026-03-17

### Added

- **Flow runtime facade**: Added async `Flow.run(...)` as the primary execution entrypoint.
  - Accepts `context_in` and `action_types` directly.
  - Supports optional `node` parameter to start execution at a specific node.

### Changed

- **Flow executor start behavior**: `FlowExecutor.execute(...)` now accepts optional `node` and starts at `flow.nodes[0]` when not provided.
- **Documentation execution examples**: Updated docs and user rules to use `flow.run(...)` instead of `FlowExecutor(...).execute(flow)`.
  - Added a single focused docs example for node-based entry (`node="..."`).

### Tests

- Added/updated unit tests for:
  - `Flow.run(...)` async facade behavior.
  - Optional start-node execution path.
  - Error handling for invalid optional start node.

## [0.6.5] - 2026-03-14

### Fixed

- **Jira Atlassian Cloud auth**: `JiraClient` now supports Basic auth for Atlassian Cloud when `JIRA_USER` (email) is set. Uses `basic_auth=(user, token)` instead of `token_auth`, fixing HTTP 403 "Failed to parse Connect Session Auth Token". Set `JIRA_USER` to your Atlassian account email in addition to `JIRA_URL` and `JIRA_TOKEN` for Cloud instances.

## [0.6.4] - 2026-03-03

### Added

- **New Jira project template**: `software_support_jira`
  - Includes complete runnable structure (`main.py`, `.flowsy`, prompts, data, objects, `pyproject.toml`, `.env.example`, `README.md`)
  - Implements software support ticket routing:
    - classify ticket description (`x`/`y`/`z`)
    - close invalid/misdirected tickets (`x`)
    - answer FAQ-based tickets via Jira comments (`y`)
    - assign specialist tickets to handler A (`z` / fallback)

### Changed

- **CLI template help** now includes `software_support_jira`.
- **Docs updated** to include the Jira support template in onboarding and project structure references.
- **Jira integration docs** now provide a mini flow example plus template-based quick start.

### Removed

- **Legacy Jira example files** under `examples/` were removed in favor of the new template successor:
  - `jira_fetch_flow.flowsy`
  - `jira_summary_flow.flowsy`
  - `run_jira_fetch.py`
  - `run_jira_summary.py`

## [0.6.3] - 2026-03-03

### Changed

- **Graph folder resolution hardening**: improved Microsoft Graph folder lookup for localized and nested folder names.
  - Uses Graph well-known folder endpoints for common folders (`inbox`, `sentitems`, `deleteditems`, `drafts`, `junkemail`, `outbox`).
  - Keeps fallback display-name traversal and now retrieves paginated folder listings via `@odata.nextLink`.
  - Improves reliability for aliases like `trash`, `posteingang`, and other locale-specific names.

### Added

- **Graph attachment lazy loading**: added account-level attachment fetch support for Graph emails.
  - New `EmailAccount.fetch_attachments(email)` extension point (default no-op).
  - `GraphEmailAccount.fetch_attachments(email)` now loads and populates attachment contents on demand.

### Documentation

- Updated onboarding and flow docs to clarify edge behavior and syntax:
  - Explicit `True: target` fallback examples.
  - Clarified runtime behavior for nodes without edges vs. unmatched edge conditions.

## [0.6.2] - 2026-01-27

### Fixed

- **IMAP/SMTP Gmail search compatibility**: Fixed IMAP UID search calls to use server-compatible charset handling.
  - Replaced `imap.uid("search", "UTF-8", ...)` with `imap.uid("search", None, ...)`
  - Resolves Gmail IMAP errors like `BAD [b'Could not parse command']` during `find_emails()` and `get_emails()`
  - Unblocks full IMAP/SMTP integration workflow tests for self-send and search

## [0.6.1] - 2026-01-27

### Added

- **Graph API Nested Folder Support**: `GraphEmailAccount` now supports nested folder paths
  - Use `/` as separator: `folders=["logistics/inbox"]`, `email.move("Archive/2024/January")`
  - Works with `get_emails()`, `find_emails()`, `move_email()`, `create_draft()`
  - Folder aliases (`sent`, `trash`, etc.) work at any nesting level

### Fixed

- **Template .env.example files**: Fixed wheel build to include `.env.example` files in templates
  - Templates created via `agy init --template` now include `.env.example`

## [0.6.0] - 2026-01-27

### Added

- **IMAP/SMTP Email Account** (`ImapSmtpEmailAccount`): Generic email provider support via standard IMAP/SMTP protocols
  - Works with any IMAP/SMTP-compatible provider (Gmail, Yahoo, custom servers, etc.)
  - Full implementation: `get_emails`, `find_emails`, `send_email`, `reply_email`, `forward_email`, `move_email`, `delete_email`, `create_draft`
  - Environment-based configuration: `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`

- **Email Routing Templates Refactoring**: Split into 4 provider-specific templates
  - `email_routing_mock`: Local testing with `MockEmailAccount` and `.eml` files in `mock_mailbox/`
  - `email_routing_imap_smtp`: Generic IMAP/SMTP provider support
  - `email_routing_graph`: Microsoft 365 / Office 365 via Graph API
  - `email_routing_gmail`: Gmail via OAuth 2.0 API
  - Each template has provider-specific `.env.example` with documented placeholders
  - Templates without `enrich` support (`imap_smtp`, `gmail`) have `email.enrich()` calls removed from flow

- **Integration Tests for IMAP/SMTP**: Real Gmail account integration tests (`test/integration/test_email_imap_smtp.py`)

### Changed

- **`enrich_email()` for GmailEmailAccount**: Now raises `NotImplementedError` (Gmail bodies are immutable, previous internal note approach was not user-trackable)
- **`enrich_email_hidden()` for all accounts**: Now raises `NotImplementedError` across all implementations (`GmailEmailAccount`, `GraphEmailAccount`, `MockEmailAccount`, `ImapSmtpEmailAccount`)
- **CLI help text**: `agy init --template` now lists all available templates
- **Template E2E tests**: Updated to test `email_routing_mock` template with `MockEmailAccount`

### Removed

- **Old `email_routing` template**: Replaced by the four provider-specific templates

### Documentation

- Updated `README.md`, `CLI_PROJECT_STRUCTURE.md`, `EMAIL.md`, `TESTING.md` to reference new templates

## [0.5.5] - 2025-01-27

### Changed

- **Google Gemini SDK Migration**: Migrated from deprecated `google-generativeai` to new `google-genai` SDK
  - Updated `gemini_llm_call()` to use new Client-based API
  - Default model changed from `gemini-pro` to `gemini-2.0-flash`
  - Removes FutureWarning about deprecated package

### Added

- **LLM Provider Integration Tests** (`test/contrib/test_llm_providers.py`): Tests for all LLM providers
  - Individual tests for OpenAI, Azure OpenAI, Gemini, Anthropic, and Fake providers
  - Summary test that reports status of all available providers
  - New pytest marker `model_integration` for tests that call real LLM APIs

### Dependencies

- Replaced `google-generativeai>=0.3.0` with `google-genai>=1.0.0`

## [0.5.4] - 2025-01-27

### Added

- **Email Integration Module** (`agy.integrations.email`): Complete email provider abstraction
  - `Email` dataclass: Provider-agnostic value object (sender, recipient, subject, text/body, message_id, etc.)
  - `EmailAccount` interface: Unified API for `reply`, `forward`, `move`, `enrich`, `enrich_hidden`
  - **Microsoft Graph** (`GraphEmailAccount`): Full implementation via Graph API
    - Reply/forward/move/enrich with HTML template support
  - **Gmail** (`GmailEmailAccount`): OAuth-based implementation via Gmail REST API
    - Reply/forward/move (labels), internal notes for enrichment (Gmail bodies are immutable)
  - **IMAP** (`IMAPEmailAccount`): Stub for future implementation
  - **Mock** (`MockEmailAccount`): In-memory recorder for testing
  - `EmailSafetyValidator`: Environment-driven allowlists (`ALLOWED_EMAIL_DOMAINS`, `ALLOWED_EMAIL_ADDRESSES`)
  - Provider selection helpers: `get_email_provider()`, `create_email_account()`, `create_email_fetcher()`
  - Fetchers: `GraphEmailFetcher`, `GmailFetcher` for inbox retrieval
  - Converters: Utilities to transform provider-specific dicts to `Email` dataclass

### Dependencies

- Added `google-auth-oauthlib>=1.2.4` for Gmail OAuth support

## [0.5.3] - 2025-01-06

### Added

- **`model_call()` JSON output**: New `output="json"` parameter for automatic JSON parsing
  - Returns parsed `dict` or `list` instead of raw string
  - Automatically strips markdown code blocks before parsing
  - Raises `json.JSONDecodeError` on invalid JSON

- **`FILE_SEARCH_ORDER`**: Files are now searched in standard directories
  - Search order: `.` → `prompts/` → `data/` → `objects/`
  - Applies to `instruction_file`, `load_files_text()`, `get_prompt_from_file()`

- **Validation**: Added `context` to implicit variables (validation now passes for `context.get()`)

### Fixed

- **Documentation**: Clarified that users access variables directly (`confidence`, not `context["confidence"]`)
- **Dead code**: Removed unused `STANDARD_DIRECTORIES` and `END_NODE_NAME` constants

## [0.5.2] - 2025-01-06

### Fixed

- **Template `pyproject.toml`**: Added `agy` to `dependencies` list - was missing, causing `ModuleNotFoundError`

## [0.5.1] - 2025-01-06

### Fixed

- **Build configuration**: Fixed `[tool.hatchling.build...]` → `[tool.hatch.build...]` in `pyproject.toml`
- **Missing `flowsy` package**: Added `flowsy` to build packages list - was causing `ModuleNotFoundError`
- **`agy init` workflow**: Templates now include complete `pyproject.toml` with `[project]` table
  - Projects created with `agy init` are now standalone and runnable without parent `uv init`
  - Removed inline `_ensure_llm_config()` from CLI - config now part of template files

### Changed

- **README**: Updated Quick Start to recommend `uv tool install` for global installation
- **Integration tests**: Added assertions for `pyproject.toml` completeness in template tests

## [0.5.0] - 2025-01-05

### Added

#### Flow Validation with SourceSpan
- **`Flow.validate()`** now provides precise error locations with line numbers and source content
- **Validation checks:**
  - Syntax is correct and all mandatory fields present (name, nodes)
  - Flow has nodes (not empty)
  - Edge targets exist
  - Variables are defined (in context_in or previous actions)
  - Functions are registered (contrib or custom action_types)
  - Function signatures match (required arguments provided)
  - Object attributes/methods exist (when context_in provided)
  - File paths exist (instruction_file, load_files_text)
  - LLM API keys set (only for used provider)
- **Refactored** validation logic into modular functions in `validation.py`

### Breaking Changes

#### FLOWSY Flow Definition Format
- **Replaced `.agy.yaml` with `.flowsy` format:**
  - New schema-driven FLOWSY parser (`flowsy/flowsy_parser.py`) based on grammar file (`flowsy_grammar.v0.1.yaml`)
  - Line-by-line, indentation-based parsing with quote-aware colon splitting
  - Grammar-driven parsing: No hardcoded key names, structure defined in grammar file
  
**What changed:**
- `Flow.from_yaml()` → `Flow.from_flowsy()` (method renamed)
- `Flow.from_yaml_string()` → `Flow.from_flowsy_string()` (method renamed)
- All flow files migrated from `.agy.yaml` to `.flowsy` extension
- `yaml_parser.py` completely removed (replaced by `flowsy_parser.py`)
- `test_yaml_parser.py` → `test_flow_parser.py` (renamed and adapted)

**FLOWSY Format Details:**
- Strict indentation-based structure (0, 2, 4, 6 spaces)
- Quote-aware colon splitting (ignores colons inside single/double quotes)
- Schema-driven: Parser interprets structure from grammar file, not hardcoded logic
- Dictionary-style node definitions: `node_name:` (not list-style `- node_name:`)

**Migration:**
- All template flows already migrated to `.flowsy` format
- Existing `.agy.yaml` files need to be renamed to `.flowsy`
- Flow structure remains the same, only file extension changes
- Grammar file path configured in `agy/config.py`

#### Action Execution Format Standardization
- **Unified format-based system for action results:**
  - New format: `{"result": ..., "context": {...}, "flow_control": "TERMINATE"}`
  - Removed old format: `{"result": ..., "confidence": ...}` (no longer supported)
  
**What changed:**
- **LLM Functions (`classify`, `extract`, `respond`):**
  - Old: `return {"result": value, "confidence": 0.9}`
  - New: `return {"result": value, "context": {"confidence": 0.9}}`
  
- **`end()` function:**
  - Old: `end(context, **kwargs)` - took context as parameter, raised `FlowTerminationError`
  - New: `end(**kwargs)` - returns `{"result": None, "context": {...}, "flow_control": "TERMINATE"}`
  - No more `context` parameter needed
  - Flow termination handled by `ActionExecutor` based on `flow_control` flag

- **`ActionExecutor`:**
  - Recognizes new format: `{"result": ..., "context": {...}}`
  - Automatically writes `result` to assigned variable and `context["result"]`
  - Updates flow context with all keys from `result["context"]`
  - Raises `FlowTerminationError` when `flow_control == "TERMINATE"`
  - Sets `context["success"] = True` before context updates (allows `end()` to override)

**Benefits:**
- Consistent return format across all actions
- Flexible context updates (not limited to `confidence`)
- Cleaner flow termination (no exception-based control flow)
- Better separation of concerns (actions return data, executor handles flow control)

**Migration:**
- Update `end(context, ...)` calls to `end(...)` in all `.flowsy` files
- Update test assertions to check return values instead of exceptions
- LLM function return format automatically handled by `ActionExecutor`

#### Complete Parsing Architecture Refactoring
- **Replaced YAML-based parsing with hybrid approach:**
  - **Level 0, 1, 2 (Structure):** Simple YAML-style line-by-line parsing with strict indentation (0, 2, 4, 6 spaces)
  - **Level 3 (Actions/Edges):** AST-based parsing for full Python expression support
  
**What changed:**
- Removed legacy parsing functions: `parse_action_string()`, `parse_arguments()`, `parse_single_argument()`, `parse_value()`
- All actions are now parsed as `__eval__` expressions using Python's AST parser
- Edges use AST parsing for conditions, allowing full Python expressions
- `end()` function in edges now uses `__eval__` instead of manual argument parsing

**Benefits:**
- Full Python expression support in actions (f-strings, dict access, method calls, etc.)
- No more escaping colons in dictionary literals
- Consistent parsing architecture across all actions and edges
- Better error messages with AST validation

**Migration:**
- Existing flows continue to work (same YAML syntax)
- No changes required to `.agy.yaml` files
- Internal parsing is now more robust and supports complex expressions

### Changed

- **`flow.py`:** 
  - `from_yaml()` → `from_flowsy()` (uses `flowsy_parser.py` instead of `yaml_parser.py`)
  - Removed `yaml` import, uses FLOWSY parser exclusively
- **`action_executor.py`:** 
  - Simplified to only handle `__eval__` actions
  - Added format-based result handling for `{"result": ..., "context": {...}}` format
  - Flow termination via `flow_control: "TERMINATE"` flag instead of exception catching
- **`node_executor.py`:** `_parse_end_action_from_edge()` now uses `__eval__` instead of manual parsing
- **`config.py`:** Added `FLOWSY_GRAMMAR_PATH` configuration for grammar file location

### Removed

- **`yaml_parser.py`:** Completely removed (replaced by `flowsy_parser.py`)
- **`test_yaml_parser.py`:** Removed (replaced by `test_flow_parser.py`)
- **Legacy parsing functions:** `parse_action_string()`, `parse_arguments()`, `parse_single_argument()`, `parse_value()`
- **`_resolve_context_value()` method:** No longer needed with AST-based evaluation
- **Old action return format:** `{"result": ..., "confidence": ...}` (replaced by format with `context` key)
- **Unused imports:** `re`, `SimpleEval`, `ast` from `action_executor.py` (where not needed)

### Added

- **`flowsy/flowsy_parser.py`:** Schema-driven FLOWSY parser with grammar-based structure interpretation
- **`flowsy/flowsy_grammar.v0.1.yaml`:** Grammar definition file for FLOWSY format
- **Format-based action results:** Support for `{"result": ..., "context": {...}, "flow_control": "TERMINATE"}` format
- **`flow_control` flag:** Standardized way to signal flow termination from actions

## [0.4.0] - 2025-12-31

### Breaking Changes

#### LLM Architecture Refactoring
- **Refactored LLM provider management to Singleton architecture:**
  - Removed `agy/contrib/model_calls.py` (moved to `agy/contrib/llm_call.py`)
  - Removed `agy/contrib/model_call_factory.py` (logic integrated into `LLMCall` Singleton)
  - `model_call()` signature changed: `model` parameter removed, now uses `**kwargs` for additional parameters

**Migration:**
```yaml
# Old
- result = model_call(prompt="...", model="gpt-4")

# New
- result = model_call(prompt="...", temperature=0.7, max_tokens=1000)
```

#### LLM Action Function Names
- **Renamed built-in LLM action functions to verb forms for consistency:**
  - `classifier()` → `classify()`
  - `generator()` → `respond()`
  - `extractor()` → `extract()`

**Migration:**
```yaml
# Old
- classifier(input_text=email.text, categories=["sales", "support"])

# New
- category = classify(input_text=email.text, categories=["sales", "support"])
```

#### LLM Action Return Structure
- **Unified return structure for all LLM actions (`classify`, `respond`, `extract`):**
  - All actions now return `{"result": <value>, "confidence": <float>}`
  - Main result is written to assigned variable (or `context["result"]` if no assignment)
  - `confidence` is always written to `context["confidence"]` for easy access in edges
  
**What changed:**
- `classify()`: Returns category string as `result` (was: `category` key in dict)
- `extract()`: Returns extracted values dict as `result` (was: flat dict with all values)
- `respond()`: Returns generated text as `result` (unchanged)

**Old behavior:**
```yaml
# classify() wrote category directly to context
- classifier(input_text=text, categories=["a", "b"])
  edges:
    - category == "a": handle_a  # category was in context
```

**New behavior:**
```yaml
# Explicit assignment recommended for clarity
- category = classify(input_text=text, categories=["a", "b"])
  edges:
    - confidence < 0.8: manual_review  # confidence always available
    - category == "a": handle_a
```

**Benefits:**
- Consistent behavior across all LLM actions
- No namespace pollution with `extract()` results
- Direct access to `confidence` in edges
- Clearer code with explicit assignments

### Added

- **Multi-provider LLM support:** OpenAI, Azure OpenAI, Google Gemini, Anthropic Claude, Fake (for testing)
- **`set_model_call()` action:** Configure provider/model/parameters for all subsequent LLM actions
- **Config-based defaults:** `pyproject.toml` `[tool.agy.llm]` section for default provider/model/params
- **`register_provider()` method:** Register custom providers (e.g., Mistral) in code
- **LLMCall Singleton:** Central management for all LLM provider calls

### Changed

- **ActionExecutor:** Updated context writing logic to use unified approach for LLM actions
- **ActionExecutor:** Removed special handling for `set_model_call` (now normal action)
- **Template structure** (affects `agy init` command):
  - `instructions/` → `prompts/`
  - `models/` → `objects/`
  - Existing projects can continue using old structure
- **LLM Actions:** Now automatically use `LLMCall().model_call()` when `model_call` parameter is not provided

### Fixed

- Fixed edge parsing to support `condition: target_node` syntax
- Fixed YAML parsing with colons in dictionary literals

## [0.3.1] - 2024-12-29

### Added
- Email routing template
- Language server support for VSCode
- Core flow execution engine
- Built-in LLM actions (classifier, generator, extractor)
- File loading utilities
- Custom action support

---

## Migration Notes

For detailed migration instructions when upgrading to 0.4.0, see the migration guide that will be provided with the release.

**Quick migration checklist:**
- [ ] Rename all `classifier()` calls to `classify()`
- [ ] Rename all `generator()` calls to `respond()`
- [ ] Rename all `extractor()` calls to `extract()`
- [ ] Add explicit variable assignments for clarity (recommended)
- [ ] Update edge conditions to use assigned variables
- [ ] Update `model_call()` calls: remove `model` parameter, use `**kwargs` for additional params
- [ ] (Optional) Configure default provider/model in `pyproject.toml` `[tool.agy.llm]`
- [ ] Test flows to ensure confidence-based routing works as expected

