"""Tests for action executor."""

# test/test_action_executor.py

from typing import Any

import pytest

from agy.action_executor import ActionExecutor, ActionRegistry
from agy.action_type import ActionType
from agy.ast_parser import parse_action_with_ast


def test_registry_register_and_get_action_type():
    """Test registering and getting action types"""
    registry = ActionRegistry()

    def test_func(x: int, y: int) -> int:
        """Test that func.

        Args:
            x: x.
            y: y.

        Returns:
            int: Operation result.
        """
        return x + y

    action_type = ActionType(
        object_name="global_function", method_name="add", callable=test_func
    )
    registry.register(action_type)
    retrieved = registry.get_action_type("add")
    assert retrieved == action_type


@pytest.mark.asyncio
async def test_executor_execute_registered_function():
    """Test executing a registered function"""
    from agy.ast_parser import parse_action_with_ast

    registry = ActionRegistry()

    def add(a: int, b: int) -> int:
        """Add.

        Args:
            a: a.
            b: b.

        Returns:
            int: Operation result.
        """
        return a + b

    action_type = ActionType(
        object_name="global_function", method_name="add", callable=add
    )
    registry.register(action_type)
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast("sum = add(5, 3)")
    await executor.execute(action_call, context)

    assert context["sum"] == 8
    assert context["success"] is True
    assert context["error_msg"] == ""


@pytest.mark.asyncio
async def test_executor_execute_flow_specific_function():
    """Test executing a flow-specific function"""
    registry = ActionRegistry()

    def process_email(subject: str) -> str:
        """Process email.

        Args:
            subject: subject.

        Returns:
            str: Operation result.
        """
        return f"processed: {subject}"

    action_type = ActionType(
        object_name="global_function",
        method_name="process_email",
        callable=process_email,
    )
    registry.register(action_type)
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast("result = process_email(subject='Test')")
    await executor.execute(action_call, context)

    assert context["result"] == "processed: Test"
    assert context["success"] is True


@pytest.mark.asyncio
async def test_executor_execute_context_object_method():
    """Test executing a context object method"""

    class Email:
        """Represents a Email object."""

        def __init__(self, address: str):
            """Initialize the object.

            Args:
                address: address.
            """
            self.address = address
            self.sent = False

        def send(self, subject: str, body: str) -> dict:
            """Send.

            Args:
                subject: subject.
                body: body.

            Returns:
                dict: Operation result.
            """
            self.sent = True
            return {"status": "sent", "to": self.address}

    registry = ActionRegistry()
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {"email": Email("test@example.com")}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast(
        "send_result = email.send(subject='Hello', body='World')"
    )
    await executor.execute(action_call, context)

    assert context["email"].sent is True
    assert context["send_result"]["status"] == "sent"


@pytest.mark.asyncio
async def test_executor_execute_complex_assignment_attribute():
    """Test executing complex assignment to object attribute"""

    class Invoice:
        """Represents a Invoice object."""

        def __init__(self):
            """Initialize the object."""
            self.invoice_number: str | None = None
            self.amount: float | None = None

    registry = ActionRegistry()
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {
        "invoice": Invoice(),
        "invoice_data": {"invoice_number": "INV-001", "amount": 1000.0},
    }

    # Test attribute assignment: invoice.invoice_number = invoice_data["invoice_number"]
    action_call = parse_action_with_ast(
        'invoice.invoice_number = invoice_data["invoice_number"]'
    )
    await executor.execute(action_call, context)

    assert context["invoice"].invoice_number == "INV-001"
    assert context["success"] is True
    assert context["result"] is None  # Complex assignments don't set result

    # Test another attribute assignment
    action_call2 = parse_action_with_ast('invoice.amount = invoice_data["amount"]')
    await executor.execute(action_call2, context)

    assert context["invoice"].amount == 1000.0


@pytest.mark.asyncio
async def test_executor_execute_complex_assignment_subscript():
    """Test executing complex assignment to dict subscript"""

    registry = ActionRegistry()
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {"data": {}, "value": "test"}

    # Test subscript assignment: data["key"] = value
    action_call = parse_action_with_ast('data["key"] = value')
    await executor.execute(action_call, context)

    assert context["data"]["key"] == "test"
    assert context["success"] is True


@pytest.mark.asyncio
async def test_executor_execute_complex_assignment_nested():
    """Test executing nested complex assignment"""

    registry = ActionRegistry()
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {"obj": [{"key": None}], "value": "test"}

    # Test nested assignment: obj[0]["key"] = value
    action_call = parse_action_with_ast('obj[0]["key"] = value')
    await executor.execute(action_call, context)

    assert context["obj"][0]["key"] == "test"
    assert context["success"] is True


@pytest.mark.asyncio
async def test_executor_error_unknown_function():
    """Test error handling for unknown functions"""
    registry = ActionRegistry()
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast("result = unknown_func()")
    await executor.execute(action_call, context)

    assert context["success"] is False
    assert "unknown_func" in context["error_msg"]


@pytest.mark.asyncio
async def test_executor_error_unknown_method():
    """Test error handling for unknown methods on context objects"""
    registry = ActionRegistry()
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {"test_obj": object()}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast("result = test_obj.unknown_method()")
    await executor.execute(action_call, context)

    assert context["success"] is False
    assert (
        "has no attribute" in context["error_msg"]
        or "has no method" in context["error_msg"]
    )


@pytest.mark.asyncio
async def test_executor_default_output():
    """Test that default output is 'result'"""
    registry = ActionRegistry()

    def test_func() -> str:
        """Test that func.

        Returns:
            str: Operation result.
        """
        return "test"

    action_type = ActionType(
        object_name="global_function", method_name="test", callable=test_func
    )
    registry.register(action_type)
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast("result = test()")
    await executor.execute(action_call, context)

    assert "result" in context
    assert context["result"] == "test"
    assert context["success"] is True


@pytest.mark.asyncio
async def test_executor_execute_async_registered_function():
    """Test executing an async registered function"""
    import asyncio

    async def async_add(a: int, b: int) -> int:
        """Async add.

        Args:
            a: a.
            b: b.

        Returns:
            int: Operation result.
        """
        await asyncio.sleep(0.01)  # Simulate async work
        return a + b

    registry = ActionRegistry()
    action_type = ActionType(
        object_name="global_function", method_name="async_add", callable=async_add
    )
    registry.register(action_type)
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast("sum = async_add(5, 3)")
    await executor.execute(action_call, context)

    assert context["sum"] == 8
    assert context["success"] is True
    assert context["error_msg"] == ""


@pytest.mark.asyncio
async def test_executor_execute_async_context_object_method():
    """Test executing an async context object method"""
    import asyncio

    class AsyncEmail:
        """Represents a AsyncEmail object."""

        def __init__(self, address: str):
            """Initialize the object.

            Args:
                address: address.
            """
            self.address = address
            self.sent = False

        async def send(self, subject: str, body: str) -> dict:
            """Send.

            Args:
                subject: subject.
                body: body.

            Returns:
                dict: Operation result.
            """
            await asyncio.sleep(0.01)  # Simulate async work
            self.sent = True
            return {"status": "sent", "to": self.address}

    registry = ActionRegistry()
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {"email": AsyncEmail("test@example.com")}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast(
        "send_result = email.send(subject='Hello', body='World')"
    )
    await executor.execute(action_call, context)

    assert context["email"].sent is True
    assert context["send_result"]["status"] == "sent"
    assert context["success"] is True
    assert context["email"].address == "test@example.com"


@pytest.mark.asyncio
async def test_executor_mixed_sync_async():
    """Test that sync and async actions can be used together"""
    import asyncio

    def sync_func(x: int) -> int:
        """Sync func.

        Args:
            x: x.

        Returns:
            int: Operation result.
        """
        return x * 2

    async def async_func(x: int) -> int:
        """Async func.

        Args:
            x: x.

        Returns:
            int: Operation result.
        """
        await asyncio.sleep(0.01)
        return x * 3

    registry = ActionRegistry()
    sync_action_type = ActionType(
        object_name="global_function", method_name="sync", callable=sync_func
    )
    async_action_type = ActionType(
        object_name="global_function", method_name="async_func", callable=async_func
    )
    registry.register(sync_action_type)
    registry.register(async_action_type)
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call1 = parse_action_with_ast("result = sync(5)")
    await executor.execute(action_call1, context)
    assert context["result"] == 10
    assert context["success"] is True

    context2: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call2 = parse_action_with_ast("result = async_func(5)")
    await executor.execute(action_call2, context2)
    assert context2["result"] == 15
    assert context2["success"] is True


@pytest.mark.asyncio
async def test_executor_positional_only_arguments():
    """Test execution with methods that have positional-only arguments"""

    def positional_func(x: int, y: int, /) -> int:
        """Function with positional-only arguments"""
        return x + y

    registry = ActionRegistry()
    action_type = ActionType(
        object_name="global_function", method_name="pos", callable=positional_func
    )
    registry.register(action_type)
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast("result = pos(10, 5)")
    await executor.execute(action_call, context)
    assert context["result"] == 15
    assert context["success"] is True


@pytest.mark.asyncio
async def test_executor_keyword_only_arguments():
    """Test execution with methods that have keyword-only arguments"""

    def keyword_func(*, x: int, y: int) -> int:
        """Function with keyword-only arguments"""
        return x * y

    registry = ActionRegistry()
    action_type = ActionType(
        object_name="global_function", method_name="kw", callable=keyword_func
    )
    registry.register(action_type)
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast("result = kw(x=4, y=3)")
    await executor.execute(action_call, context)
    assert context["result"] == 12
    assert context["success"] is True


@pytest.mark.asyncio
async def test_executor_mixed_positional_keyword():
    """Test execution with methods that accept both positional and keyword arguments"""

    def mixed_func(a: int, b: int, c: int = 0) -> int:
        """Function with positional and optional keyword arguments"""
        return a + b + c

    registry = ActionRegistry()
    action_type = ActionType(
        object_name="global_function", method_name="mixed", callable=mixed_func
    )
    registry.register(action_type)
    executor = ActionExecutor(registry)

    # Test with positional args
    context1: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call1 = parse_action_with_ast("result = mixed(1, 2)")
    await executor.execute(action_call1, context1)
    assert context1["result"] == 3  # 1 + 2 + 0 (default)

    # Test with keyword arg for c
    context2: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call2 = parse_action_with_ast("result = mixed(1, 2, c=5)")
    await executor.execute(action_call2, context2)
    assert context2["result"] == 8  # 1 + 2 + 5


@pytest.mark.asyncio
async def test_executor_var_keyword():
    """Test execution with methods that accept **kwargs"""

    def kwargs_func(a: int, **kwargs: Any) -> dict[str, Any]:
        """Function that accepts **kwargs"""
        result = {"a": a}
        result.update(kwargs)
        return result

    registry = ActionRegistry()
    action_type = ActionType(
        object_name="global_function", method_name="kwargs", callable=kwargs_func
    )
    registry.register(action_type)
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast("result = kwargs(10, extra='value', more=42)")
    await executor.execute(action_call, context)
    assert context["result"]["a"] == 10
    assert context["result"]["extra"] == "value"
    assert context["result"]["more"] == 42
    assert context["success"] is True


@pytest.mark.asyncio
async def test_executor_context_variable_resolution():
    """Test resolving context variables in action calls"""

    def add(a: int, b: int) -> int:
        """Add.

        Args:
            a: a.
            b: b.

        Returns:
            int: Operation result.
        """
        return a + b

    registry = ActionRegistry()
    action_type = ActionType(
        object_name="global_function", method_name="add", callable=add
    )
    registry.register(action_type)
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {"x": 10, "y": 5}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast("result = add(x, y)")
    await executor.execute(action_call, context)
    assert context["result"] == 15
    assert context["success"] is True


@pytest.mark.asyncio
async def test_executor_nested_context_access():
    """Test nested context access like email.text"""

    class Email:
        """Represents a Email object."""

        def __init__(self):
            """Initialize the object."""
            self.subject = "Test Subject"
            self.body = "Test Body"

    def format_message(subject: str, body: str) -> str:
        """Format message.

        Args:
            subject: subject.
            body: body.

        Returns:
            str: Operation result.
        """
        return f"{subject}: {body}"

    registry = ActionRegistry()
    action_type = ActionType(
        object_name="global_function",
        method_name="format_message",
        callable=format_message,
    )
    registry.register(action_type)
    executor = ActionExecutor(registry)

    context: dict[str, Any] = {"email": Email()}
    # Use AST parser to create ActionCall
    action_call = parse_action_with_ast(
        "result = format_message(email.subject, email.body)"
    )
    await executor.execute(action_call, context)
    assert context["result"] == "Test Subject: Test Body"
    assert context["success"] is True


# Tests for _resolve_context_value removed - this method was part of the old
# argument resolution system and is no longer used (replaced by direct eval() in __eval__)
