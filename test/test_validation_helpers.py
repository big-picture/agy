"""Additional unit tests for validation helper functions."""

from __future__ import annotations

from pathlib import Path

from agy.validation import (
    _check_context_in_types,
    _check_file_exists,
    _extract_callables_from_ast,
    _extract_function_calls_from_ast,
    _extract_variables_from_ast,
)


def test_extract_variables_and_callables_from_ast() -> None:
    expr = "classify(input_text=email.text) if len(items) > 0 else fallback()"
    vars_used = _extract_variables_from_ast(expr)
    callables = _extract_callables_from_ast(expr)
    funcs = _extract_function_calls_from_ast(expr)

    assert "email" in vars_used
    assert "items" in vars_used
    assert any(method == "classify" and is_call for _, method, is_call in callables)
    assert any(call.name == "len" for call in funcs)


def test_check_context_in_types_reports_mismatch() -> None:
    class Invoice:
        pass

    class Email:
        pass

    issues = _check_context_in_types({"ctx": "Invoice"}, {"ctx": Email()})
    assert issues
    assert "Type mismatch" in issues[0].message

    ok_issues = _check_context_in_types({"ctx": "Invoice"}, {"ctx": Invoice()})
    assert ok_issues == []


def test_check_file_exists_uses_resolution_logic(tmp_path: Path) -> None:
    flowsy = tmp_path / "flow.flowsy"
    flowsy.write_text("name: x", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    file_path = data_dir / "prompt.md"
    file_path.write_text("hello", encoding="utf-8")

    issues_ok = _check_file_exists("data/prompt.md", flowsy, tmp_path, "node: n1")
    assert issues_ok == []

    issues_missing = _check_file_exists("data/missing.md", flowsy, tmp_path, "node: n1")
    assert issues_missing
    assert "File not found" in issues_missing[0].message
