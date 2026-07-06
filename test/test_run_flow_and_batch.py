"""Tests for run_flow and run_flow_batch contrib actions."""

from __future__ import annotations

import asyncio
import tempfile
import time
from typing import Any

import pytest

from agy.action_type import ActionType
from agy.flow import Flow

SIMPLE_FLOW = """\
name: Simple Sub-Flow
context_in:
  x: str

nodes:
  start:
    edges:
      - True: end(success=True, result=x)
"""

TWO_CHAINS_FLOW = """\
name: Two Chains
context_in:
  value: str

nodes:
  chain_a:
    edges:
      - True: end(success=True, result="from_a")

  chain_b:
    edges:
      - True: end(success=True, result="from_b")
"""


@pytest.mark.asyncio
async def test_run_flow_with_external_flowsy_file() -> None:
    """run_flow loads an external .flowsy and returns its final context."""
    with tempfile.NamedTemporaryFile(suffix=".flowsy", mode="w", delete=False) as f:
        f.write(SIMPLE_FLOW)
        f.flush()
        flowsy_path = f.name

    # Build a parent flow that calls run_flow(flow=<path>, x="hello")
    parent_flowsy = f"""\
name: Parent Flow

nodes:
  call_sub:
    actions:
      - sub = run_flow(flow="{flowsy_path}", x="hello")
    edges:
      - True: end(success=True, result=sub)
"""
    flow = Flow.from_flowsy_string(parent_flowsy)
    ctx = await flow.run()

    assert ctx["success"] is True
    sub = ctx["result"]
    assert isinstance(sub, dict)
    assert sub["success"] is True
    assert sub["result"] == "hello"


@pytest.mark.asyncio
async def test_run_flow_with_node_same_flow() -> None:
    """run_flow(node=...) reuses current flow and starts at the given node."""
    parent_flowsy = """\
name: Self-Referencing Flow
context_in:
  value: str

nodes:
  entry:
    actions:
      - sub = run_flow(node="chain_b", value="test")
    edges:
      - True: end(success=True, result=sub)

  chain_b:
    edges:
      - True: end(success=True, result="from_b")
"""
    flow = Flow.from_flowsy_string(parent_flowsy)
    ctx = await flow.run(context_in={"value": "ignored"})

    assert ctx["success"] is True
    sub = ctx["result"]
    assert sub["result"] == "from_b"


@pytest.mark.asyncio
async def test_run_flow_raises_when_both_none() -> None:
    """run_flow(flow=None, node=None) sets success=False with a clear error."""
    parent_flowsy = """\
name: Bad Call

nodes:
  start:
    actions:
      - sub = run_flow()
    edges:
      - sub: end(success=True)
      - True: end(success=False, error_msg=error_msg)
"""
    flow = Flow.from_flowsy_string(parent_flowsy)
    ctx = await flow.run()
    assert ctx["success"] is False
    assert "at least one" in ctx.get("error_msg", "")


@pytest.mark.asyncio
async def test_run_flow_batch_sequential() -> None:
    """run_flow_batch processes items sequentially and returns ordered results."""
    with tempfile.NamedTemporaryFile(suffix=".flowsy", mode="w", delete=False) as f:
        f.write(SIMPLE_FLOW)
        f.flush()
        flowsy_path = f.name

    parent_flowsy = f"""\
name: Batch Parent

nodes:
  batch:
    actions:
      - items = ["a", "b", "c"]
      - results = run_flow_batch(items, element="x", flow="{flowsy_path}")
    edges:
      - True: end(success=True, result=results)
"""
    flow = Flow.from_flowsy_string(parent_flowsy)
    ctx = await flow.run()

    assert ctx["success"] is True
    results = ctx["result"]
    assert len(results) == 3
    assert results[0]["result"] == "a"
    assert results[1]["result"] == "b"
    assert results[2]["result"] == "c"


@pytest.mark.asyncio
async def test_run_flow_batch_parallel() -> None:
    """run_flow_batch with mode=parallel returns results for all items."""
    with tempfile.NamedTemporaryFile(suffix=".flowsy", mode="w", delete=False) as f:
        f.write(SIMPLE_FLOW)
        f.flush()
        flowsy_path = f.name

    parent_flowsy = f"""\
name: Parallel Batch

nodes:
  batch:
    actions:
      - items = ["x", "y", "z"]
      - results = run_flow_batch(items, element="x", flow="{flowsy_path}", mode="parallel")
    edges:
      - True: end(success=True, result=results)
"""
    flow = Flow.from_flowsy_string(parent_flowsy)
    ctx = await flow.run()

    assert ctx["success"] is True
    results = ctx["result"]
    assert len(results) == 3
    result_values = sorted(r["result"] for r in results)
    assert result_values == ["x", "y", "z"]


@pytest.mark.asyncio
async def test_run_flow_batch_fail_fast() -> None:
    """run_flow_batch with on_error=fail_fast stops at first failure."""
    fail_flow = """\
name: Maybe Fail
context_in:
  x: str

nodes:
  check:
    actions:
      - ok = x != "bad"
    edges:
      - ok: end(success=True, result=x)
      - True: end(success=False, error_msg="bad item")
"""
    with tempfile.NamedTemporaryFile(suffix=".flowsy", mode="w", delete=False) as f:
        f.write(fail_flow)
        f.flush()
        flowsy_path = f.name

    parent_flowsy = f"""\
name: Fail Fast Batch

nodes:
  batch:
    actions:
      - items = ["good", "bad", "also_good"]
      - results = run_flow_batch(items, element="x", flow="{flowsy_path}", on_error="fail_fast")
    edges:
      - True: end(success=True, result=results)
"""
    flow = Flow.from_flowsy_string(parent_flowsy)
    ctx = await flow.run()

    results = ctx["result"]
    assert len(results) == 2
    assert results[0]["success"] is True
    assert results[1]["success"] is False


@pytest.mark.asyncio
async def test_run_flow_batch_continue_on_error() -> None:
    """run_flow_batch with on_error=continue processes all items despite failures."""
    fail_flow = """\
name: Maybe Fail
context_in:
  x: str

nodes:
  check:
    actions:
      - ok = x != "bad"
    edges:
      - ok: end(success=True, result=x)
      - True: end(success=False, error_msg="bad item")
"""
    with tempfile.NamedTemporaryFile(suffix=".flowsy", mode="w", delete=False) as f:
        f.write(fail_flow)
        f.flush()
        flowsy_path = f.name

    parent_flowsy = f"""\
name: Continue Batch

nodes:
  batch:
    actions:
      - items = ["good", "bad", "also_good"]
      - results = run_flow_batch(items, element="x", flow="{flowsy_path}", on_error="continue")
    edges:
      - True: end(success=True, result=results)
"""
    flow = Flow.from_flowsy_string(parent_flowsy)
    ctx = await flow.run()

    results = ctx["result"]
    assert len(results) == 3
    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert results[2]["success"] is True


@pytest.mark.asyncio
async def test_run_flow_batch_empty_list() -> None:
    """run_flow_batch with empty list returns empty results."""
    with tempfile.NamedTemporaryFile(suffix=".flowsy", mode="w", delete=False) as f:
        f.write(SIMPLE_FLOW)
        f.flush()
        flowsy_path = f.name

    parent_flowsy = f"""\
name: Empty Batch

nodes:
  batch:
    actions:
      - items = []
      - results = run_flow_batch(items, element="x", flow="{flowsy_path}")
    edges:
      - True: end(success=True, result=results)
"""
    flow = Flow.from_flowsy_string(parent_flowsy)
    ctx = await flow.run()

    assert ctx["success"] is True
    assert ctx["result"] == []


@pytest.mark.asyncio
async def test_run_flow_batch_with_node_same_flow() -> None:
    """run_flow_batch with node= iterates over items using nodes in the same flow."""
    parent_flowsy = """\
name: Batch Same Flow
context_in:
  x: str

nodes:
  entry:
    actions:
      - items = ["alpha", "beta"]
      - results = run_flow_batch(items, element="x", node="process")
    edges:
      - True: end(success=True, result=results)

  process:
    edges:
      - True: end(success=True, result=x)
"""
    flow = Flow.from_flowsy_string(parent_flowsy)
    ctx = await flow.run(context_in={"x": "unused"})

    assert ctx["success"] is True
    results = ctx["result"]
    assert len(results) == 2
    assert results[0]["result"] == "alpha"
    assert results[1]["result"] == "beta"


@pytest.mark.asyncio
async def test_run_flow_batch_context_isolation() -> None:
    """Each sub-flow gets its own context; no bleed between iterations or to parent."""
    # Sub-flow writes a marker derived from input into context key "marker".
    sub_flow = """\
name: Marker Flow
context_in:
  val: str

nodes:
  mark:
    actions:
      - marker = "marked_" + val
    edges:
      - True: end(success=True, result=marker)
"""
    with tempfile.NamedTemporaryFile(suffix=".flowsy", mode="w", delete=False) as f:
        f.write(sub_flow)
        f.flush()
        flowsy_path = f.name

    parent_flowsy = f"""\
name: Isolation Test

nodes:
  batch:
    actions:
      - items = ["aaa", "bbb", "ccc"]
      - results = run_flow_batch(items, element="val", flow="{flowsy_path}")
    edges:
      - True: end(success=True, result=results)
"""
    flow = Flow.from_flowsy_string(parent_flowsy)
    ctx = await flow.run()

    assert ctx["success"] is True
    results = ctx["result"]

    # Each sub-flow saw only its own input — no cross-contamination.
    assert results[0]["result"] == "marked_aaa"
    assert results[1]["result"] == "marked_bbb"
    assert results[2]["result"] == "marked_ccc"

    # Parent context must not contain "marker" — sub-flow keys stay isolated.
    assert "marker" not in ctx
    assert "val" not in ctx


async def _async_sleep(seconds: float = 1.0) -> dict[str, Any]:
    """Custom action that sleeps asynchronously and returns elapsed time."""
    t0 = time.monotonic()
    await asyncio.sleep(seconds)
    return {"result": round(time.monotonic() - t0, 2), "context": {}, "flow_control": None}


SLEEP_ACTION = ActionType(
    object_name="global_function",
    method_name="async_sleep",
    kwargs={"seconds": float},
    callable=_async_sleep,
    description="Async sleep for testing parallelism",
)


@pytest.mark.asyncio
async def test_run_flow_batch_parallel_is_concurrent() -> None:
    """5 sub-flows each sleeping 1s in parallel must finish in ≈1s, not 5s."""
    sleep_flow = """\
name: Sleep Flow
context_in:
  idx: int

nodes:
  wait:
    actions:
      - elapsed = async_sleep(1.0)
    edges:
      - True: end(success=True, result=idx)
"""
    with tempfile.NamedTemporaryFile(suffix=".flowsy", mode="w", delete=False) as f:
        f.write(sleep_flow)
        f.flush()
        flowsy_path = f.name

    parent_flowsy = f"""\
name: Parallel Timing Test

nodes:
  batch:
    actions:
      - items = [1, 2, 3, 4, 5]
      - results = run_flow_batch(items, element="idx", flow="{flowsy_path}", mode="parallel")
    edges:
      - True: end(success=True, result=results)
"""
    flow = Flow.from_flowsy_string(parent_flowsy)

    t0 = time.monotonic()
    ctx = await flow.run(action_types=[SLEEP_ACTION])
    wall_time = time.monotonic() - t0

    assert ctx["success"] is True
    results = ctx["result"]
    assert len(results) == 5
    assert all(r["success"] for r in results)

    # Parallel: 5 × 1s sleep should complete in well under 3s.
    # Sequential would take ≥5s.
    assert wall_time < 3.0, f"Expected <3s for parallel execution, got {wall_time:.2f}s"
