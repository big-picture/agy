"""Tests for contrib generator."""

# test/contrib/test_contrib_generator.py

import json
from typing import Any

import pytest

from agy.action_call import ActionCall
from agy.action_executor import ActionExecutor, ActionRegistry
from agy.action_type import ActionType
from agy.contrib.action_type_functions import respond


def fake_generator_llm(prompt: str, model: str = "gpt-5-mini") -> str:
    """Fake generator llm.

    Args:
        prompt: prompt.
        model: model.

    Returns:
        str: Operation result.
    """
    payload = {"result": "Here is the generated response.", "confidence": 0.85}
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_respond_basic():
    """Test that respond basic."""
    result = respond(
        input_text="Please draft a reply.",
        instruction="Keep it concise.",
        augmentation="Customer is VIP.",
        model_call=fake_generator_llm,
    )

    assert result["result"] == "Here is the generated response."
    assert result["context"]["confidence"] == 0.85


@pytest.mark.asyncio
async def test_respond_instruction_file(tmp_path):
    """Test that respond instruction file.

    Args:
        tmp_path: tmp path.
    """
    instruction_file = tmp_path / "instruction.txt"
    instruction_file.write_text("Answer politely.", encoding="utf-8")

    result = respond(
        input_text="Need help with my account.",
        instruction_file=str(instruction_file),
        model_call=fake_generator_llm,
    )

    assert result["result"] == "Here is the generated response."


@pytest.mark.asyncio
async def test_respond_missing_model_call():
    """Test that respond() uses LLMCall singleton when model_call is None."""
    # Should work now because LLMCall is automatically initialized
    from agy.contrib.llm_call import LLMCall

    def fake_respond_call(prompt: str, **kwargs) -> str:
        """Fake respond call.

        Args:
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: Operation result.
        """
        return '{"result": "response", "confidence": 0.9}'

    llm = LLMCall()
    llm.set_model_call(callable=fake_respond_call)

    result = respond(input_text="Test", model_call=None)
    assert result["result"] == "response"
    assert result["context"]["confidence"] == 0.9


@pytest.mark.asyncio
async def test_respond_invalid_json():
    """Test that respond invalid json."""

    def bad_llm(prompt: str, model: str = "gpt-5-mini") -> str:
        """Bad llm.

        Args:
            prompt: prompt.
            model: model.

        Returns:
            str: Operation result.
        """
        return "not-json"

    with pytest.raises(ValueError, match="Failed to parse JSON response"):
        respond(input_text="Test", model_call=bad_llm)


@pytest.mark.asyncio
async def test_respond_action_executor(tmp_path):
    """Test that respond action executor.

    Args:
        tmp_path: tmp path.
    """
    registry = ActionRegistry()

    model_call_action_type = ActionType(
        object_name="global_function",
        method_name="model_call",
        kwargs={"prompt": str, "model": str},
        callable=fake_generator_llm,
    )
    registry.register(model_call_action_type)

    generator_action_type = ActionType(
        object_name="global_function",
        method_name="respond",
        kwargs={
            "input_text": str,
            "instruction": str,
            "instruction_file": str,
            "augmentation": str,
        },
        callable=respond,
    )
    registry.register(generator_action_type)

    # Set LLMCall singleton to use fake_generator_llm
    from agy.contrib.llm_call import LLMCall

    llm = LLMCall()
    llm.set_model_call(callable=fake_generator_llm)

    executor = ActionExecutor(registry)

    instruction_file = tmp_path / "instruction.txt"
    instruction_file.write_text("Be friendly.", encoding="utf-8")

    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[
            (
                f"respond(input_text='Hello, can you assist?', instruction_file='{instruction_file}', augmentation='Customer status: Gold', instruction='')",
                False,
            )
        ],
        kwargs={},
        output="generated",
    )

    context: dict[str, Any] = {}
    await executor.execute(action_call, context)

    assert context["generated"] == "Here is the generated response."
    assert context["confidence"] == 0.85
