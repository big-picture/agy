"""Contrib extract action."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agy.action_type import ActionType
from agy.utils.file_readers import find_file_in_standard_dirs

_agy_logger = logging.getLogger("agy")


def _canonical_schema_type_key(type_hint: Any) -> str:
    """Map values_to_extract type entry to a lowercase schema name (str, float, int, list, dict)."""
    if isinstance(type_hint, str):
        return type_hint.strip().lower()
    if type_hint is str:
        return "str"
    if type_hint is float:
        return "float"
    if type_hint is int:
        return "int"
    if type_hint is list:
        return "list"
    if type_hint is dict:
        return "dict"
    name = getattr(type_hint, "__name__", None)
    if isinstance(name, str) and name:
        return name.lower()
    return "str"


def _missing_sentinel_for_schema_type(type_key: str) -> Any:
    if type_key == "str":
        return ""
    if type_key == "float":
        return 0.0
    if type_key == "int":
        return 0
    if type_key == "list":
        return []
    if type_key == "dict":
        return {}
    return ""


def _normalize_extracted_values(
    parsed: dict[str, Any],
    values_to_extract: dict[str, type[Any] | str],
) -> dict[str, Any]:
    """Build result dict with exactly schema keys; coerce JSON null / missing keys to type sentinels."""
    out: dict[str, Any] = {}
    for key, type_hint in values_to_extract.items():
        type_key = _canonical_schema_type_key(type_hint)
        raw_val = parsed.get(key)
        if raw_val is None:
            out[key] = _missing_sentinel_for_schema_type(type_key)
            continue
        if type_key == "float" and type(raw_val) in (int, float):
            out[key] = float(raw_val)
            continue
        if type_key == "int" and type(raw_val) in (int, float):
            out[key] = int(raw_val)
            continue
        if type_key == "str" and not isinstance(raw_val, str):
            out[key] = str(raw_val)
            continue
        out[key] = raw_val
    return out


def extract(
    input_text: str,
    values_to_extract: dict[str, type[Any] | str],
    instruction: str | None = None,
    instruction_file: str | None = None,
    augmentation: str | None = None,
    context: dict[str, Any] | None = None,
    model_call: Callable | None = None,
) -> dict[str, Any]:
    """Extract structured values from input text using an LLM.

    The returned ``result`` dict contains exactly the keys in ``values_to_extract``.
    JSON ``null`` or missing keys are coerced to type sentinels (``""``, ``0.0``,
    ``0``, ``[]``, ``{}``) so downstream code always sees stable types.
    """
    try:
        from agy.contrib.llm_call import LLMCall

        llm = LLMCall()
        call_func = model_call if model_call else llm.model_call

        template_path = (
            Path(__file__).parent.parent
            / "prompt_contents"
            / "generic_extract_instruction.md"
        )
        template = template_path.read_text(encoding="utf-8")

        if instruction:
            specific_instructions = instruction
        elif instruction_file:
            file_path = find_file_in_standard_dirs(instruction_file)
            specific_instructions = file_path.read_text(encoding="utf-8")
        else:
            specific_instructions = "Use just the generic extraction guidelines."

        schema_lines = []
        for key, type_hint in values_to_extract.items():
            if isinstance(type_hint, str):
                type_repr = type_hint
            elif hasattr(type_hint, "__name__"):
                type_repr = type_hint.__name__  # type: ignore[attr-defined]
            else:
                type_repr = str(type_hint)
            schema_lines.append(f'  "{key}": {type_repr},\n')
        schema_str = "".join(schema_lines)

        augmentation_text = augmentation if augmentation else "None provided"
        prompt = template.format(
            specific_instructions=specific_instructions,
            augmentation=augmentation_text,
            value_schema=schema_str,
            input_text=input_text,
        )

        _agy_logger.debug(f"Extract prompt:\n{prompt}")
        result = call_func(prompt)
        _agy_logger.debug(f"Extract model response:\n{result}")

        result_clean = result.strip()
        if result_clean.startswith("```"):
            lines = result_clean.split("\n")
            result_clean = "\n".join(lines[1:-1]) if len(lines) > 2 else result_clean

        try:
            parsed = json.loads(result_clean)
        except json.JSONDecodeError as exc:
            _agy_logger.debug(
                f"Extract JSON parsing failed. Raw response: {result_clean}"
            )
            raise ValueError(f"Failed to parse JSON response: {exc}")

        if not isinstance(parsed, dict):
            raise ValueError("Extract must return a JSON object")
        if "confidence" not in parsed:
            raise ValueError("Extract response must contain 'confidence'")
        if parsed["confidence"] is None:
            raise ValueError("Extract response must contain non-null 'confidence'")

        confidence = float(parsed["confidence"])
        if not (0 <= confidence <= 1):
            raise ValueError(f"Confidence must be between 0 and 1, got {confidence}")

        extracted_values = _normalize_extracted_values(parsed, values_to_extract)
        _agy_logger.debug(
            "Extract normalized result keys: %s", list(extracted_values.keys())
        )

        return {"result": extracted_values, "context": {"confidence": confidence}}
    except Exception as exc:  # pylint: disable=broad-except
        _agy_logger.error(f"Extract failed: {exc}")
        raise


ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="extract",
    kwargs={
        "input_text": str,
        "values_to_extract": dict,
        "instruction": str | None,
        "instruction_file": str | None,
        "augmentation": str | None,
    },
    callable=extract,
    description="Extract structured values from text using an LLM",
)
