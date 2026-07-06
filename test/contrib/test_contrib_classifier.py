"""Tests for contrib classifier."""

# test/contrib/test_contrib_classifier.py

import os
from typing import Any

import pytest

from agy.action_call import ActionCall
from agy.action_executor import ActionExecutor, ActionRegistry
from agy.action_type import ActionType
from agy.contrib.action_type_functions import classify
from agy.edge import Edge
from agy.flow import Flow
from agy.flow_executor import FlowExecutor
from agy.node import Node


def fake_llm_call_classifier(prompt: str, model: str = "gpt-5-mini") -> str:
    """Fake llm call classifier.

    Args:
        prompt: prompt.
        model: model.

    Returns:
        str: Operation result.
    """
    if "## Value schema" in prompt:
        return '{"extracted_field": "value", "confidence": 0.75}'

    if "## Classes" in prompt:
        classes_section = prompt.split("## Classes")[1]
        if "## Text to classify" in classes_section:
            classes_section = classes_section.split("## Text to classify")[0]

        lines = classes_section.split("\n")
        classes = []
        for line in lines:
            if line.strip().startswith("- "):
                class_name = line.strip()[2:].strip()
                if not class_name.startswith("**") and not class_name.startswith("*"):
                    classes.append(class_name)
        if classes:
            return f'{{"category": "{classes[0]}", "confidence": 0.95}}'

    return '{"category": "unknown", "confidence": 0.5}'


@pytest.mark.asyncio
async def test_classify_with_instruction():
    """Test that classify with instruction."""
    result = classify(
        input_text="This is a billing request",
        categories=["billing_request", "price_request", "support"],
        instruction="Classify the email type.",
        model_call=fake_llm_call_classifier,
    )
    assert result["result"] == "billing_request"
    assert result["context"]["confidence"] == 0.95


@pytest.mark.asyncio
async def test_classify_with_instruction_file():
    """Test that classify with instruction file."""
    instruction_file = "test_instruction.txt"
    with open(instruction_file, "w", encoding="utf-8") as file:
        file.write("Classify the following email into one of the given categories.")

    try:
        result = classify(
            input_text="I need help with pricing",
            categories=["billing_request", "price_request", "support"],
            instruction_file=instruction_file,
            model_call=fake_llm_call_classifier,
        )
        assert result["result"] in ["billing_request", "price_request", "support"]
        assert "context" in result
        assert "confidence" in result["context"]
    finally:
        if os.path.exists(instruction_file):
            os.unlink(instruction_file)


@pytest.mark.asyncio
async def test_classify_without_instruction():
    """Test that classify without instruction."""
    result = classify(
        input_text="Help needed",
        categories=["billing_request", "price_request", "support"],
        model_call=fake_llm_call_classifier,
    )
    assert result["result"] in ["billing_request", "price_request", "support"]
    assert "context" in result
    assert "confidence" in result["context"]


@pytest.mark.asyncio
async def test_classify_missing_model_call():
    """Test that classify() uses LLMCall singleton when model_call is not provided."""
    # Should work now because LLMCall is automatically initialized
    # Set fake provider for predictable results
    from agy.contrib.llm_call import LLMCall

    def fake_classify_call(prompt: str, **kwargs) -> str:
        """Fake classify call.

        Args:
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: Operation result.
        """
        return '{"category": "a", "confidence": 0.9}'

    llm = LLMCall()
    llm.set_model_call(callable=fake_classify_call)

    result = classify(input_text="Test", categories=["a", "b"])
    assert result["result"] == "a"
    assert result["context"]["confidence"] == 0.9


@pytest.mark.asyncio
async def test_classify_with_augmentation():
    """Test that classify with augmentation."""
    result = classify(
        input_text="This is a billing request",
        categories=["billing_request", "price_request"],
        augmentation="Customer history: VIP tier",
        model_call=fake_llm_call_classifier,
    )
    assert result["result"] == "billing_request"
    assert result["context"]["confidence"] == 0.95


@pytest.mark.asyncio
async def test_classify_action_type_execution():
    """Test that classify action type execution."""
    registry = ActionRegistry()
    # Set LLMCall singleton to use fake_llm_call_classifier
    from agy.contrib.llm_call import LLMCall

    LLMCall().set_model_call(callable=fake_llm_call_classifier)

    classifier_action_type = ActionType(
        object_name="global_function",
        method_name="classify",
        kwargs={"input_text": str, "categories": list, "instruction": str},
        callable=classify,
    )
    registry.register(classifier_action_type)
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[
            (
                "classify(input_text='This is a billing request', categories=['billing_request', 'price_request', 'support'], instruction='Classify the email.')",
                False,
            )
        ],
        kwargs={},
        output="category",
    )
    await executor.execute(action_call, context)

    assert context["category"] in ["billing_request", "price_request", "support"]
    assert context["confidence"] == 0.95
    assert context["success"] is True


@pytest.mark.asyncio
async def test_classify_in_flow():
    """Test that classify in flow."""
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[
            (
                "classify(input_text='I need help with my invoice', categories=['billing_request', 'price_request', 'support'], instruction='Classify the email type.')",
                False,
            )
        ],
        kwargs={},
        output="category",
    )

    node1 = Node(name="classify", control_type="deterministic", actions=[action_call])

    terminate = Node(name="end", control_type="deterministic", actions=None, edges=[])
    node1.edges = [Edge(target=terminate, condition="True")]

    flow = Flow(
        name="Classifier Flow",
        description="Test classifier in flow",
        nodes=[node1, terminate],
        context_in={},
    )

    # Set LLMCall singleton to use fake_llm_call_classifier
    from agy.contrib.llm_call import LLMCall

    llm = LLMCall()
    llm.set_model_call(callable=fake_llm_call_classifier)

    classifier_action_type = ActionType(
        object_name="global_function",
        method_name="classify",
        kwargs={
            "input_text": str,
            "categories": list,
            "instruction": str,
            "augmentation": str,
        },
        callable=classify,
    )

    executor = FlowExecutor(action_types=[classifier_action_type], context_in={})

    context = await executor.execute(flow)
    assert context["category"] in ["billing_request", "price_request", "support"]
    assert context["confidence"] == 0.95
    assert context["success"] is True


@pytest.mark.asyncio
async def test_classify_model_call_parameter_injection():
    """Test that classify model call parameter injection."""
    from agy.contrib.llm_call import LLMCall

    # Set LLMCall singleton to use fake_llm_call_classifier
    llm = LLMCall()
    llm.set_model_call(callable=fake_llm_call_classifier)

    registry = ActionRegistry()

    classifier_action_type = ActionType(
        object_name="global_function",
        method_name="classify",
        kwargs={"input_text": str, "categories": list},
        callable=classify,
    )
    registry.register(classifier_action_type)

    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    action_call = ActionCall(
        object_name="global_function",
        method_name="__eval__",
        args=[("classify(input_text='Test email', categories=['a', 'b', 'c'])", False)],
        kwargs={},
        output="result",
    )

    await executor.execute(action_call, context)

    assert context["result"] in ["a", "b", "c"]
    assert context["confidence"] == 0.95
    assert context["success"] is True


@pytest.mark.asyncio
async def test_classify_instruction_file_not_found():
    """Test that classify instruction file not found."""
    with pytest.raises(FileNotFoundError):
        classify(
            input_text="Test",
            categories=["a", "b"],
            instruction_file="nonexistent_file.txt",
            model_call=fake_llm_call_classifier,
        )


@pytest.mark.asyncio
async def test_classify_empty_categories():
    """Test that classify() raises error with empty categories list"""
    with pytest.raises(ValueError, match="at least one category"):
        classify(
            input_text="Test",
            categories=[],
            model_call=fake_llm_call_classifier,
        )


@pytest.mark.asyncio
async def test_classify_single_category():
    """Test that classify() raises error with only one category"""
    with pytest.raises(ValueError, match="at least 2 categories"):
        classify(
            input_text="Test",
            categories=["only_one"],
            model_call=fake_llm_call_classifier,
        )
