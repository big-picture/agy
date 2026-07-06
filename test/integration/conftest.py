"""Shared fixtures for integration tests."""

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Ensure every test in this directory is marked as integration."""
    integration_marker = pytest.mark.integration
    for item in items:
        item.add_marker(integration_marker)


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory for test projects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def _uv_env() -> dict[str, str]:
    """Return a deterministic environment for uv subprocesses."""
    env = os.environ.copy()
    # Prevent outer virtualenv leakage into the temporary uv project.
    env.pop("VIRTUAL_ENV", None)
    return env


def _run_or_fail(
    args: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and fail the test with useful diagnostics."""
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=_uv_env(),
    )
    if result.returncode != 0:
        rendered = " ".join(shlex.quote(part) for part in args)
        where = str(cwd) if cwd is not None else os.getcwd()
        pytest.fail(
            "\n".join(
                [
                    f"Command failed: {rendered}",
                    f"CWD: {where}",
                    f"Exit code: {result.returncode}",
                    f"STDOUT:\n{result.stdout}",
                    f"STDERR:\n{result.stderr}",
                ]
            )
        )
    return result


@pytest.fixture
def uv_project(temp_project_dir):
    """
    Create a uv project with agy installed (editable from source).

    This fixture:
    1. Runs `uv init` to create a new project
    2. Installs agy in editable mode from source
    3. Returns the project directory path
    """
    # Use a stable, valid package directory name inside temp dir.
    # Some tempfile basenames can end with "_" and are rejected by `uv init`.
    project_dir = temp_project_dir / "uv_project"

    # Get agy root directory (parent of test/)
    agy_root = Path(__file__).parent.parent.parent

    # Initialize uv project with the same interpreter running this test process.
    _run_or_fail(
        [
            "uv",
            "init",
            "--python",
            sys.executable,
            "--no-readme",
            "--no-workspace",
            "--vcs",
            "none",
            str(project_dir),
        ]
    )

    # Install agy in editable mode from source
    _run_or_fail(["uv", "add", "--editable", str(agy_root)], cwd=project_dir)

    return project_dir


@pytest.fixture
def mock_llm_action_type():
    """
    Create a mock model_call ActionType for testing without real API calls.

    Also configures the LLMCall singleton to use the mock, so that
    classify/extract/respond use the mock directly.
    """
    from agy.action_type import ActionType
    from agy.contrib.llm_call import LLMCall

    def mock_model_call(prompt: str, model: str = "gpt-4") -> str:
        """
        Mock LLM call that returns JSON based on prompt content.

        Simulates classification and generation responses for email routing.
        """
        prompt_lower = prompt.lower()

        # Detect if this is a respond/generate call (looking for "result" format)
        if (
            "generate" in prompt_lower
            or "respond" in prompt_lower
            or "answer" in prompt_lower
            or "reply" in prompt_lower
        ):
            return '{"result": "Thank you for your question. Your policy covers involuntary job loss if it occurs at least 14 days before your trip departure.", "confidence": 0.9}'

        # Classification: Question indicators
        if any(
            word in prompt_lower
            for word in [
                "question",
                "wondering",
                "would that be covered",
                "clarify",
                "how",
                "what kind",
            ]
        ):
            return '{"category": "question", "confidence": 0.95}'

        # Classification: New claim indicators
        elif any(
            word in prompt_lower
            for word in [
                "claim",
                "cancel",
                "cancellation",
                "refund",
                "emergency",
                "happened",
            ]
        ):
            return '{"category": "new_claim", "confidence": 0.92}'

        # Classification: Wrong department indicators
        elif any(
            word in prompt_lower
            for word in [
                "car insurance",
                "home insurance",
                "life insurance",
                "wrong department",
            ]
        ):
            return '{"category": "wrong_department", "confidence": 0.90}'

        # Default to question with lower confidence
        else:
            return '{"category": "question", "confidence": 0.70}'

    # Configure LLMCall singleton to use the mock
    llm = LLMCall()
    llm.set_model_call(callable=mock_model_call)

    return ActionType(
        object_name="global_function",
        method_name="model_call",
        kwargs={"prompt": str, "model": str},
        callable=mock_model_call,
        description="Mock LLM call for testing",
    )
