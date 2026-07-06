"""Tests for agy CLI init command."""

import os
import tempfile
from pathlib import Path

from agy.cli import init_project


def test_init_creates_directories():
    """Test that init creates all required directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project()

            base_path = Path("agy_project")
            assert (base_path / "prompts").exists()
            assert (base_path / "prompts").is_dir()
            assert (base_path / "data").exists()
            assert (base_path / "data").is_dir()
            assert (base_path / "objects").exists()
            assert (base_path / "objects").is_dir()
        finally:
            os.chdir(original_cwd)


def test_init_creates_files():
    """Test that init creates all required files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project()

            base_path = Path("agy_project")
            assert (base_path / "prompts" / "example_instruction.md").exists()
            assert (base_path / "objects" / "example_context.py").exists()
            assert (base_path / "example_flow.flowsy").exists()
            assert (base_path / "main.py").exists()
            assert (base_path / ".env.example").exists()
            assert (base_path / "README.md").exists()
        finally:
            os.chdir(original_cwd)


def test_init_fails_if_directory_exists():
    """Test that init fails if project directory already exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project()

            # Try to run again - should fail
            from contextlib import redirect_stderr, redirect_stdout
            from io import StringIO

            stderr = StringIO()
            stdout = StringIO()
            with redirect_stderr(stderr), redirect_stdout(stdout):
                try:
                    init_project()
                    assert False, "Should have exited with error"
                except SystemExit as e:
                    assert e.code != 0
                    assert (
                        "already exists" in stderr.getvalue()
                        or "already exists" in stdout.getvalue()
                    )
        finally:
            os.chdir(original_cwd)


def test_init_instruction_file_content():
    """Test that instruction file has expected content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project()

            instruction_file = (
                Path("agy_project") / "prompts" / "example_instruction.md"
            )
            content = instruction_file.read_text()

            assert (
                "# Example Classification Instruction" in content
                or "# Example Instruction" in content
            )
            assert (
                "classification" in content.lower() or "categorize" in content.lower()
            )
        finally:
            os.chdir(original_cwd)


def test_init_model_file_content():
    """Test that model file has expected content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project()

            model_file = Path("agy_project") / "objects" / "example_context.py"
            content = model_file.read_text()

            assert "class ExampleContext" in content
            assert "def __init__" in content
        finally:
            os.chdir(original_cwd)


def test_init_flow_file_content():
    """Test that flow file has expected content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project()

            flow_file = Path("agy_project") / "example_flow.flowsy"
            content = flow_file.read_text()

            assert "name: Example Flow" in content
            assert "context_in:" in content
            assert "context: ExampleContext" in content
            assert "nodes:" in content
            assert "context.text" in content
        finally:
            os.chdir(original_cwd)


def test_init_data_readme_content():
    """Test that data directory exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project()

            data_dir = Path("agy_project") / "data"
            assert data_dir.exists()
            assert data_dir.is_dir()
        finally:
            os.chdir(original_cwd)


def test_init_creates_agy_project_directory():
    """Test that init creates agy_project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project()

            project_dir = Path("agy_project")
            assert project_dir.exists()
            assert project_dir.is_dir()
            assert (project_dir / "prompts").exists()
            assert (project_dir / "data").exists()
            assert (project_dir / "objects").exists()
            assert (project_dir / "prompts" / "example_instruction.md").exists()
            assert (project_dir / "main.py").exists()
            assert (project_dir / "README.md").exists()

            # Verify README.md content
            readme_content = (project_dir / "README.md").read_text()
            assert "Agy Minimal Template" in readme_content
            assert "python main.py" in readme_content
        finally:
            os.chdir(original_cwd)


def test_init_main_file_content():
    """Test that main.py has expected content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project()

            main_file = Path("agy_project") / "main.py"
            content = main_file.read_text()

            assert "from agy import Flow, FlowExecutor" in content
            assert "from objects.example_context import ExampleContext" in content
            assert "Flow.from_flowsy" in content
            assert "FlowExecutor" in content
            assert "asyncio.run(main())" in content
        finally:
            os.chdir(original_cwd)


def test_init_env_example_file_content():
    """Test that .env.example has expected content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project()

            env_file = Path("agy_project") / ".env.example"
            content = env_file.read_text()

            assert "OPENAI_API_KEY" in content
            assert "your_openai_api_key_here" in content
        finally:
            os.chdir(original_cwd)


def test_init_email_routing_mock_template():
    """Test that email_routing_mock template creates agy_email_routing_mock directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project(template="email_routing_mock")

            project_dir = Path("agy_email_routing_mock")
            assert project_dir.exists()
            assert project_dir.is_dir()
            assert (project_dir / "email_routing_flow.flowsy").exists()
            assert (project_dir / "mock_mailbox" / "inbox").exists()
            assert (project_dir / "README.md").exists()

            # Verify README.md content
            readme_content = (project_dir / "README.md").read_text()
            assert "Email Routing" in readme_content
            assert "python main.py" in readme_content
        finally:
            os.chdir(original_cwd)


def test_init_software_support_jira_template():
    """Test that software_support_jira template creates expected project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_project(template="software_support_jira")

            project_dir = Path("agy_software_support_jira")
            assert project_dir.exists()
            assert project_dir.is_dir()
            assert (project_dir / "software_support_flow.flowsy").exists()
            assert (project_dir / "prompts" / "classify_ticket_type.md").exists()
            assert (project_dir / "prompts" / "answer_from_faq.md").exists()
            assert (project_dir / "objects" / "support_helpers.py").exists()
            assert (project_dir / "data" / "software_support_faq.md").exists()
            assert (project_dir / ".env.example").exists()
            assert (project_dir / "pyproject.toml").exists()
            assert (project_dir / "README.md").exists()
        finally:
            os.chdir(original_cwd)
