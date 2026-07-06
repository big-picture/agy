"""Contrib action: run a sub-flow from within a running flow."""

from __future__ import annotations

from typing import Any

from agy.action_type import ActionType


async def run_flow(
    flow: str | None = None,
    node: str | None = None,
    **context_in: Any,
) -> dict[str, Any]:
    """Call a sub-flow and return its final context.

    Args:
        flow: Path to a ``.flowsy`` file, or ``None`` to reuse the current flow.
        node: Optional start node name inside the target flow.
        **context_in: Key-value pairs passed as ``context_in`` to the sub-flow.
    """
    from agy.flow import Flow as FlowCls
    from agy.flow_executor import current_action_types_var, current_flow_var

    if flow is None and node is None:
        raise ValueError(
            "run_flow requires at least one of 'flow' (path) or 'node' (start node)"
        )

    if flow is not None:
        target_flow = FlowCls.from_flowsy(flow)
    else:
        target_flow = current_flow_var.get()
        if target_flow is None:
            raise ValueError(
                "run_flow(flow=None) requires a running flow context "
                "(missing current flow reference)"
            )

    action_types = current_action_types_var.get() or []

    sub_context = await target_flow.run(
        context_in=context_in,
        action_types=action_types,
        node=node,
    )

    return {
        "result": sub_context,
        "context": {},
        "flow_control": None,
    }


ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="run_flow",
    kwargs={},
    callable=run_flow,
    description="Call a sub-flow and return its final context",
)
