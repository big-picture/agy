"""Contrib classify action."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agy.action_type import ActionType
from agy.utils.file_readers import find_file_in_standard_dirs

_agy_logger = logging.getLogger("agy")


def classify(
    input_text: str,
    categories: list[str],
    instruction: str | None = None,
    instruction_file: str | None = None,
    augmentation: str | None = None,
    context: dict[str, Any] | None = None,
    model_call: Callable | None = None,
) -> dict[str, Any]:
    """Classify text into one of the given categories."""
    try:
        from agy.contrib.llm_call import LLMCall

        llm = LLMCall()
        call_func = model_call if model_call else llm.model_call

        if not categories:
            raise ValueError("classify() requires at least one category")
        if len(categories) < 2:
            raise ValueError(
                f"classify() requires at least 2 categories for meaningful classification, got {len(categories)}: {categories}"
            )

        template_path = (
            Path(__file__).parent.parent
            / "prompt_contents"
            / "generic_classify_instruction.md"
        )
        template = template_path.read_text(encoding="utf-8")

        if instruction:
            specific_instructions = instruction
        elif instruction_file:
            file_path = find_file_in_standard_dirs(instruction_file)
            specific_instructions = file_path.read_text(encoding="utf-8")
        else:
            specific_instructions = "Use just the generic classification guidelines."

        classes_str = "\n".join(f"- {cls}" for cls in categories)
        augmentation_text = augmentation if augmentation else "None provided"
        prompt = template.format(
            specific_instructions=specific_instructions,
            augmentation=augmentation_text,
            classes=classes_str,
            input_text=input_text,
        )

        _agy_logger.debug(f"Classify prompt:\n{prompt}")
        result = call_func(prompt)
        _agy_logger.debug(f"Classify model response:\n{result}")

        result_clean = result.strip()
        if result_clean.startswith("```"):
            lines = result_clean.split("\n")
            result_clean = "\n".join(lines[1:-1]) if len(lines) > 2 else result_clean

        try:
            parsed = json.loads(result_clean)
            if (
                not isinstance(parsed, dict)
                or "category" not in parsed
                or "confidence" not in parsed
            ):
                raise ValueError(
                    "Response must contain 'category' and 'confidence' keys"
                )

            selected_class = parsed["category"]
            confidence = float(parsed["confidence"])
            if not (0 <= confidence <= 1):
                raise ValueError(
                    f"Confidence must be between 0 and 1, got {confidence}"
                )

            _agy_logger.debug(
                f"Classify parsed result: category={selected_class}, confidence={confidence}"
            )
            if selected_class not in categories:
                _agy_logger.warning(
                    f"Classify returned category '{selected_class}' which doesn't match any provided category: {categories}"
                )

            return {"result": selected_class, "context": {"confidence": confidence}}
        except json.JSONDecodeError as exc:
            _agy_logger.debug(
                f"Classify JSON parsing failed. Raw response: {result_clean}"
            )
            raise ValueError(f"Failed to parse JSON response: {exc}")
    except Exception as exc:
        _agy_logger.error(f"Classify failed: {exc}")
        raise


ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="classify",
    kwargs={
        "input_text": str,
        "categories": list,
        "instruction": str | None,
        "instruction_file": str | None,
        "augmentation": str | None,
    },
    callable=classify,
    description="Classify text into one of the given categories",
)
