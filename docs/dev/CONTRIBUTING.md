# Contributing to Agy

Thank you for your interest in contributing to Agy!

## Development Environment Setup

### Prerequisites

- Python 3.11 or higher
- `uv` (recommended) or `pip`
- Git

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/MaximilianVogel/agy.git
   cd agy
   ```

2. **Install dependencies:**
   ```bash
   uv sync --extra dev
   ```
   
   Or with pip:
   ```bash
   pip install -e ".[dev]"
   ```

3. **Run tests (verify everything works):**
   ```bash
   uv run pytest test/ -v
   ```

4. **Run linting (verify code quality):**
   ```bash
   uv run ruff check src/ test/
   uv run mypy src/agy src/flowsy
   ```

## Code Style

### Linting with Ruff

We use **ruff** for linting and code style enforcement:

```bash
# Check for issues
uv run ruff check src/ test/

# Auto-fix fixable issues
uv run ruff check src/ test/ --fix
```

**Configuration:** See `[tool.ruff]` in `pyproject.toml`

### Type Checking with Mypy

We use **mypy** for static type checking:

```bash
uv run mypy src/agy src/flowsy
```

### Code Style Guidelines

- **PEP 8**: Follow Python Style Guide
- **Type Hints**: Required for public functions
- **Line Length**: 88 characters (configured in ruff)

**Example:**
```python
# ✅ Good
def process_email(
    email_text: str,
    categories: list[str],
    instruction: str | None = None,
) -> dict[str, Any]:
    """Process email and return classification result."""
    return classify(email_text, categories, instruction)

# ❌ Bad
def process_email(email_text,categories,instruction=None):
    return classify(email_text,categories,instruction)
```

### Naming Conventions

- **Functions/Variables**: `snake_case` (e.g., `process_email`, `user_name`)
- **Classes**: `PascalCase` (e.g., `ActionExecutor`, `FlowExecutor`)
- **Constants**: `UPPER_CASE` (e.g., `STANDARD_DIRECTORIES`, `END_NODE_NAME`)

## Testing

### Running Tests

```bash
# All tests
uv run pytest test/ -v

# Unit tests only (fast)
uv run pytest test/unit/ -v

# Integration tests
uv run pytest test/integration/ -v

# Specific test file
uv run pytest test/unit/test_mock_email_account.py -v
```

### Writing New Tests

- Place unit tests in `test/unit/`
- Place integration tests in `test/integration/`
- Use `@pytest.mark.asyncio` for async tests
- Use `@pytest.mark.slow` for slow tests (> 5s)

**Example:**
```python
import pytest
from agy.action_executor import ActionExecutor, ActionRegistry

@pytest.mark.asyncio
async def test_my_new_feature():
    """Test description."""
    # Setup
    registry = ActionRegistry()
    executor = ActionExecutor(registry)
    
    # Execute
    result = await executor.execute(...)
    
    # Assert
    assert result == expected
```

## Project Structure

```
agy/
├── src/
│   ├── agy/                # Main package
│   ├── contrib/           # Built-in ActionTypes
│   │   ├── actions/      # Modular action implementations
│   │   │   ├── classify.py
│   │   │   ├── extract.py
│   │   │   ├── respond.py
│   │   │   └── ...
│   │   ├── action_type_functions.py  # Re-exports (backward compat)
│   │   └── action_types.py           # ActionType registry
│   ├── integrations/      # External service integrations
│   │   └── email/        # Email providers (Graph, Gmail, IMAP/SMTP)
│   │   ├── templates/     # Project templates
│   │   └── utils/         # Utility functions
│   └── flowsy/            # FLOWSY parser and grammar
├── test/                  # Test files
│   ├── unit/             # Unit tests
│   └── integration/      # Integration tests
├── docs/                  # Documentation
│   └── dev/              # Developer documentation
├── .github/workflows/     # CI/CD workflows
└── pyproject.toml         # Project configuration
```

## Adding New Contrib Functions

Contrib functions are organized in `src/agy/contrib/actions/`:

### Creating a New Action

1. Create a new file in `src/agy/contrib/actions/`:

```python
# src/agy/contrib/actions/my_action.py
"""My custom action."""

from agy.action_type import ActionType

def my_action(param: str, option: str | None = None) -> dict[str, Any]:
    """Process param and return result."""
    result = do_something(param, option)
    return {
        "result": result,
        "context": {"processed": True},
    }

ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="my_action",
    kwargs={"param": str, "option": str | None},
    callable=my_action,
    description="My custom action description",
)
```

2. Export in `src/agy/contrib/actions/__init__.py`:

```python
from .my_action import my_action, ACTION_TYPE as MY_ACTION_TYPE
```

3. Register in `src/agy/contrib/action_types.py`:

```python
from agy.contrib.actions.my_action import ACTION_TYPE as MY_ACTION_TYPE

def get_contrib_action_types() -> list[ActionType]:
    return [
        # ... existing types
        MY_ACTION_TYPE,
    ]
```

4. Re-export in `src/agy/contrib/action_type_functions.py` (for backward compatibility):

```python
from agy.contrib.actions.my_action import my_action
```

### Return Formats

**Simple format** (basic results):
```python
def my_function(param: str) -> str:
    return "processed_value"
```

**Dict format** (with context/flow control):
```python
def my_function(param: str) -> dict[str, Any]:
    return {
        "result": "main_value",
        "context": {"confidence": 0.9},
        "flow_control": "TERMINATE"  # Optional
    }
```

## CI/CD

### Automated Checks

Every push and PR triggers GitHub Actions:

1. **Lint**: `ruff check` + `mypy`
2. **Test**: `pytest test/`
3. **Build**: `python -m build`

### Pre-Push Checklist

Before pushing, run locally:

```bash
# Same checks as CI
uv run ruff check src/ test/
uv run mypy src/agy src/flowsy
uv run pytest test/ -v --tb=short
```

### Viewing CI Status

```bash
# List recent runs
gh run list --limit 5

# View failed logs
gh run view --log-failed

# Open in browser
gh run view --web
```

## Pull Request Process

### 1. Create Branch

```bash
git checkout develop
git pull origin develop
git checkout -b feature/my-new-feature
```

### 2. Make Changes

- Write code
- Add/update tests
- Update documentation (if needed)
- Run linting and tests locally

### 3. Commit

```bash
git add .
git commit -m "feat: Add new feature XYZ"
```

**Commit Message Format:**
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `test:` - Tests
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks
- `style:` - Code style/formatting

### 4. Push and Create PR

```bash
git push origin feature/my-new-feature
gh pr create --base develop --title "feat: Add new feature XYZ"
```

### 5. Wait for CI

- CI runs automatically on PR
- All checks must pass before merge
- Address any review comments

## Pull Request Checklist

- [ ] Code follows style guidelines (ruff passes)
- [ ] Type hints added (mypy passes)
- [ ] All tests pass (`pytest test/`)
- [ ] New tests added for new features
- [ ] Documentation updated (if needed)
- [ ] Commit messages follow format
- [ ] CI is green
- [ ] No debug prints or commented-out code

## Core Modules

The following modules represent the **core logic of AGY** and should **only be modified for bug fixes or fundamental extensions**:

- `src/agy/action_call.py` - Action call representation
- `src/agy/action_executor.py` - Action execution
- `src/agy/action_type.py` - Action type definitions
- `src/agy/ast_parser.py` - AST-based parsing
- `src/agy/config.py` - Configuration
- `src/agy/edge.py` - Edge definitions
- `src/agy/flow_executor.py` - Flow execution
- `src/agy/flow.py` - Flow definitions
- `src/agy/node_executor.py` - Node execution
- `src/agy/node.py` - Node definitions
- `src/flowsy/flowsy_parser.py` - FLOWSY parsing

**Important:** Changes to core modules can affect the entire architecture. Coordinate with maintainers before making changes.

## Questions?

- Create an issue in the repository
- Check existing documentation in `docs/`
- Review test files for usage examples

Thank you for contributing to Agy!
