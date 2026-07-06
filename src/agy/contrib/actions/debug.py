"""Contrib debug helpers."""

from __future__ import annotations

import logging

from agy.action_type import ActionType

_agy_logger = logging.getLogger("agy")


def show(*messages: str) -> None:
    """Print debug information to stdout and log."""
    parts = [str(part) for part in messages]
    text = " ".join(parts)
    print(text)
    _agy_logger.info(f"[agy.show] {text}")


ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="show",
    args=[str],
    kwargs={},
    callable=show,
    description="Prints debug information to stdout and INFO log",
)
