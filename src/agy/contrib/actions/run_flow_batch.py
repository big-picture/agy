"""Contrib action: run a sub-flow for each element in a list."""

from __future__ import annotations

import asyncio
from typing import Any

from agy.action_type import ActionType


async def run_flow_batch(
    items: list[Any],
    element: str = "item",
    flow: str | None = None,
    node: str | None = None,
    mode: str = "sequential",
    on_error: str = "continue",
    **context_in: Any,
) -> dict[str, Any]:
    """Run a sub-flow once per list element and collect all results.

    Args:
        items: List to iterate over.
        element: Context key under which the current item is passed.
        flow: Path to a ``.flowsy`` file, or ``None`` to reuse the current flow.
        node: Optional start node name inside the target flow.
        mode: ``"sequential"`` (default) or ``"parallel"``.
        on_error: ``"continue"`` (default) or ``"fail_fast"`` (sequential only).
        **context_in: Additional key-value pairs merged into every sub-flow's
            ``context_in`` alongside the current element.
    """
    from agy.flow import Flow as FlowCls
    from agy.flow_executor import current_action_types_var, current_flow_var

    if flow is None and node is None:
        raise ValueError(
            "run_flow_batch requires at least one of 'flow' (path) or 'node' (start node)"
        )

    if flow is not None:
        target_flow = FlowCls.from_flowsy(flow)
    else:
        target_flow = current_flow_var.get()
        if target_flow is None:
            raise ValueError(
                "run_flow_batch(flow=None) requires a running flow context "
                "(missing current flow reference)"
            )

    action_types = current_action_types_var.get() or []
    mode_normalized = mode.strip().lower()
    on_error_normalized = on_error.strip().lower()

    async def _run_one(item: Any) -> dict[str, Any]:
        per_item_context = {element: item, **context_in}
        try:
            return await target_flow.run(
                context_in=per_item_context,
                action_types=action_types,
                node=node,
            )
        except Exception as exc:
            return {"success": False, "error_msg": str(exc)}

    results: list[dict[str, Any]] = []

    if mode_normalized == "parallel":
        tasks = [_run_one(item) for item in items]
        results = list(await asyncio.gather(*tasks, return_exceptions=False))
    else:
        for item in items:
            result = await _run_one(item)
            results.append(result)
            if on_error_normalized == "fail_fast" and not result.get("success", False):
                break

    return {
        "result": results,
        "context": {},
        "flow_control": None,
    }


ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="run_flow_batch",
    kwargs={},
    callable=run_flow_batch,
    description="Run a sub-flow for each element in a list (sequential or parallel)",
)
