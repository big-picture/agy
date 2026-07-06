"""Compatibility facade for contrib action functions.

This module re-exports action functions from `agy.contrib.actions.*` so existing
imports keep working while contrib logic is modularized.
"""

from agy.contrib.actions.classify import classify
from agy.contrib.actions.debug import show
from agy.contrib.actions.extract import extract
from agy.contrib.actions.flow_control import FlowTerminationError, end
from agy.contrib.actions.io import load_files_text
from agy.contrib.actions.model_call import model_call
from agy.contrib.actions.prompt import get_prompt_from_file, get_prompt_from_str
from agy.contrib.actions.respond import respond
from agy.contrib.actions.set_model_call import set_model_call

__all__ = [
    "set_model_call",
    "model_call",
    "FlowTerminationError",
    "show",
    "load_files_text",
    "respond",
    "extract",
    "classify",
    "get_prompt_from_str",
    "get_prompt_from_file",
    "end",
]
