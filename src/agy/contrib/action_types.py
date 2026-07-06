# agy/contrib/action_types.py
"""Standard contrib ActionType manifest for Agy."""

from agy.action_type import ActionType
from agy.contrib.actions.classify import ACTION_TYPE as CLASSIFY_ACTION_TYPE
from agy.contrib.actions.debug import ACTION_TYPE as SHOW_ACTION_TYPE
from agy.contrib.actions.extract import ACTION_TYPE as EXTRACT_ACTION_TYPE
from agy.contrib.actions.flow_control import ACTION_TYPE as END_ACTION_TYPE
from agy.contrib.actions.io import ACTION_TYPE as LOAD_FILES_ACTION_TYPE
from agy.contrib.actions.model_call import ACTION_TYPE as MODEL_CALL_ACTION_TYPE
from agy.contrib.actions.prompt import (
    GET_PROMPT_FROM_FILE_ACTION_TYPE,
    GET_PROMPT_FROM_STR_ACTION_TYPE,
)
from agy.contrib.actions.respond import ACTION_TYPE as RESPOND_ACTION_TYPE
from agy.contrib.actions.run_flow import ACTION_TYPE as RUN_FLOW_ACTION_TYPE
from agy.contrib.actions.run_flow_batch import ACTION_TYPE as RUN_FLOW_BATCH_ACTION_TYPE
from agy.contrib.actions.search_records import (
    SEARCH_EMAILS_ACTION_TYPE,
    SEARCH_FILES_ACTION_TYPE,
)
from agy.contrib.actions.set_model_call import ACTION_TYPE as SET_MODEL_CALL_ACTION_TYPE


def get_contrib_action_types() -> list[ActionType]:
    """Get all contrib ActionTypes."""
    return [
        MODEL_CALL_ACTION_TYPE,
        SET_MODEL_CALL_ACTION_TYPE,
        CLASSIFY_ACTION_TYPE,
        EXTRACT_ACTION_TYPE,
        RESPOND_ACTION_TYPE,
        LOAD_FILES_ACTION_TYPE,
        SHOW_ACTION_TYPE,
        END_ACTION_TYPE,
        GET_PROMPT_FROM_STR_ACTION_TYPE,
        GET_PROMPT_FROM_FILE_ACTION_TYPE,
        RUN_FLOW_ACTION_TYPE,
        RUN_FLOW_BATCH_ACTION_TYPE,
        SEARCH_EMAILS_ACTION_TYPE,
        SEARCH_FILES_ACTION_TYPE,
    ]
