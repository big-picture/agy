"""Contrib action to configure active model call."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agy.action_type import ActionType


def set_model_call(
    provider: str | None = None,
    model: str | None = None,
    callable: Callable | None = None,
    context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Set the current model_call for all subsequent LLM actions."""
    from agy.contrib.llm_call import LLMCall

    legacy_params = kwargs.pop("params", None)
    if legacy_params is not None and not isinstance(legacy_params, dict):
        raise TypeError("set_model_call(params=...) must be a dict when provided")

    merged_params = {
        **(legacy_params or {}),
        **kwargs,
    }

    llm = LLMCall()
    llm.set_model_call(
        provider=provider,
        model=model,
        params=merged_params if merged_params else None,
        callable=callable,
    )
    return {"success": True}


ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="set_model_call",
    kwargs={
        "provider": str | None,
        "model": str | None,
        "callable": Callable | None,
    },
    callable=set_model_call,
    description=(
        "Set/override model_call for subsequent LLM actions; accepts provider/model/callable "
        "plus arbitrary model params (for example temperature, max_tokens)"
    ),
)
