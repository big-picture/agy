"""Contrib action for direct LLM calls."""

from __future__ import annotations

import json
from typing import Any, cast

from agy.action_type import ActionType


def model_call(
    prompt: str,
    output: str = "str",
    **kwargs: Any,
) -> str | dict[str, Any] | list[Any]:
    """Call LLM with prompt and optional parameters."""
    from agy.contrib.llm_call import LLMCall

    llm = LLMCall()
    result = cast(str, llm.model_call(prompt, **kwargs))

    if output == "json":
        result_clean = result.strip()
        if result_clean.startswith("```"):
            lines = result_clean.split("\n")
            result_clean = "\n".join(lines[1:-1]) if len(lines) > 2 else result_clean
        parsed = json.loads(result_clean)
        return cast(dict[str, Any] | list[Any], parsed)

    return result


ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="model_call",
    kwargs={
        "prompt": str,
        "output": str,
    },
    callable=model_call,
    description="Call LLM with prompt and optional parameters",
)
