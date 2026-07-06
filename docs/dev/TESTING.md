# Testing Strategy

## Overview

AGY uses a multi-layered testing approach combining unit tests, integration tests, and end-to-end tests. This document describes the testing philosophy, structure, and best practices.

## Test Categories

### Unit Tests (`test/unit/`)

**Purpose:** Test individual functions, classes, and components in isolation.

**Location:** `test/unit/`

**Characteristics:**
- Fast execution (< 1 second per test)
- No external dependencies (no file system, no network, no LLM calls)
- Use mocks for all external services
- Test edge cases, error handling, and data transformations

**Example:**
```python
def test_parse_action_with_ast():
    """Test parsing action with variable assignment using AST parser."""
    from agy.ast_parser import parse_action_with_ast
    action_call = parse_action_with_ast('category = classify(input_text=text)')
    assert action_call.output == "category"
    assert action_call.method_name == "__eval__"
```

### Integration Tests (`test/integration/`)

**Purpose:** Test complete workflows and user journeys from installation to execution.

**Location:** `test/integration/`

**Characteristics:**
- Slow execution (10-30 seconds per test)
- Use real file system operations
- Test subprocess execution (CLI commands)
- Simulate real user scenarios

**Test Types:**

#### Email Integration Tests

Test email account implementations with real or mocked services:

```python
# test/integration/test_email_graph.py - Microsoft Graph API
@pytest.mark.email_integration
def test_graph_get_emails(graph_account):
    """Test fetching emails from Graph API."""
    emails = graph_account.get_emails(max_results=5)
    assert isinstance(emails, list)

# test/integration/test_email_imap_smtp.py - IMAP/SMTP
@pytest.mark.email_integration  
def test_imap_smtp_workflow(imap_smtp_account):
    """Test IMAP/SMTP email workflow."""
    emails = imap_smtp_account.get_emails(folder="INBOX")
    assert isinstance(emails, list)
```

**Environment Setup:**
- Graph API: `.env.graph_test` with `TENANT_ID`, `CLIENT_ID`, etc.
- IMAP/SMTP: `.env.imap_test` with `IMAP_HOST`, `SMTP_HOST`, etc.

#### Template Tests

Test that templates can be initialized and executed:

```python
@pytest.mark.slow
@pytest.mark.integration
def test_agy_init_email_routing_mock_template(uv_project):
    """Test agy init --template email_routing_mock creates correct structure."""
    subprocess.run(["uv", "run", "agy", "init", "--template", "email_routing_mock"], check=True)
    assert (uv_project / "agy_email_routing_mock" / "email_routing_flow.flowsy").exists()
```

## CI/CD Integration

### Automated Testing via GitHub Actions

CI runs automatically on every push to `develop`/`main` and on PRs:

```yaml
# .github/workflows/ci.yml
jobs:
  lint:
    steps:
      - run: pip install -e ".[dev]"
      - run: ruff check src/ test/
      - run: mypy src/agy src/flowsy

  test:
    steps:
      - run: pip install -e ".[dev]"
      - run: pytest test/

  build:
    needs: [lint, test]
    steps:
      - run: python -m build
```

### Running CI Checks Locally

Before pushing, run the same checks locally:

```bash
# Linting (same as CI)
uv run ruff check src/ test/
uv run mypy src/agy src/flowsy

# Tests (same as CI)
uv run pytest test/

# Or all at once
uv run ruff check src/ test/ && uv run mypy src/agy src/flowsy && uv run pytest test/
```

## Linting & Type Checking

### Ruff (Linting)

Ruff checks for code quality issues:

```bash
# Check for issues
uv run ruff check src/ test/

# Auto-fix fixable issues
uv run ruff check src/ test/ --fix
```

**Common Issues:**
- `F401`: Unused import
- `E402`: Import not at top of file
- `W293`: Blank line with whitespace

### Mypy (Type Checking)

Mypy checks type annotations:

```bash
uv run mypy src/agy src/flowsy
```

**Configuration:** See `[tool.mypy]` in `pyproject.toml`

## LLM Testing Strategy

### Mock-Based Tests (Default)

**Purpose:** Fast, reliable tests without API costs or network dependencies.

**Implementation:**
- Use `mock_llm_action_type` fixture from `test/integration/conftest.py`
- Mock returns deterministic JSON based on prompt content

**Example:**
```python
@pytest.fixture
def mock_llm_action_type():
    """Mock LLM that returns JSON based on prompt keywords."""
    def mock_model_call(prompt: str, model: str = "gpt-4") -> str:
        if "sales" in prompt.lower():
            return '{"category": "sales", "confidence": 0.95}'
        return '{"category": "unknown", "confidence": 0.5}'
    return ActionType(..., callable=mock_model_call)
```

### Real LLM Tests (Optional)

**Purpose:** Validate that flows work with actual LLM providers.

**Implementation:**
- Marked with `@pytest.mark.requires_api_key`
- Skip automatically if API key is missing

```python
@pytest.mark.requires_api_key
async def test_with_real_llm(uv_project):
    """Test with real LLM (requires OPENAI_API_KEY)."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    # Execute with real LLM
```

## Test Markers

```python
@pytest.mark.slow              # Takes > 5 seconds
@pytest.mark.integration       # Integration/E2E test
@pytest.mark.requires_api_key  # Needs real API key
@pytest.mark.email_integration # Email integration test
```

**Running by marker:**
```bash
pytest test/ -m "not slow"           # Fast tests only
pytest test/ -m "integration"        # Integration tests
pytest test/ -m "email_integration"  # Email tests only
```

## Test Structure

```
test/
├── unit/                           # Unit tests
│   ├── test_imap_smtp_account.py  # IMAP/SMTP account tests
│   ├── test_mock_email_account.py # Mock email account tests
│   └── ...
├── integration/                    # Integration tests
│   ├── conftest.py                # Shared fixtures
│   ├── test_template_e2e.py       # Template execution tests
│   ├── test_email_graph.py        # Graph API integration
│   ├── test_email_imap_smtp.py    # IMAP/SMTP integration
│   ├── .env.graph_test            # Graph API credentials (gitignored)
│   └── .env.imap_test             # IMAP/SMTP credentials (gitignored)
├── test_cli_init.py               # CLI tests
└── ...
```

## Test Fixtures

### Shared Fixtures (`test/integration/conftest.py`)

**`temp_project_dir`**
- Creates temporary directory for test projects
- Automatically cleaned up after test

**`uv_project`**
- Creates uv project with AGY installed (editable from source)
- Sets up complete project environment

**`mock_llm_action_type`**
- Provides mock LLM for fast testing
- Returns deterministic responses

## Running Tests

### Quick Development Cycle

```bash
# Fast unit tests only
uv run pytest test/unit/ -v

# Specific test file
uv run pytest test/unit/test_mock_email_account.py -v

# Specific test
uv run pytest test/unit/test_mock_email_account.py::TestMockEmailAccount::test_send_email -v
```

### Integration Testing

```bash
# All integration tests
uv run pytest test/integration/ -v

# Email integration tests (requires credentials)
uv run pytest test/integration/ -m "email_integration" -v

# Template tests
uv run pytest test/integration/test_template_e2e.py -v
```

### Full Test Suite

```bash
# All tests
uv run pytest test/ -v

# With coverage
uv run pytest test/ --cov=agy --cov-report=html

# Stop on first failure
uv run pytest test/ -x

# Short traceback
uv run pytest test/ --tb=short
```

### Pre-Push Check (Recommended)

```bash
# Run everything CI would run
uv run ruff check src/ test/ && \
uv run mypy src/agy src/flowsy && \
uv run pytest test/ -v --tb=short
```

## Email Integration Test Setup

### Graph API Tests

1. Create `.env.graph_test`:
```env
TENANT_ID=your-tenant-id
CLIENT_ID=your-client-id
CLIENT_SECRET=your-client-secret
USER_EMAIL=your-email@domain.com
```

2. Run tests:
```bash
uv run pytest test/integration/test_email_graph.py -v
```

### IMAP/SMTP Tests

1. Create `.env.imap_test`:
```env
IMAP_HOST=imap.gmail.com
IMAP_USER=your-email@gmail.com
IMAP_PASSWORD=your-app-password
SMTP_HOST=smtp.gmail.com
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

2. Run tests:
```bash
uv run pytest test/integration/test_email_imap_smtp.py -v
```

## Troubleshooting

### CI fails but local tests pass

**Possible causes:**
- Different Python version (CI uses 3.13)
- Missing dependencies in `.[dev]`
- Environment variables not set

**Solution:**
```bash
# Check CI logs
gh run view --log-failed

# Match CI environment
python3.13 -m pytest test/
```

### Flaky integration tests

**Cause:** External API eventual consistency (e.g., Graph API)

**Solution:** Add retry logic with `wait_for_*` helpers:
```python
def wait_for_email_deleted(account, subject, max_wait=30):
    """Wait for email to be deleted with retry."""
    for _ in range(max_wait // 3):
        emails = account.find_emails(folders=["Inbox"], subject_contains=subject)
        if not emails:
            return True
        time.sleep(3)
    return False
```

### Tests fail with import errors

**Cause:** Package not installed in editable mode

**Solution:**
```bash
uv sync
# or
pip install -e ".[dev]"
```

## Best Practices

### Unit Tests
1. Keep tests fast (< 1 second)
2. Mock all external dependencies
3. Test edge cases and error paths
4. One assertion per test (when practical)

### Integration Tests
1. Use realistic scenarios
2. Clean up temporary files
3. Mark slow tests with `@pytest.mark.slow`
4. Skip gracefully if credentials missing

### Email Tests
1. Use unique subjects with UUIDs to avoid collisions
2. Clean up test emails after tests
3. Handle eventual consistency with retries
4. Never commit credentials to git
