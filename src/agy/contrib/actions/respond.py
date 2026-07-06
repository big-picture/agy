"""Contrib respond action."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agy.action_type import ActionType
from agy.utils.file_readers import find_file_in_standard_dirs

_agy_logger = logging.getLogger("agy")


def respond(
    input_text: str,
    instruction: str | None = None,
    instruction_file: str | None = None,
    augmentation: str | None = None,
    context: dict[str, Any] | None = None,
    model_call: Callable | None = None,
) -> dict[str, Any]:
    """Generate a response using an LLM."""
    try:
        from agy.contrib.llm_call import LLMCall

        llm = LLMCall()
        call_func = model_call if model_call else llm.model_call

        template_path = (
            Path(__file__).parent.parent
            / "prompt_contents"
            / "generic_respond_instruction.md"
        )
        template = template_path.read_text(encoding="utf-8")

        if instruction:
            specific_instructions = instruction
        elif instruction_file:
            file_path = find_file_in_standard_dirs(instruction_file)
            specific_instructions = file_path.read_text(encoding="utf-8")
        else:
            specific_instructions = "Use just the generic generation guidelines."

        augmentation_text = augmentation if augmentation else "No augmentation provided"
        prompt = template.format(
            input_text=input_text,
            specific_instructions=specific_instructions,
            augmentation=augmentation_text,
        )

        _agy_logger.debug(f"Generate() prompt:\n{prompt}")
        result = call_func(prompt)
        _agy_logger.debug(f"Generate() model response:\n{result}")

        result_clean = result.strip()
        if result_clean.startswith("```"):
            lines = result_clean.split("\n")
            result_clean = "\n".join(lines[1:-1]) if len(lines) > 2 else result_clean

        try:
            parsed = json.loads(result_clean)
        except json.JSONDecodeError as exc:
            _agy_logger.debug(
                f"Generate() JSON parsing failed. Raw response: {result_clean}"
            )
            raise ValueError(f"Failed to parse JSON response: {exc}")

        if not isinstance(parsed, dict):
            raise ValueError("Generate() must return a JSON object")
        if "result" not in parsed or "confidence" not in parsed:
            raise ValueError(
                "Generate() response must contain 'result' and 'confidence'"
            )

        confidence = float(parsed["confidence"])
        if not (0 <= confidence <= 1):
            raise ValueError(f"Confidence must be between 0 and 1, got {confidence}")

        return {"result": parsed["result"], "context": {"confidence": confidence}}
    except Exception as exc:  # pylint: disable=broad-except
        _agy_logger.error(f"Generate() failed: {exc}")
        raise


ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="respond",
    kwargs={
        "input_text": str,
        "instruction": str | None,
        "instruction_file": str | None,
        "augmentation": str | None,
    },
    callable=respond,
    description="Generate a response based on input text and optional instructions",
)
