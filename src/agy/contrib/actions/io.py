"""Contrib I/O helpers."""

from __future__ import annotations

from agy.action_type import ActionType
from agy.utils.file_readers import find_file_in_standard_dirs, load_files_as_text


def load_files_text(*file_paths: str) -> str:
    """Load one or more files and return their concatenated text content."""
    if not file_paths:
        raise ValueError("At least one file path must be provided")

    paths = [find_file_in_standard_dirs(path) for path in file_paths]
    combined_text = load_files_as_text(paths)
    return combined_text


ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="load_files_text",
    args=[str],
    callable=load_files_text,
    description="Load one or more files and return their concatenated text",
)
