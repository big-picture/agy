"""Module for validation."""

# agy/validation.py

from __future__ import annotations

import ast
import inspect
import os
import re
from collections.abc import Callable
from dataclasses import (
    dataclass,
    field,
    is_dataclass,
)
from dataclasses import (
    fields as dataclass_fields,
)
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from agy.action_type import ActionType
from agy.ast_parser import SAFE_BUILTINS
from agy.source_span import SourceSpan  # noqa: F401 - re-exported for backwards compat

if TYPE_CHECKING:
    from agy.action_call import ActionCall
    from agy.flow import Flow
    from agy.node import Node


@dataclass
class ValidationIssue:
    """Represents a single validation issue (error or warning)."""

    level: Literal["error", "warning"]
    message: str
    location: str | None = None  # e.g., "node: classify_email, action: 1"
    line_number: int | None = None  # Line number in flowsy file (1-based)
    line_str: str | None = None  # Content of the line
    details: dict[str, Any] | None = None


@dataclass
class ValidationResult:
    """Result of flow validation with errors and warnings."""

    is_valid: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        """Raise ValidationError if there are errors."""
        if self.errors:
            raise ValidationError(self.errors)


class ValidationError(Exception):
    """Exception raised when validation fails."""

    def __init__(self, errors: list[ValidationIssue]):
        """Initialize the object.

        Args:
            errors: errors.
        """
        self.errors = errors
        error_messages = [
            f"{err.location}: {err.message}" if err.location else err.message
            for err in errors
        ]
        super().__init__("\n".join(error_messages))


# AST-Analyse Helper-Funktionen


class _VariableExtractor(ast.NodeVisitor):
    """Extract variable names from AST expression."""

    def __init__(self):
        """Initialize the object."""
        self.variables: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        """Extract variable names (not function names)."""
        # Skip built-ins and constants
        if node.id not in SAFE_BUILTINS and node.id not in ["None", "True", "False"]:
            # Check if it's a load (variable access), not store (assignment)
            if isinstance(node.ctx, ast.Load):
                self.variables.add(node.id)
        self.generic_visit(node)


class _CallableExtractor(ast.NodeVisitor):
    """Extract function/method calls from AST expression."""

    def __init__(self):
        """Initialize the object."""
        self.callables: list[
            tuple[str | None, str, bool]
        ] = []  # (object_name, method_name, is_call)
        self.call_func_nodes: set[int] = (
            set()
        )  # IDs of nodes that are the func of a Call

    def visit_Call(self, node: ast.Call) -> None:
        """Extract function/method calls."""
        # Mark the func node so we don't double-count it as attribute access
        self.call_func_nodes.add(id(node.func))

        if isinstance(node.func, ast.Name):
            # Global function call: func_name()
            self.callables.append((None, node.func.id, True))
        elif isinstance(node.func, ast.Attribute):
            # Method call: obj.method()
            obj_name = self._extract_object_name(node.func.value)
            self.callables.append((obj_name, node.func.attr, True))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Extract attribute access (only if not part of a method call)."""
        # Skip if this attribute is the func of a Call (already handled as method call)
        if id(node) not in self.call_func_nodes:
            obj_name = self._extract_object_name(node.value)
            self.callables.append(
                (obj_name, node.attr, False)
            )  # False = attribute, not call
        self.generic_visit(node)

    def _extract_object_name(self, node: ast.expr) -> str | None:
        """Extract object name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            # Recursive: obj.attr.attr2
            base = self._extract_object_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None


def _extract_variables_from_ast(expr_str: str) -> set[str]:
    """Extract variable names from Python expression string."""
    try:
        tree = ast.parse(expr_str, mode="eval")
        extractor = _VariableExtractor()
        extractor.visit(tree)
        return extractor.variables
    except SyntaxError:
        return set()


def _extract_callables_from_ast(expr_str: str) -> list[tuple[str | None, str, bool]]:
    """Extract function/method calls and attribute access from Python expression string.

    Returns:
        List of (object_name, method/attr_name, is_call) tuples
        - is_call=True: method/function call (obj.method() or func())
        - is_call=False: attribute access (obj.attr)
    """
    try:
        tree = ast.parse(expr_str, mode="eval")
        extractor = _CallableExtractor()
        extractor.visit(tree)
        return extractor.callables
    except SyntaxError:
        return []


class _FunctionCallInfo:
    """Information about a function call for signature validation."""

    def __init__(self, name: str, args: list[ast.expr], keywords: list[ast.keyword]):
        """Initialize the object.

        Args:
            name: name.
            args: args.
            keywords: keywords.
        """
        self.name = name
        self.args = args
        self.keywords = keywords


class _FunctionCallExtractor(ast.NodeVisitor):
    """Extract function calls with their arguments from AST."""

    def __init__(self):
        """Initialize the object."""
        self.calls: list[_FunctionCallInfo] = []

    def visit_Call(self, node: ast.Call) -> None:
        """Extract function calls (global functions only for now)."""
        if isinstance(node.func, ast.Name):
            # Global function call: func_name(args)
            self.calls.append(
                _FunctionCallInfo(
                    name=node.func.id,
                    args=node.args,
                    keywords=node.keywords,
                )
            )
        self.generic_visit(node)


def _extract_function_calls_from_ast(expr_str: str) -> list[_FunctionCallInfo]:
    """Extract function calls with arguments from Python expression string."""
    try:
        tree = ast.parse(expr_str, mode="eval")
        extractor = _FunctionCallExtractor()
        extractor.visit(tree)
        return extractor.calls
    except SyntaxError:
        return []


# Type-Check Helper-Funktionen


def _context_object_type_name(obj_or_cls: Any) -> str:
    """Return the declared type name for a context class or instance."""
    if inspect.isclass(obj_or_cls):
        return obj_or_cls.__name__
    return type(obj_or_cls).__name__


def _context_object_has_attribute(obj_or_cls: Any, attr_name: str) -> bool:
    """Check attributes on either an instance or class-based validation contract."""
    if hasattr(obj_or_cls, attr_name):
        return True

    cls = obj_or_cls if inspect.isclass(obj_or_cls) else type(obj_or_cls)

    annotations = getattr(cls, "__annotations__", {})
    if attr_name in annotations:
        return True

    model_fields = getattr(cls, "model_fields", None)
    if isinstance(model_fields, dict) and attr_name in model_fields:
        return True

    legacy_model_fields = getattr(cls, "__fields__", None)
    if isinstance(legacy_model_fields, dict) and attr_name in legacy_model_fields:
        return True

    if is_dataclass(cls):
        return any(field_info.name == attr_name for field_info in dataclass_fields(cls))

    return False


def _get_context_object_member(obj_or_cls: Any, member_name: str) -> Any:
    """Return a member from a context class or instance."""
    return getattr(obj_or_cls, member_name)


def _check_context_in_types(
    flow_context_in: dict[str, str], provided_context_in: dict[str, Any] | None
) -> list[ValidationIssue]:
    """Check if provided context_in classes or instances match declared types."""
    issues: list[ValidationIssue] = []

    if not provided_context_in:
        return issues

    for key, declared_type_str in flow_context_in.items():
        if key not in provided_context_in:
            continue  # Missing keys handled elsewhere

        obj = provided_context_in[key]
        obj_type_name = _context_object_type_name(obj)
        if obj_type_name != declared_type_str:
            issues.append(
                ValidationIssue(
                    level="error",
                    message=f"Type mismatch for context_in['{key}']: expected {declared_type_str}, got {obj_type_name}",
                    location=f"context_in: {key}",
                )
            )

    return issues


# Callable-Check Helper-Funktionen


def _check_callable_signature(
    callable_obj: Callable,
    method_name: str,
    call_args: list[ast.expr],
    call_keywords: list[ast.keyword],
    location: str,
) -> list[ValidationIssue]:
    """Check if callable signature matches the call arguments."""
    issues: list[ValidationIssue] = []

    try:
        sig = inspect.signature(callable_obj)
    except (ValueError, TypeError):
        # Can't inspect signature (e.g., built-in), skip
        return issues

    # Get required parameters (no default value)
    required_params: list[str] = []
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        if param.default is inspect.Parameter.empty and param.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            required_params.append(param_name)

    # Get provided arguments
    provided_positional = len(call_args)
    provided_keywords = {kw.arg for kw in call_keywords if kw.arg is not None}

    # Check if required parameters are covered
    missing_params: list[str] = []
    for i, param_name in enumerate(required_params):
        # Check if covered by positional arg
        if i < provided_positional:
            continue
        # Check if covered by keyword arg
        if param_name in provided_keywords:
            continue
        missing_params.append(param_name)

    if missing_params:
        issues.append(
            ValidationIssue(
                level="error",
                message=f"Function '{method_name}' missing required argument(s): {', '.join(missing_params)}",
                location=location,
            )
        )

    return issues


def _check_builtin_callable(func_name: str, location: str) -> list[ValidationIssue]:
    """Check if function is in SAFE_BUILTINS."""
    issues: list[ValidationIssue] = []

    if func_name not in SAFE_BUILTINS:
        issues.append(
            ValidationIssue(
                level="error",
                message=f"Built-in function '{func_name}' is not in SAFE_BUILTINS",
                location=location,
            )
        )

    return issues


def _check_contrib_callable(
    func_name: str, registry: dict[str, ActionType], location: str
) -> list[ValidationIssue]:
    """Check if function is in contrib ActionTypes."""
    issues: list[ValidationIssue] = []

    if func_name not in registry:
        issues.append(
            ValidationIssue(
                level="error",
                message=f"Function '{func_name}' is not registered (not in contrib or custom action_types)",
                location=location,
            )
        )

    return issues


def _check_object_method(
    obj_name: str,
    method_name: str,
    context_in: dict[str, Any],
    location: str,
) -> list[ValidationIssue]:
    """Check if object method exists and validate signature (SIGNATURE prüfen)."""
    issues: list[ValidationIssue] = []

    if obj_name not in context_in:
        issues.append(
            ValidationIssue(
                level="error",
                message=f"Object '{obj_name}' not found in context_in",
                location=location,
            )
        )
        return issues

    obj = context_in[obj_name]

    # Check if method exists
    if not _context_object_has_attribute(obj, method_name):
        issues.append(
            ValidationIssue(
                level="error",
                message=f"Object '{obj_name}' has no method '{method_name}'",
                location=location,
            )
        )
        return issues

    method = _get_context_object_member(obj, method_name)

    # Check if it's callable
    if not callable(method):
        issues.append(
            ValidationIssue(
                level="error",
                message=f"'{obj_name}.{method_name}' is not callable",
                location=location,
            )
        )
        return issues

    # SIGNATURE prüfen
    try:
        inspect.signature(method)
        # Note: Full signature validation would require parsing actual call arguments
        # For now, just verify it exists and is callable
    except (ValueError, TypeError):
        # Can't inspect signature (e.g., built-in method), skip
        pass

    return issues


def _check_object_attribute(
    obj_name: str,
    attr_name: str,
    context_in: dict[str, Any],
    location: str,
) -> list[ValidationIssue]:
    """Check if object attribute exists."""
    issues: list[ValidationIssue] = []

    if obj_name not in context_in:
        issues.append(
            ValidationIssue(
                level="error",
                message=f"Object '{obj_name}' not found in context_in",
                location=location,
            )
        )
        return issues

    obj = context_in[obj_name]

    if not _context_object_has_attribute(obj, attr_name):
        issues.append(
            ValidationIssue(
                level="error",
                message=f"Object '{obj_name}' has no attribute '{attr_name}'",
                location=location,
            )
        )

    return issues


# LLM-Check Helper-Funktionen


def _extract_providers_from_flow(flow: Flow) -> set[str]:
    """Extract provider names from set_model_call() actions in the flow."""
    providers: set[str] = set()

    for node in flow.nodes:
        if not node.actions:
            continue
        for action_call in node.actions:
            if action_call.method_name != "__eval__" or not action_call.args:
                continue
            expr_str, is_literal = action_call.args[0]
            if is_literal or "set_model_call" not in expr_str:
                continue

            # Extract provider= parameter
            pattern = r'set_model_call\s*\([^)]*provider\s*=\s*["\']([^"\']+)["\']'
            match = re.search(pattern, expr_str)
            if match:
                providers.add(match.group(1))

    return providers


def _check_llm_env_vars(
    providers_used: set[str] | None = None,
) -> list[ValidationIssue]:
    """Check if LLM ENV variables are set for the used providers.

    Args:
        providers_used: Set of provider names used in the flow (from set_model calls).
                       If None or empty, uses default_provider from config.
    """
    from agy.config import load_llm_config

    issues: list[ValidationIssue] = []

    # Determine which providers to check
    if not providers_used:
        config = load_llm_config()
        providers_used = {config.get("default_provider", "openai")}

    # Provider → (env_var, description)
    provider_keys = {
        "openai": [("OPENAI_API_KEY", "OpenAI")],
        "anthropic": [("ANTHROPIC_API_KEY", "Anthropic")],
        "google": [("GEMINI_API_KEY", "Google Gemini")],
        "azure": [
            ("AZURE_OPENAI_API_KEY", "Azure OpenAI"),
            ("AZURE_OPENAI_ENDPOINT", "Azure OpenAI endpoint"),
        ],
    }

    for provider in providers_used:
        provider_lower = provider.lower()
        if provider_lower not in provider_keys:
            continue

        for env_var, description in provider_keys[provider_lower]:
            if not os.getenv(env_var):
                issues.append(
                    ValidationIssue(
                        level="warning",
                        message=f"{env_var} not set (required for {description})",
                        location="environment",
                    )
                )

    return issues


# File-Check Helper-Funktionen


def _resolve_file_path(
    file_path: str, flowsy_path: Path, project_root: Path | None = None
) -> Path | None:
    """Resolve file path using same logic as runtime (project_root → flowsy_path → CWD)."""
    from agy.config import get_project_root
    from agy.utils.file_readers import find_file_in_standard_dirs

    # Use provided project_root or auto-detect
    if project_root is None:
        try:
            project_root = get_project_root()
        except Exception:
            project_root = None

    path_obj = Path(file_path)

    # Absolute path
    if path_obj.is_absolute():
        return path_obj if path_obj.exists() else None

    # Try relative to flowsy_path directory
    flowsy_dir = flowsy_path.parent
    candidate = flowsy_dir / file_path
    if candidate.exists():
        return candidate.resolve()

    # Try relative to CWD
    candidate = Path.cwd() / file_path
    if candidate.exists():
        return candidate.resolve()

    # Try relative to project_root
    if project_root:
        candidate = project_root / file_path
        if candidate.exists():
            return candidate.resolve()

    # Use find_file_in_standard_dirs as last resort
    try:
        return find_file_in_standard_dirs(file_path)
    except FileNotFoundError:
        return None


def _check_file_exists(
    file_path: str,
    flowsy_path: Path,
    project_root: Path | None,
    location: str,
) -> list[ValidationIssue]:
    """Check if file exists using path resolution logic."""
    issues: list[ValidationIssue] = []

    resolved = _resolve_file_path(file_path, flowsy_path, project_root)
    if resolved is None:
        issues.append(
            ValidationIssue(
                level="error",
                message=f"File not found: {file_path}",
                location=location,
            )
        )

    return issues


# Structural-Check Helper-Funktionen


def _check_node_connections(flow: Any) -> list[ValidationIssue]:  # type: ignore[no-untyped-def]
    """Check if all edge targets exist (except end()) and flow has nodes."""
    issues: list[ValidationIssue] = []

    # Check if flow has any nodes
    if not flow.nodes:
        issues.append(
            ValidationIssue(
                level="error",
                message="Flow has no nodes",
                location="flow",
            )
        )
        return issues

    node_names = {node.name for node in flow.nodes}

    def _is_end_target(target: str) -> bool:
        target_stripped = target.strip()
        if target_stripped == "end":
            return True
        if not target_stripped.startswith("end") or not target_stripped.endswith(")"):
            return False
        # Allow whitespace between function name and parenthesis: "end (...)"
        return target_stripped[3:].lstrip().startswith("(")

    for node in flow.nodes:
        if not node.edges:
            continue

        for edge in node.edges:
            target = edge.target

            # Handle string targets (not yet resolved)
            if isinstance(target, str):
                # Skip end() targets
                if _is_end_target(target):
                    continue

                if target not in node_names:
                    span = edge.source_span
                    issues.append(
                        ValidationIssue(
                            level="error",
                            message=f"Edge target node '{target}' not found",
                            location=f"node: {node.name}",
                            line_number=span.start_line if span else None,
                            line_str=span.content if span else None,
                        )
                    )

            # Handle Node object targets (already resolved)
            elif hasattr(target, "name"):
                if target.name not in node_names:
                    span = edge.source_span
                    issues.append(
                        ValidationIssue(
                            level="error",
                            message=f"Edge target node '{target.name}' not found",
                            location=f"node: {node.name}",
                            line_number=span.start_line if span else None,
                            line_str=span.content if span else None,
                        )
                    )

    return issues


# ============================================================================
# High-Level Validation Functions
# ============================================================================


def validate_action(
    action_call: ActionCall,
    node_name: str,
    defined_variables: set[str],
    registry_dict: dict[str, ActionType],
    context_in: dict[str, Any] | None,
    flowsy_path: Path,
    project_root: Path | None,
) -> list[ValidationIssue]:
    """Validate a single action and return issues with source_span info."""
    issues: list[ValidationIssue] = []
    span = action_call.source_span

    # Only check __eval__ actions (all actions are in this format)
    if action_call.method_name != "__eval__" or not action_call.args:
        return issues

    expr_str, is_literal = action_call.args[0]
    if is_literal:
        return issues

    # Extract variables and callables from expression
    used_variables = _extract_variables_from_ast(expr_str)
    callables = _extract_callables_from_ast(expr_str)

    # Build set of callable names (functions that are called, not variables)
    callable_names: set[str] = set()
    for obj_name, method_name, is_call in callables:
        if obj_name is None and method_name and is_call:
            callable_names.add(method_name)

    # Check if variables are defined (exclude callable names)
    for var_name in used_variables:
        # Skip if it's a callable (function call, not variable)
        if var_name in callable_names:
            continue
        # Skip built-ins
        if var_name in SAFE_BUILTINS:
            continue
        # Skip if it's in registry (contrib/custom functions)
        if var_name in registry_dict:
            continue

        if var_name not in defined_variables:
            issues.append(
                ValidationIssue(
                    level="error",
                    message=f"Variable '{var_name}' is not defined (not in context_in or previous actions)",
                    location=f"node: {node_name}",
                    line_number=span.start_line if span else None,
                    line_str=span.content if span else None,
                )
            )

    # Extract function calls with arguments for signature validation
    function_calls = _extract_function_calls_from_ast(expr_str)
    function_calls_by_name = {call.name: call for call in function_calls}

    # Check callables
    for obj_name, method_name, is_call in callables:
        if obj_name is None:
            # Global function call: func_name()
            if method_name in SAFE_BUILTINS:
                builtin_issues = _check_builtin_callable(
                    method_name, f"node: {node_name}"
                )
                for issue in builtin_issues:
                    issue.line_number = span.start_line if span else None
                    issue.line_str = span.content if span else None
                issues.extend(builtin_issues)
            else:
                # Check if it's in contrib or custom actions
                contrib_issues = _check_contrib_callable(
                    method_name, registry_dict, f"node: {node_name}"
                )
                for issue in contrib_issues:
                    issue.line_number = span.start_line if span else None
                    issue.line_str = span.content if span else None
                issues.extend(contrib_issues)

                # If function is registered, check signature
                if (
                    method_name in registry_dict
                    and method_name in function_calls_by_name
                ):
                    action_type = registry_dict[method_name]
                    if action_type.callable:
                        call_info = function_calls_by_name[method_name]
                        sig_issues = _check_callable_signature(
                            action_type.callable,
                            method_name,
                            call_info.args,
                            call_info.keywords,
                            f"node: {node_name}",
                        )
                        for issue in sig_issues:
                            issue.line_number = span.start_line if span else None
                            issue.line_str = span.content if span else None
                        issues.extend(sig_issues)
        else:
            # Object method/attribute: obj.method() or obj.attr
            if "." not in obj_name:
                if is_call:
                    # Method call: obj.method()
                    if context_in and obj_name in context_in:
                        method_issues = _check_object_method(
                            obj_name, method_name, context_in, f"node: {node_name}"
                        )
                        for issue in method_issues:
                            issue.line_number = span.start_line if span else None
                            issue.line_str = span.content if span else None
                        issues.extend(method_issues)
                else:
                    # Attribute access: obj.attr
                    if context_in and obj_name in context_in:
                        attr_issues = _check_object_attribute(
                            obj_name, method_name, context_in, f"node: {node_name}"
                        )
                        for issue in attr_issues:
                            issue.line_number = span.start_line if span else None
                            issue.line_str = span.content if span else None
                        issues.extend(attr_issues)
            else:
                # Nested access: obj.attr.method()
                base_obj = obj_name.split(".")[0]
                if context_in and base_obj not in context_in:
                    issues.append(
                        ValidationIssue(
                            level="error",
                            message=f"Object '{base_obj}' not found in context_in",
                            location=f"node: {node_name}",
                            line_number=span.start_line if span else None,
                            line_str=span.content if span else None,
                        )
                    )

    # Check file paths in LLM function calls
    llm_functions_with_files = {"classify", "extract", "respond"}

    if any(func in expr_str for func in llm_functions_with_files):
        pattern = r'instruction_file\s*=\s*["\']([^"\']+)["\']'
        matches = re.findall(pattern, expr_str)
        for file_path in matches:
            file_issues = _check_file_exists(
                file_path, flowsy_path, project_root, f"node: {node_name}"
            )
            for issue in file_issues:
                issue.line_number = span.start_line if span else None
                issue.line_str = span.content if span else None
            issues.extend(file_issues)

    if "load_files_text" in expr_str:
        pattern = r"load_files_text\s*\(\s*([^)]+)\)"
        matches = re.findall(pattern, expr_str)
        for match in matches:
            file_pattern = r'["\']([^"\']+)["\']'
            file_matches = re.findall(file_pattern, match)
            for file_path in file_matches:
                file_issues = _check_file_exists(
                    file_path, flowsy_path, project_root, f"node: {node_name}"
                )
                for issue in file_issues:
                    issue.line_number = span.start_line if span else None
                    issue.line_str = span.content if span else None
                issues.extend(file_issues)

    if "get_prompt_from_file" in expr_str:
        pattern = r'get_prompt_from_file\s*\(\s*file_path\s*=\s*["\']([^"\']+)["\']'
        matches = re.findall(pattern, expr_str)
        for file_path in matches:
            file_issues = _check_file_exists(
                file_path, flowsy_path, project_root, f"node: {node_name}"
            )
            for issue in file_issues:
                issue.line_number = span.start_line if span else None
                issue.line_str = span.content if span else None
            issues.extend(file_issues)

    return issues


def validate_node_actions(
    node: Node,
    defined_variables: set[str],
    registry_dict: dict[str, ActionType],
    context_in: dict[str, Any] | None,
    flowsy_path: Path,
    project_root: Path | None,
) -> list[ValidationIssue]:
    """Validate all actions in a node."""
    issues: list[ValidationIssue] = []

    if node.control_type == "stochastic":
        span = node.source_span

        if node.actions:
            issues.append(
                ValidationIssue(
                    level="error",
                    message="Stochastic nodes must use requests, not actions",
                    location=f"node: {node.name}",
                    line_number=span.start_line if span else None,
                    line_str=span.content if span else None,
                )
            )

        if not node.agent:
            issues.append(
                ValidationIssue(
                    level="error",
                    message="Stochastic node is missing required 'agent'",
                    location=f"node: {node.name}",
                    line_number=span.start_line if span else None,
                    line_str=span.content if span else None,
                )
            )
        elif node.agent not in defined_variables:
            issues.append(
                ValidationIssue(
                    level="error",
                    message=f"Stochastic agent '{node.agent}' is not defined in context_in",
                    location=f"node: {node.name}",
                    line_number=span.start_line if span else None,
                    line_str=span.content if span else None,
                )
            )
        elif context_in and node.agent in context_in:
            agent = context_in[node.agent]
            run_method = (
                _get_context_object_member(agent, "run")
                if _context_object_has_attribute(agent, "run")
                else None
            )
            if not callable(run_method):
                issues.append(
                    ValidationIssue(
                        level="error",
                        message=(
                            f"Stochastic agent '{node.agent}' must provide a "
                            "callable run(...) method"
                        ),
                        location=f"node: {node.name}",
                        line_number=span.start_line if span else None,
                        line_str=span.content if span else None,
                    )
                )

        if not node.requests:
            issues.append(
                ValidationIssue(
                    level="error",
                    message="Stochastic node must define at least one request",
                    location=f"node: {node.name}",
                    line_number=span.start_line if span else None,
                    line_str=span.content if span else None,
                )
            )

        if node.output:
            defined_variables.add(node.output)
        if node.message:
            defined_variables.add(node.message)
        defined_variables.update({"output", "message", "agent_outputs", "result"})

        return issues

    if not node.actions:
        return issues

    for action_call in node.actions:
        action_issues = validate_action(
            action_call=action_call,
            node_name=node.name,
            defined_variables=defined_variables,
            registry_dict=registry_dict,
            context_in=context_in,
            flowsy_path=flowsy_path,
            project_root=project_root,
        )
        issues.extend(action_issues)

        # Track variable assignments
        if action_call.output and action_call.output != "result":
            defined_variables.add(action_call.output)
        defined_variables.add("result")  # All actions write to result

    return issues


def validate_flow_actions(
    flow: Flow,
    registry_dict: dict[str, ActionType],
    context_in: dict[str, Any] | None,
    flowsy_path: Path,
    project_root: Path | None,
) -> list[ValidationIssue]:
    """Validate all actions in a flow."""
    issues: list[ValidationIssue] = []

    # Track variables defined in actions for variable checking
    defined_variables: set[str] = set(flow.context_in.keys()) | {
        "result",
        "success",
        "error_msg",
        "confidence",
        "context",  # implicit flow context dict
    }

    for node in flow.nodes:
        node_issues = validate_node_actions(
            node=node,
            defined_variables=defined_variables,
            registry_dict=registry_dict,
            context_in=context_in,
            flowsy_path=flowsy_path,
            project_root=project_root,
        )
        issues.extend(node_issues)

    return issues


def _build_registry(
    action_types: list[ActionType] | None = None,
) -> dict[str, ActionType]:
    """Build registry dict from contrib and custom action types."""
    from agy.action_executor import ActionRegistry

    registry = ActionRegistry()

    # Load contrib ActionTypes
    try:
        from agy.contrib.action_types import get_contrib_action_types

        contrib_types = get_contrib_action_types()
        for action_type in contrib_types:
            registry.register(action_type)
    except ImportError:
        pass

    # Register provided action types
    if action_types:
        for action_type in action_types:
            registry.register(action_type)

    # Build registry dict for easy lookup
    registry_dict: dict[str, ActionType] = {}
    for method_name, action_type in registry.action_types.items():
        registry_dict[method_name] = action_type

    return registry_dict
