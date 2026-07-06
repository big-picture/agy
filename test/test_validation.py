# test/test_validation.py

"""Tests for validation functions with SourceSpan support."""

from pathlib import Path

from agy.flow import Flow

TEST_FLOWSYS_DIR = Path(__file__).parent / "test_flowsys"


class TestValidationWithSourceSpan:
    """Tests for validation with line_number and line_str in ValidationIssue."""

    def test_missing_attribute_has_source_span(self):
        """Test that missing attribute error contains line info."""
        import tempfile

        class MockEmail:
            """Represents a MockEmail object."""

            subject: str = "test"
            # no 'nonexistent_attr' attribute

        flowsy_content = """name: Test Flow
description: A test flow
context_in:
  email: MockEmail

nodes:
  test_node:
    actions:
      - result = email.nonexistent_attr
    edges:
      - True: end()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".flowsy", delete=False) as f:
            f.write(flowsy_content)
            temp_path = Path(f.name)

        try:
            result = Flow.validate(temp_path, context_in={"email": MockEmail()})

            assert not result.is_valid
            assert len(result.errors) >= 1

            # Find the attribute error
            attr_error = None
            for error in result.errors:
                if "nonexistent_attr" in error.message:
                    attr_error = error
                    break

            assert attr_error is not None, (
                f"Expected error about nonexistent_attr, got: {result.errors}"
            )
            assert attr_error.line_number is not None, "Expected line_number to be set"
            assert attr_error.line_str is not None, "Expected line_str to be set"
            assert "nonexistent_attr" in attr_error.line_str
        finally:
            temp_path.unlink()

    def test_nonexistent_function_has_source_span(self):
        """Test that nonexistent function error contains line info."""
        flowsy_path = (
            TEST_FLOWSYS_DIR / "invoice_invalid_005_nonexistent_function.flowsy"
        )

        result = Flow.validate(flowsy_path)

        assert not result.is_valid

        # Find the function error
        func_error = None
        for error in result.errors:
            if "nonexistent_func" in error.message:
                func_error = error
                break

        assert func_error is not None, "Expected error about nonexistent_func"
        assert func_error.line_number is not None, "Expected line_number to be set"
        assert func_error.line_str is not None, "Expected line_str to be set"
        assert func_error.line_number == 9, (
            f"Expected line 9, got {func_error.line_number}"
        )
        assert "nonexistent_func" in func_error.line_str

    def test_valid_flow_with_custom_actions(self):
        """Test that a valid flow with registered actions has no validation errors."""
        from agy.action_type import ActionType

        flowsy_path = TEST_FLOWSYS_DIR / "invoice_valid.flowsy"

        # Register pdf2text as a custom action
        pdf2text_action = ActionType(
            object_name="global_function",
            method_name="pdf2text",
            kwargs={"file_path": str},
            callable=lambda file_path: "mock text",
        )

        result = Flow.validate(flowsy_path, action_types=[pdf2text_action])

        assert result.is_valid, f"Expected valid, got errors: {result.errors}"
        assert len(result.errors) == 0

    def test_node_name_with_end_prefix_is_valid_target(self):
        """Edge target end_* should resolve as a regular node, not end()."""
        import tempfile

        flowsy_content = """name: End Prefix Node Validation
nodes:
  start:
    edges:
      - True: end_review
  end_review:
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".flowsy", delete=False) as f:
            f.write(flowsy_content)
            temp_path = Path(f.name)

        try:
            result = Flow.validate(temp_path)
            assert result.is_valid, f"Expected valid, got errors: {result.errors}"
        finally:
            temp_path.unlink()

    def test_validation_issue_str_contains_line_info(self):
        """Test that ValidationIssue string representation contains line info."""
        from agy.validation import ValidationIssue

        issue = ValidationIssue(
            level="error",
            message="Variable 'x' is not defined",
            location="node: test_node",
            line_number=15,
            line_str="- x = undefined_func()",
        )

        # Check that the issue has all the info
        assert issue.line_number == 15
        assert issue.line_str == "- x = undefined_func()"
        assert issue.level == "error"
        assert issue.location == "node: test_node"


class TestValidateFlowActions:
    """Tests for validate_flow_actions function."""

    def test_undefined_variable_error(self):
        """Test that undefined variable errors have source span."""
        flowsy_content = """name: Test Flow
description: A test flow
context_in:
  email: Email

nodes:
  test_node:
    actions:
      - result = process(undefined_var)
    edges:
      - True: end()
"""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".flowsy", delete=False) as f:
            f.write(flowsy_content)
            temp_path = Path(f.name)

        try:
            result = Flow.validate(temp_path)

            assert not result.is_valid

            # Find undefined variable error
            var_error = None
            for error in result.errors:
                if "undefined_var" in error.message and "not defined" in error.message:
                    var_error = error
                    break

            assert var_error is not None, (
                f"Expected error about undefined_var, got: {result.errors}"
            )
            assert var_error.line_number is not None
            assert var_error.line_str is not None
            assert "undefined_var" in var_error.line_str
        finally:
            temp_path.unlink()

    def test_context_in_can_validate_against_classes(self):
        """Test that validation can use classes as the preferred static contract."""
        flowsy_content = """name: Class Contract Validation
context_in:
  email: EmailContract

nodes:
  test_node:
    actions:
      - text = email.text
      - email.reply("Thanks")
"""
        import tempfile

        class EmailContract:
            text: str

            def reply(self, text: str) -> None:
                self.text = text

        with tempfile.NamedTemporaryFile(mode="w", suffix=".flowsy", delete=False) as f:
            f.write(flowsy_content)
            temp_path = Path(f.name)

        try:
            result = Flow.validate(temp_path, context_in={"email": EmailContract})
            assert result.is_valid, f"Expected valid, got errors: {result.errors}"
        finally:
            temp_path.unlink()

    def test_context_in_instances_still_validate_for_backwards_compatibility(self):
        """Test that existing instance-based validation remains valid."""
        flowsy_content = """name: Instance Contract Validation
context_in:
  email: EmailContract

nodes:
  test_node:
    actions:
      - text = email.text
      - email.reply("Thanks")
"""
        import tempfile

        class EmailContract:
            def __init__(self):
                self.text = "hello"

            def reply(self, text: str) -> None:
                self.text = text

        with tempfile.NamedTemporaryFile(mode="w", suffix=".flowsy", delete=False) as f:
            f.write(flowsy_content)
            temp_path = Path(f.name)

        try:
            result = Flow.validate(temp_path, context_in={"email": EmailContract()})
            assert result.is_valid, f"Expected valid, got errors: {result.errors}"
        finally:
            temp_path.unlink()

    def test_context_in_class_type_mismatch_is_reported(self):
        """Test type name checks for class-based validation."""
        flowsy_content = """name: Class Mismatch Validation
context_in:
  email: EmailContract

nodes:
  test_node:
"""
        import tempfile

        class OtherContract:
            pass

        with tempfile.NamedTemporaryFile(mode="w", suffix=".flowsy", delete=False) as f:
            f.write(flowsy_content)
            temp_path = Path(f.name)

        try:
            result = Flow.validate(temp_path, context_in={"email": OtherContract})
            assert not result.is_valid
            assert any("Type mismatch" in error.message for error in result.errors)
        finally:
            temp_path.unlink()

    def test_stochastic_node_validates_agent_and_requests(self):
        """Test valid stochastic node validation."""
        flowsy_content = """name: Stochastic Validation
context_in:
  consc: MockAgent

nodes:
  summarize:
    type: stochastic
    agent: consc
    requests:
      - "Create a report."
    output: report
    message: agent_message
    edges:
      - success == True: send_report
  send_report:
    actions:
      - result = len(report)
"""
        import tempfile

        class MockAgent:
            def run(self, request, options=None):
                return request

        with tempfile.NamedTemporaryFile(mode="w", suffix=".flowsy", delete=False) as f:
            f.write(flowsy_content)
            temp_path = Path(f.name)

        try:
            result = Flow.validate(temp_path, context_in={"consc": MockAgent()})
            assert result.is_valid, f"Expected valid, got errors: {result.errors}"
        finally:
            temp_path.unlink()

    def test_stochastic_node_validates_agent_class(self):
        """Test that stochastic agent validation supports class contracts."""
        flowsy_content = """name: Stochastic Class Validation
context_in:
  consc: MockAgent

nodes:
  summarize:
    type: stochastic
    agent: consc
    requests:
      - "Create a report."
"""
        import tempfile

        class MockAgent:
            def run(self, request: str, options: dict | None = None) -> str:
                return request

        with tempfile.NamedTemporaryFile(mode="w", suffix=".flowsy", delete=False) as f:
            f.write(flowsy_content)
            temp_path = Path(f.name)

        try:
            result = Flow.validate(temp_path, context_in={"consc": MockAgent})
            assert result.is_valid, f"Expected valid, got errors: {result.errors}"
        finally:
            temp_path.unlink()

    def test_stochastic_node_reports_unknown_agent(self):
        """Test that stochastic nodes require an agent from context_in."""
        flowsy_content = """name: Stochastic Validation
context_in:
  email: Email

nodes:
  summarize:
    type: stochastic
    agent: consc
    requests:
      - "Create a report."
"""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".flowsy", delete=False) as f:
            f.write(flowsy_content)
            temp_path = Path(f.name)

        try:
            result = Flow.validate(temp_path)
            assert not result.is_valid
            assert any("Stochastic agent 'consc'" in e.message for e in result.errors)
        finally:
            temp_path.unlink()

    def test_stochastic_node_reports_missing_run_method(self):
        """Test that provided stochastic agents must expose run(...)."""
        flowsy_content = """name: Stochastic Validation
context_in:
  consc: BrokenAgent

nodes:
  summarize:
    type: stochastic
    agent: consc
    requests:
      - "Create a report."
"""
        import tempfile

        class BrokenAgent:
            pass

        with tempfile.NamedTemporaryFile(mode="w", suffix=".flowsy", delete=False) as f:
            f.write(flowsy_content)
            temp_path = Path(f.name)

        try:
            result = Flow.validate(temp_path, context_in={"consc": BrokenAgent()})
            assert not result.is_valid
            assert any("run(...)" in e.message for e in result.errors)
        finally:
            temp_path.unlink()


class TestBuildRegistry:
    """Tests for _build_registry helper function."""

    def test_build_registry_with_contrib(self):
        """Test that _build_registry includes contrib action types."""
        from agy.validation import _build_registry

        registry = _build_registry()

        # Should include contrib functions
        assert "classify" in registry or "extract" in registry or "respond" in registry

    def test_build_registry_with_custom_action_type(self):
        """Test that _build_registry includes custom action types."""
        from agy.action_type import ActionType
        from agy.validation import _build_registry

        def custom_func(x: int) -> int:
            """Custom func.

            Args:
                x: x.

            Returns:
                int: Operation result.
            """
            return x * 2

        custom_action = ActionType(
            object_name="global_function",
            method_name="custom_action",
            callable=custom_func,
        )
        registry = _build_registry([custom_action])

        assert "custom_action" in registry
