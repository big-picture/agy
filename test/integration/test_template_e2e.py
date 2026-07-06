"""End-to-end integration tests for AGY templates."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from agy import Flow, FlowExecutor


@pytest.mark.slow
@pytest.mark.integration
def test_agy_installation_with_uv(temp_project_dir):
    """Test that agy can be installed via uv with all dependencies."""
    project_dir = temp_project_dir
    agy_root = Path(__file__).parent.parent.parent

    # uv init
    subprocess.run(
        [
            "uv",
            "init",
            "--python",
            sys.executable,
            "--name",
            "uv-project",
            "--no-readme",
            "--no-workspace",
            "--vcs",
            "none",
            str(project_dir),
        ],
        check=True,
        capture_output=True,
    )

    # Install agy (editable from source)
    subprocess.run(
        ["uv", "add", "--editable", str(agy_root)],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )

    # Verify agy CLI is available
    result = subprocess.run(
        ["uv", "run", "agy", "--help"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Agy" in result.stdout or "agy" in result.stdout.lower()


@pytest.mark.slow
@pytest.mark.integration
def test_agy_init_minimal_template(uv_project):
    """Test agy init creates minimal template structure in agy_project/."""
    subprocess.run(
        ["uv", "run", "agy", "init"],
        cwd=uv_project,
        capture_output=True,
        text=True,
        check=True,
    )

    # Verify agy_project directory was created
    project_dir = uv_project / "agy_project"
    assert project_dir.exists()
    assert project_dir.is_dir()

    # Verify structure
    assert (project_dir / "prompts").exists()
    assert (project_dir / "data").exists()
    assert (project_dir / "objects").exists()
    assert (project_dir / "example_flow.flowsy").exists()
    assert (project_dir / "main.py").exists()
    assert (project_dir / ".env.example").exists()

    # Verify file contents
    assert (project_dir / "prompts" / "example_instruction.md").exists()

    # Verify pyproject.toml has [project] table (runnable without parent uv init)
    pyproject = project_dir / "pyproject.toml"
    assert pyproject.exists()
    content = pyproject.read_text()
    assert "[project]" in content
    assert 'name = "agy-minimal"' in content
    assert "[tool.agy.llm]" in content


@pytest.mark.slow
@pytest.mark.integration
def test_agy_init_email_routing_mock_template(uv_project):
    """Test agy init --template email_routing_mock creates correct structure."""
    subprocess.run(
        ["uv", "run", "agy", "init", "--template", "email_routing_mock"],
        cwd=uv_project,
        capture_output=True,
        text=True,
        check=True,
    )

    # Verify directory was created
    project_dir = uv_project / "agy_email_routing_mock"
    assert project_dir.exists()
    assert project_dir.is_dir()

    # Verify email_routing_mock structure
    assert (project_dir / "email_routing_flow.flowsy").exists()
    assert (project_dir / "mock_mailbox/inbox").exists()
    assert (project_dir / "objects/claim_functions.py").exists()
    assert (project_dir / "prompts/classify_insurance_email.md").exists()

    # Verify .eml files exist in mock_mailbox/inbox
    eml_files = list((project_dir / "mock_mailbox/inbox").glob("*.eml"))
    assert len(eml_files) == 6

    # Verify pyproject.toml has [project] table
    pyproject = project_dir / "pyproject.toml"
    assert pyproject.exists()
    content = pyproject.read_text()
    assert "[project]" in content
    assert 'name = "agy-email-routing-mock"' in content
    assert "[tool.agy.llm]" in content

    # Verify flow can be parsed
    flow = Flow.from_flowsy(str(project_dir / "email_routing_flow.flowsy"))
    assert flow.name == "Travel Insurance Email Routing"
    assert len(flow.nodes) >= 5


@pytest.mark.slow
@pytest.mark.integration
def test_agy_init_software_support_jira_template(uv_project):
    """Test agy init --template software_support_jira creates correct structure."""
    subprocess.run(
        ["uv", "run", "agy", "init", "--template", "software_support_jira"],
        cwd=uv_project,
        capture_output=True,
        text=True,
        check=True,
    )

    project_dir = uv_project / "agy_software_support_jira"
    assert project_dir.exists()
    assert project_dir.is_dir()

    assert (project_dir / "software_support_flow.flowsy").exists()
    assert (project_dir / "prompts" / "classify_ticket_type.md").exists()
    assert (project_dir / "prompts" / "answer_from_faq.md").exists()
    assert (project_dir / "objects" / "support_helpers.py").exists()
    assert (project_dir / "data" / "software_support_faq.md").exists()
    assert (project_dir / ".env.example").exists()
    assert (project_dir / "pyproject.toml").exists()

    pyproject = project_dir / "pyproject.toml"
    content = pyproject.read_text()
    assert "[project]" in content
    assert 'name = "agy-software-support-jira"' in content
    assert "[tool.agy.llm]" in content

    flow = Flow.from_flowsy(str(project_dir / "software_support_flow.flowsy"))
    assert flow.name == "Software Support Ticket Routing"
    assert len(flow.nodes) >= 4


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.asyncio
async def test_email_routing_mock_template_execution(uv_project, mock_llm_action_type):
    """Test email_routing_mock template executes with mock LLM."""
    # Initialize template
    subprocess.run(
        ["uv", "run", "agy", "init", "--template", "email_routing_mock"],
        cwd=uv_project,
        check=True,
        capture_output=True,
    )

    project_dir = uv_project / "agy_email_routing_mock"

    # Add project to path for imports
    sys.path.insert(0, str(project_dir))

    try:
        from agy.integrations.email import MockEmailAccount

        # Load flow
        flow = Flow.from_flowsy(str(project_dir / "email_routing_flow.flowsy"))

        # Use MockEmailAccount to get emails
        account = MockEmailAccount(
            base_path=project_dir / "mock_mailbox", user_email="test@example.com"
        )
        emails = account.get_emails(folders=["inbox"], max_results=1)
        assert len(emails) > 0
        email = emails[0]

        # Change to project directory for file path resolution
        original_cwd = os.getcwd()
        os.chdir(project_dir)

        try:
            # Execute with mock LLM
            executor = FlowExecutor(
                action_types=[mock_llm_action_type],
                context_in={"email": email},
            )
            result = await executor.execute(flow)
        finally:
            os.chdir(original_cwd)

        # Validate results
        category = result.get("category") or result.get("result")
        assert category is not None
        assert result.get("confidence") is not None
        assert 0 <= result.get("confidence", 0) <= 1

        # Should classify into one of the expected categories
        assert category in ["question", "new_claim", "wrong_department"]

    finally:
        # Clean up path
        if str(project_dir) in sys.path:
            sys.path.remove(str(project_dir))


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.requires_api_key
async def test_email_routing_mock_template_execution_real_llm(uv_project):
    """Test email_routing_mock template with real LLM (requires OPENAI_API_KEY)."""
    # Check if API key is available
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set, skipping real LLM test")

    # Initialize template
    subprocess.run(
        ["uv", "run", "agy", "init", "--template", "email_routing_mock"],
        cwd=uv_project,
        check=True,
        capture_output=True,
    )

    project_dir = uv_project / "agy_email_routing_mock"

    # Add project to path for imports
    sys.path.insert(0, str(project_dir))

    try:
        from agy.integrations.email import MockEmailAccount

        # Load flow
        flow = Flow.from_flowsy(str(project_dir / "email_routing_flow.flowsy"))

        # Use MockEmailAccount to get emails
        account = MockEmailAccount(
            base_path=project_dir / "mock_mailbox", user_email="test@example.com"
        )
        emails = account.get_emails(folders=["inbox"], max_results=1)
        assert len(emails) > 0
        email = emails[0]

        # Change to project directory for file path resolution
        original_cwd = os.getcwd()
        os.chdir(project_dir)

        try:
            # Execute with real LLM (uses default model_call from contrib)
            executor = FlowExecutor(context_in={"email": email})
            result = await executor.execute(flow)
        finally:
            os.chdir(original_cwd)

        # Validate results
        category = result.get("category") or result.get("result")
        assert category is not None
        assert result.get("confidence") is not None
        assert 0 <= result.get("confidence", 0) <= 1

        # Should classify into one of the expected categories
        assert category in ["question", "new_claim", "wrong_department"]

    finally:
        # Clean up path
        if str(project_dir) in sys.path:
            sys.path.remove(str(project_dir))
