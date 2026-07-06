# test/test_ast_parser.py
"""
Tests for AST-based action parser.

This module tests the AST-based parser that supports any valid Python expression.
"""

import pytest

from agy.action_call import ActionCall
from agy.ast_parser import parse_action_with_ast, parse_edge_with_ast


def test_dict_access():
    """
    Test dictionary access in action expressions.

    Example: missing_list = validation["missing_fields"]
    """
    action_str = 'missing_list = validation["missing_fields"]'
    action = parse_action_with_ast(action_str)

    assert isinstance(action, ActionCall)
    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    assert len(action.args) == 1
    # ast.unparse() normalizes quotes (double to single), so accept both
    assert action.args[0][0] in [
        'validation["missing_fields"]',
        "validation['missing_fields']",
    ]
    assert action.args[0][1] is False  # Not literal, it's code to eval
    assert action.output == "missing_list"
    assert action.kwargs == {}


def test_show_with_colons_and_complex_strings():
    """
    Test action expressions with colons in strings.

    Example: show("Classification complete: Category:", category, " - Confidence:", confidence)
    """
    action_str = 'show("Classification complete: Category:", category, " - Confidence:", confidence)'
    action = parse_action_with_ast(action_str)

    assert isinstance(action, ActionCall)
    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    assert len(action.args) == 1

    # Check that the full expression is stored as code string
    # ast.unparse() normalizes quotes, so check that key parts are present
    assert "show(" in action.args[0][0]
    assert "Classification complete: Category:" in action.args[0][0]
    assert "category" in action.args[0][0]
    assert "Confidence:" in action.args[0][0]
    assert action.args[0][1] is False  # Not literal, it's code to eval

    assert action.output == "result"  # No assignment, so default output
    assert action.kwargs == {}


def test_fstring():
    """
    Test f-string expressions in actions.

    Example: answer = f"The category is {category} with confidence {confidence}"
    """
    action_str = 'answer = f"The category is {category} with confidence {confidence}"'
    action = parse_action_with_ast(action_str)

    assert isinstance(action, ActionCall)
    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    assert action.output == "answer"

    # F-string is stored as code string
    assert len(action.args) == 1
    # ast.unparse() normalizes quotes, so check content
    assert action.args[0][0].startswith("f")
    assert "category is" in action.args[0][0]
    assert "{category}" in action.args[0][0]
    assert "{confidence}" in action.args[0][0]
    assert action.args[0][1] is False  # Not literal, it's code to eval


def test_simple_function_call():
    """Test basic function call (backwards compatibility)"""
    action_str = 'show("Hello World")'
    action = parse_action_with_ast(action_str)

    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    # ast.unparse() normalizes quotes
    assert action.args[0][0] in ['show("Hello World")', "show('Hello World')"]
    assert action.args[0][1] is False
    assert action.output == "result"


def test_method_call():
    """Test method call on object"""
    action_str = 'email.forward("billing@acme.com")'
    action = parse_action_with_ast(action_str)

    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    # ast.unparse() normalizes quotes
    assert "email.forward(" in action.args[0][0]
    assert "billing@acme.com" in action.args[0][0]
    assert action.args[0][1] is False
    assert action.output == "result"


def test_method_call_with_assignment():
    """Test method call with variable assignment"""
    action_str = 'result = email.forward("billing@acme.com")'
    action = parse_action_with_ast(action_str)

    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    # ast.unparse() normalizes quotes
    assert "email.forward(" in action.args[0][0]
    assert "billing@acme.com" in action.args[0][0]
    assert action.args[0][1] is False
    assert action.output == "result"


def test_function_with_keyword_args():
    """Test function call with keyword arguments"""
    action_str = 'classify(input_text=email.text, categories=["sales", "support"])'
    action = parse_action_with_ast(action_str)

    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    # ast.unparse() normalizes quotes
    assert "classify(" in action.args[0][0]
    assert "input_text=email.text" in action.args[0][0]
    assert "categories=" in action.args[0][0]
    assert "sales" in action.args[0][0]
    assert "support" in action.args[0][0]
    assert action.args[0][1] is False
    assert action.kwargs == {}


def test_function_with_mixed_args():
    """Test function with both positional and keyword arguments"""
    action_str = 'show("Status:", status, level="info")'
    action = parse_action_with_ast(action_str)

    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    # ast.unparse() normalizes quotes
    assert "show(" in action.args[0][0]
    assert "Status:" in action.args[0][0]
    assert "status" in action.args[0][0]
    assert "level=" in action.args[0][0]
    assert "info" in action.args[0][0]
    assert action.args[0][1] is False
    assert action.kwargs == {}


def test_attribute_access():
    """Test simple attribute access (not a method call)"""
    action_str = "text = email.body"
    action = parse_action_with_ast(action_str)

    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    assert action.args[0][0] == "email.body"
    assert action.args[0][1] is False
    assert action.output == "text"


def test_binary_operation_string_concat():
    """Test binary operation (string concatenation)"""
    action_str = 'message = "Hello " + name'
    action = parse_action_with_ast(action_str)

    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    assert action.output == "message"
    # ast.unparse() normalizes quotes
    assert "Hello" in action.args[0][0]
    assert "+" in action.args[0][0]
    assert "name" in action.args[0][0]
    assert action.args[0][1] is False


def test_complex_dict_literal():
    """Test action with complex dictionary literal containing colons"""
    action_str = """result = extract(
        input_text=email.text,
        values_to_extract={"name": "str", "email": "str", "amount": "float"}
    )"""
    # Normalize to single line for parsing
    action_str = action_str.replace("\n", "").replace("    ", " ")

    action = parse_action_with_ast(action_str)

    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    assert action.output == "result"
    # Check that the full expression is stored
    assert "extract(" in action.args[0][0]
    assert "values_to_extract=" in action.args[0][0]
    assert "name" in action.args[0][0]
    assert "str" in action.args[0][0]
    assert action.args[0][1] is False


def test_method_call_parsing():
    """
    Test that method calls are parsed correctly.
    """
    action_str = 'email.forward("test@example.com")'
    action = parse_action_with_ast(action_str)

    assert action.object_name == "global_function"
    assert action.method_name == "__eval__"
    # ast.unparse() normalizes quotes
    assert "email.forward(" in action.args[0][0]
    assert "test@example.com" in action.args[0][0]
    assert action.args[0][1] is False


def test_invalid_syntax_raises_error():
    """Test that invalid Python syntax raises an error"""
    action_str = "this is not valid python"

    with pytest.raises(ValueError, match="Could not parse action"):
        parse_action_with_ast(action_str)


def test_empty_string_raises_error():
    """Test that empty string raises an error"""
    with pytest.raises(ValueError, match="Empty action string"):
        parse_action_with_ast("")


def test_multiple_assignments_not_supported():
    """Test that multiple assignments raise an error"""
    action_str = "a, b = func()"

    with pytest.raises(ValueError, match="Multiple assignment not supported"):
        parse_action_with_ast(action_str)


def test_complex_assignment_attribute():
    """Test that complex assignment to attribute is supported"""
    action_str = 'invoice.invoice_number = invoice_data["invoice_number"]'
    action = parse_action_with_ast(action_str)

    assert isinstance(action, ActionCall)
    assert action.object_name == "global_function"
    assert action.method_name == "__exec__"
    assert len(action.args) == 1
    assert "invoice.invoice_number =" in action.args[0][0]
    assert action.args[0][1] is False  # Not literal, it's code to exec
    assert action.output is None  # Complex assignments don't set output


def test_complex_assignment_subscript():
    """Test that complex assignment to subscript is supported"""
    action_str = 'obj["key"] = value'
    action = parse_action_with_ast(action_str)

    assert isinstance(action, ActionCall)
    assert action.object_name == "global_function"
    assert action.method_name == "__exec__"
    assert len(action.args) == 1
    assert 'obj["key"] =' in action.args[0][0] or "obj['key'] =" in action.args[0][0]
    assert action.output is None


def test_complex_assignment_nested():
    """Test that nested complex assignments are supported"""
    action_str = 'obj[1]["key"] = value'
    action = parse_action_with_ast(action_str)

    assert isinstance(action, ActionCall)
    assert action.object_name == "global_function"
    assert action.method_name == "__exec__"
    assert action.output is None


def test_edge_simple_condition():
    """Test edge with simple condition"""
    edge_str = 'category == "sales": handle_sales'
    condition, target = parse_edge_with_ast(edge_str)

    assert condition == 'category == "sales"'
    assert target == "handle_sales"


def test_edge_with_dict_access():
    """Test edge with dict access in condition"""
    edge_str = 'validation["is_complete"] == True: complete_claim'
    condition, target = parse_edge_with_ast(edge_str)

    assert condition == 'validation["is_complete"] == True'
    assert target == "complete_claim"


def test_edge_with_end_target():
    """Test edge with end() target"""
    edge_str = "True: end()"
    condition, target = parse_edge_with_ast(edge_str)

    assert condition == "True"
    assert target == "end()"


def test_edge_with_colon_in_string():
    """Test edge where condition contains colon in string"""
    edge_str = 'show("Status: active"): next_node'
    condition, target = parse_edge_with_ast(edge_str)

    assert condition == 'show("Status: active")'
    assert target == "next_node"


def test_edge_with_complex_condition():
    """Test edge with complex condition"""
    edge_str = 'category == "sales" and confidence > 0.8: handle_sales'
    condition, target = parse_edge_with_ast(edge_str)

    assert condition == 'category == "sales" and confidence > 0.8'
    assert target == "handle_sales"


def test_edge_missing_colon_raises_error():
    """Test that edge without colon raises error"""
    edge_str = 'category == "sales"'

    with pytest.raises(ValueError, match="Edge must contain ':' separator"):
        parse_edge_with_ast(edge_str)


def test_edge_invalid_condition_raises_error():
    """Test that invalid condition expression raises error"""
    edge_str = "invalid python syntax: target"

    with pytest.raises(ValueError, match="Invalid condition expression"):
        parse_edge_with_ast(edge_str)
