"""Tests for get_prompt_from_str and get_prompt_from_file"""

from pathlib import Path

import pytest

from agy.action_call import ActionCall
from agy.action_executor import ActionExecutor, ActionRegistry
from agy.action_type import ActionType
from agy.contrib.action_type_functions import get_prompt_from_file, get_prompt_from_str


def test_get_prompt_from_str_success():
    """Test that get_prompt_from_str formats template correctly"""
    template = "Hello {name}, you have {count} messages."
    result = get_prompt_from_str(template, name="Alice", count=5)

    assert result == "Hello Alice, you have 5 messages."


def test_get_prompt_from_str_missing_key():
    """Test that get_prompt_from_str raises KeyError for missing keys"""
    template = "Hello {name}, you have {count} messages."

    with pytest.raises(KeyError) as exc_info:
        get_prompt_from_str(template, name="Alice")

    assert "count" in str(exc_info.value)


def test_get_prompt_from_file_success(tmp_path: Path):
    """Test that get_prompt_from_file loads and formats template file"""
    template_file = tmp_path / "template.md"
    template_file.write_text(
        "Hello {name}, you have {count} messages.", encoding="utf-8"
    )

    result = get_prompt_from_file(str(template_file), name="Bob", count=10)

    assert result == "Hello Bob, you have 10 messages."


def test_get_prompt_from_file_missing_file(tmp_path: Path):
    """Test that get_prompt_from_file raises FileNotFoundError for missing file"""
    missing_file = tmp_path / "missing.md"

    with pytest.raises(FileNotFoundError):
        get_prompt_from_file(str(missing_file), name="Alice")


def test_get_prompt_from_file_missing_key(tmp_path: Path):
    """Test that get_prompt_from_file raises KeyError for missing template keys"""
    template_file = tmp_path / "template.md"
    template_file.write_text(
        "Hello {name}, you have {count} messages.", encoding="utf-8"
    )

    with pytest.raises(KeyError) as exc_info:
        get_prompt_from_file(str(template_file), name="Alice")

    assert "count" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_prompt_from_str_action_call():
    """Test that get_prompt_from_str works as an action"""
    registry = ActionRegistry()

    action_type = ActionType(
        object_name="global_function",
        method_name="get_prompt_from_str",
        kwargs={"template": str},
        callable=get_prompt_from_str,
    )
    registry.register(action_type)

    executor = ActionExecutor(registry)

    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("get_prompt_from_str(template='Hello {name}', name='Alice')", False)],
        kwargs={},
        output="prompt",
    )

    context: dict[str, str | bool] = {}
    await executor.execute(action_call, context)

    assert context["success"] is True
    assert context["prompt"] == "Hello Alice"


@pytest.mark.asyncio
async def test_get_prompt_from_file_action_call(tmp_path: Path):
    """Test that get_prompt_from_file works as an action"""
    template_file = tmp_path / "template.md"
    template_file.write_text("Hello {name}, count: {count}", encoding="utf-8")

    registry = ActionRegistry()

    action_type = ActionType(
        object_name="global_function",
        method_name="get_prompt_from_file",
        kwargs={"file_path": str},
        callable=get_prompt_from_file,
    )
    registry.register(action_type)

    executor = ActionExecutor(registry)

    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[
            (
                f"get_prompt_from_file(file_path='{template_file}', name='Bob', count=42)",
                False,
            )
        ],
        kwargs={},
        output="prompt",
    )

    context: dict[str, str | bool] = {}
    await executor.execute(action_call, context)

    assert context["success"] is True
    assert context["prompt"] == "Hello Bob, count: 42"
