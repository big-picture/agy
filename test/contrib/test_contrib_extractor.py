"""Tests for contrib extractor."""

# test/test_extractor.py

import asyncio
import json
from typing import Any

import pytest

from agy.action_call import ActionCall
from agy.action_executor import ActionExecutor, ActionRegistry
from agy.action_type import ActionType
from agy.contrib.action_type_functions import extract


def fake_extractor_llm(prompt: str, model: str = "gpt-5-mini") -> str:
    # Simple heuristic: return a JSON echoing the schema with dummy values
    """Fake extractor llm.

    Args:
        prompt: prompt.
        model: model.

    Returns:
        str: Operation result.
    """
    payload = {"product_name": "Widget", "price": 19.99, "confidence": 0.9}
    return json.dumps(payload)


def fake_extractor_llm_schema(prompt: str, model: str = "gpt-5-mini") -> str:
    """Fake extractor llm schema.

    Args:
        prompt: prompt.
        model: model.

    Returns:
        str: Operation result.
    """
    payload = {
        "names": ["Alice", "Bob"],
        "colors": {"red": "A1", "blue": "B2"},
        "confidence": 0.8,
    }
    return json.dumps(payload)


@pytest.mark.parametrize(
    "values_to_extract, llm",
    [
        ({"product_name": str, "price": float}, fake_extractor_llm),
        ({"names": list, "colors": dict}, fake_extractor_llm_schema),
    ],
)
def test_extract_basic(values_to_extract, llm):
    """Test that extract basic.

    Args:
        values_to_extract: values to extract.
        llm: llm.
    """
    result = extract(
        input_text="Sample text",
        values_to_extract=values_to_extract,
        augmentation="Additional hints",
        model_call=llm,
    )

    assert "context" in result
    assert "confidence" in result["context"]
    assert 0 <= result["context"]["confidence"] <= 1
    assert "result" in result
    assert isinstance(result["result"], dict)
    for key in values_to_extract:
        assert key in result["result"]


def test_extract_missing_model_call():
    """Test that extract() uses LLMCall singleton when model_call is not provided."""
    # Should work now because LLMCall is automatically initialized
    from agy.contrib.llm_call import LLMCall

    def fake_extract_call(prompt: str, **kwargs) -> str:
        """Fake extract call.

        Args:
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: Operation result.
        """
        return '{"value": "extracted", "confidence": 0.95}'

    llm = LLMCall()
    llm.set_model_call(callable=fake_extract_call)

    result = extract(input_text="Sample", values_to_extract={"value": str})
    assert result["result"]["value"] == "extracted"
    assert result["context"]["confidence"] == 0.95


def test_extract_normalizes_json_null_for_schema_keys():
    """JSON null and missing values become type-stable sentinels."""

    def llm(prompt: str) -> str:
        return json.dumps({"product_name": None, "price": None, "confidence": 0.85})

    result = extract(
        input_text="body",
        values_to_extract={"product_name": str, "price": float},
        model_call=llm,
    )
    assert result["result"]["product_name"] == ""
    assert result["result"]["price"] == 0.0
    assert result["context"]["confidence"] == 0.85


def test_extract_normalizes_missing_schema_keys():
    def llm(prompt: str) -> str:
        return json.dumps({"confidence": 0.9})

    result = extract(
        input_text="body",
        values_to_extract={"product_name": str, "price": float},
        model_call=llm,
    )
    assert result["result"]["product_name"] == ""
    assert result["result"]["price"] == 0.0


def test_extract_coerces_int_json_number_to_float_field():
    def llm(prompt: str) -> str:
        return json.dumps({"product_name": "Widget", "price": 19, "confidence": 0.9})

    result = extract(
        input_text="body",
        values_to_extract={"product_name": str, "price": float},
        model_call=llm,
    )
    assert result["result"]["price"] == 19.0


def test_extract_normalizes_null_list_and_dict():
    def llm(prompt: str) -> str:
        return json.dumps({"names": None, "colors": None, "confidence": 0.5})

    result = extract(
        input_text="body",
        values_to_extract={"names": list, "colors": dict},
        model_call=llm,
    )
    assert result["result"]["names"] == []
    assert result["result"]["colors"] == {}


def test_extract_result_contains_only_schema_keys():
    def llm(prompt: str) -> str:
        return json.dumps(
            {"product_name": "x", "price": 1.0, "noise": 123, "confidence": 0.9}
        )

    result = extract(
        input_text="body",
        values_to_extract={"product_name": str, "price": float},
        model_call=llm,
    )
    assert set(result["result"].keys()) == {"product_name", "price"}
    assert "noise" not in result["result"]


def test_extract_invalid_json_response():
    """Test that extract invalid json response."""

    def bad_llm(prompt: str, model: str = "gpt-5-mini") -> str:
        """Bad llm.

        Args:
            prompt: prompt.
            model: model.

        Returns:
            str: Operation result.
        """
        return "not-json"

    with pytest.raises(ValueError, match="Failed to parse JSON response"):
        extract(
            input_text="Sample", values_to_extract={"value": str}, model_call=bad_llm
        )


def test_extract_action_type_execution():
    """Test that extract action type execution."""
    from agy.contrib.llm_call import LLMCall

    async def _run() -> None:
        llm = LLMCall()
        llm.set_model_call(callable=fake_extractor_llm)

        registry = ActionRegistry()

        extractor_action_type = ActionType(
            object_name="global_function",
            method_name="extract",
            kwargs={"input_text": str, "values_to_extract": dict, "augmentation": str},
            callable=extract,
        )
        registry.register(extractor_action_type)
        executor = ActionExecutor(registry)

        action_call = ActionCall(
            object_name="global_function",
            method_name="__eval__",
            args=[
                (
                    "extract(input_text='Order details', values_to_extract={'product_name': 'str', 'price': 'float'}, augmentation='Priority customer')",
                    False,
                )
            ],
            kwargs={},
            output="extracted",
        )

        context: dict[str, Any] = {}
        await executor.execute(action_call, context)

        assert context["extracted"]["product_name"] == "Widget"
        assert context["confidence"] == 0.9
        assert context["success"] is True

    asyncio.run(_run())
