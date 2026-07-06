"""Tests for contrib loader."""

# test/contrib/test_contrib_loader.py

from pathlib import Path
from typing import Any

import pytest

from agy.action_call import ActionCall
from agy.action_executor import ActionExecutor, ActionRegistry
from agy.action_type import ActionType
from agy.contrib.action_type_functions import load_files_text


@pytest.fixture
def sample_files(tmp_path: Path):
    """Sample files.

    Args:
        tmp_path: tmp path.
    """
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("Hello world", encoding="utf-8")

    csv_file = tmp_path / "data.csv"
    csv_file.write_text("col1,col2\n1,2", encoding="utf-8")

    html_file = tmp_path / "page.html"
    html_file.write_text("<html><body><p>Paragraph</p></body></html>", encoding="utf-8")

    return txt_file, csv_file, html_file


def test_load_files_text_success(sample_files):
    """Test that load files text success.

    Args:
        sample_files: sample files.
    """
    result = load_files_text(*(str(path) for path in sample_files))

    # Now returns string directly (Pattern 2)
    assert isinstance(result, str)
    assert "*** sample.txt ***" in result
    assert "Hello world" in result
    assert "*** data.csv ***" in result
    assert "col1, col2" in result
    assert "Paragraph" in result


def test_load_files_text_missing_file(tmp_path: Path):
    """Test that load files text missing file.

    Args:
        tmp_path: tmp path.
    """
    missing = tmp_path / "missing.txt"

    # Now raises exception (Pattern 2)
    with pytest.raises(FileNotFoundError):
        load_files_text(str(missing))


@pytest.mark.asyncio
async def test_load_files_text_action_call(sample_files):
    """Test that load files text action call.

    Args:
        sample_files: sample files.
    """
    registry = ActionRegistry()

    action_type = ActionType(
        object_name="global_function",
        method_name="load_files_text",
        args=[str],
        callable=load_files_text,
    )
    registry.register(action_type)

    executor = ActionExecutor(registry)

    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[(f"load_files_text('{sample_files[0]}', '{sample_files[1]}')", False)],
        kwargs={},
        output="content",
    )

    context: dict[str, Any] = {}
    await executor.execute(action_call, context)

    # ActionExecutor sets success/error_msg automatically (Pattern 2)
    assert context["success"] is True
    # content is now a string directly, not a Dict
    assert isinstance(context["content"], str)
    assert "*** sample.txt ***" in context["content"]
    assert "*** data.csv ***" in context["content"]
