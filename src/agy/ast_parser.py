# agy/ast_parser.py
"""
AST-based action/edge parser with generic Python expression evaluation.

This module provides Python AST-based parsing for action strings,
enabling support for ANY valid Python expression by evaluating them
directly instead of using a whitelist approach.
"""

from __future__ import annotations

import ast

from agy.action_call import ActionCall

# Safe built-ins that are allowed in evaluated expressions
SAFE_BUILTINS = {
    # Type constructors
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    # Common functions
    "len": len,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "reversed": reversed,
    "enumerate": enumerate,
    "zip": zip,
    "range": range,
    # String methods (as functions)
    "join": str.join,
    # Type checking
    "isinstance": isinstance,
    "type": type,
    # None, True, False
    "None": None,
    "True": True,
    "False": False,
}


def parse_action_with_ast(action_str: str) -> ActionCall:
    """
    Parse action string using Python AST with generic evaluation.

    Instead of parsing specific expression types, this function converts
    any valid Python expression to an evaluable string that will be
    executed at runtime with the flow context.

    Args:
        action_str: The action string to parse

    Returns:
        ActionCall object with __eval__ method that will evaluate the expression

    Raises:
        ValueError: If the action string is not valid Python syntax
    """
    try:
        return _parse_action_ast(action_str)
    except (SyntaxError, ValueError) as ast_error:
        raise ValueError(
            f"Could not parse action: {action_str}\nAST Error: {ast_error}"
        ) from ast_error


def _parse_action_ast(action_str: str) -> ActionCall:
    """
    Internal AST parser implementation.

    Converts any Python expression to an ActionCall that evaluates it.
    """
    tree = ast.parse(action_str, mode="exec")

    if not tree.body:
        raise ValueError("Empty action string")

    stmt = tree.body[0]

    # Case 1: Assignment (var = expression OR complex target = expression)
    if isinstance(stmt, ast.Assign):
        if len(stmt.targets) != 1:
            raise ValueError("Multiple assignment not supported")

        target = stmt.targets[0]
        expr = stmt.value

        # Check for multiple assignment (tuple unpacking): a, b = func()
        if isinstance(target, ast.Tuple):
            raise ValueError("Multiple assignment not supported")

        # Check if target is simple variable (ast.Name) or complex (ast.Attribute, ast.Subscript)
        if isinstance(target, ast.Name):
            # Simple assignment: var = expr
            output_var = target.id
            expr_str = ast.unparse(expr)

            return ActionCall(
                object_name="global_function",
                method_name="__eval__",
                args=[(expr_str, False)],  # False = not literal, it's code to eval
                kwargs={},
                output=output_var,
            )
        else:
            # Complex assignment: obj.attr = expr, obj["key"] = expr, obj[1] = expr, etc.
            # Convert entire assignment statement to string
            assignment_str = ast.unparse(
                stmt
            )  # "invoice.invoice_number = invoice_data['invoice_number']"

            return ActionCall(
                object_name="global_function",
                method_name="__exec__",  # Use __exec__ for assignment statements
                args=[(assignment_str, False)],
                kwargs={},
                output=None,  # No output variable for complex assignments
            )

    # Case 2: Expression (no assignment)
    elif isinstance(stmt, ast.Expr):
        # Convert expression to Python code string
        expr_str = ast.unparse(stmt.value)

        return ActionCall(
            object_name="global_function",
            method_name="__eval__",
            args=[(expr_str, False)],
            kwargs={},
            output="result",
        )

    else:
        raise ValueError(f"Unsupported statement: {type(stmt).__name__}")


def parse_edge_with_ast(edge_str: str) -> tuple[str, str]:
    """
    Parse edge string using AST for the condition part.

    Edge format: "AST_STATEMENT : NODE_NAME" or "AST_STATEMENT : end(...)"

    The condition (left side of `:`) is parsed as an AST expression.
    The target (right side of `:`) is a node name or "end(...)".

    Args:
        edge_str: The edge string to parse (e.g., 'category == "sales": handle_sales')

    Returns:
        Tuple of (condition_string, target_string)
        - condition_string: The condition as a string (AST expression)
        - target_string: The target node name or "end(...)"

    Examples:
        >>> parse_edge_with_ast('category == "sales": handle_sales')
        ('category == "sales"', 'handle_sales')

        >>> parse_edge_with_ast('validation["is_complete"] == True: complete_claim')
        ('validation["is_complete"] == True', 'complete_claim')

        >>> parse_edge_with_ast('True: end()')
        ('True', 'end()')
    """
    # Split at the last colon (not the first, because condition might contain colons in strings)
    if ":" not in edge_str:
        raise ValueError(f"Edge must contain ':' separator: {edge_str}")

    # Find the last colon that is not inside quotes
    last_colon_idx = -1
    in_quotes = False
    quote_char = None

    for i in range(len(edge_str) - 1, -1, -1):
        char = edge_str[i]
        if char in ['"', "'"] and (i == 0 or edge_str[i - 1] != "\\"):
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
                quote_char = None
        elif char == ":" and not in_quotes:
            last_colon_idx = i
            break

    if last_colon_idx == -1:
        raise ValueError(f"Could not find valid ':' separator in edge: {edge_str}")

    condition_str = edge_str[:last_colon_idx].strip()
    target_str = edge_str[last_colon_idx + 1 :].strip()

    # Validate condition is valid Python AST
    try:
        ast.parse(condition_str, mode="eval")
    except SyntaxError as e:
        raise ValueError(
            f"Invalid condition expression in edge: {condition_str}\nError: {e}"
        )

    # Validate target
    if not target_str:
        raise ValueError(f"Edge target is empty: {edge_str}")

    return (condition_str, target_str)
