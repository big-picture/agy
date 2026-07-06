"""Contrib prompt formatting helpers."""

from __future__ import annotations

from agy.action_type import ActionType
from agy.utils.file_readers import find_file_in_standard_dirs


def get_prompt_from_str(template: str, **kwargs) -> str:
    """Format a template string using Python's .format() method."""
    try:
        return template.format(**kwargs)
    except KeyError as exc:
        missing_key = str(exc).strip("'")
        raise KeyError(f"Template key '{missing_key}' not provided in kwargs") from exc


def get_prompt_from_file(file_path: str, **kwargs) -> str:
    """Load a template file and format it using get_prompt_from_str."""
    path = find_file_in_standard_dirs(file_path)
    template = path.read_text(encoding="utf-8")
    return get_prompt_from_str(template, **kwargs)


GET_PROMPT_FROM_STR_ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="get_prompt_from_str",
    kwargs={"template": str},
    callable=get_prompt_from_str,
    description="Format a template string with provided kwargs using Python .format()",
)

GET_PROMPT_FROM_FILE_ACTION_TYPE = ActionType(
    object_name="global_function",
    method_name="get_prompt_from_file",
    kwargs={"file_path": str},
    callable=get_prompt_from_file,
    description="Load a template file and format it with provided kwargs",
)
