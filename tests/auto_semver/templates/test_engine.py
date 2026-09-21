"""
Unit tests for the TemplateEngine class.

Tests the centralized Jinja2 template engine with pluggable custom functions,
filters, and template validation functionality.
"""

from datetime import datetime
from typing import Any, cast

import pytest
from jinja2 import TemplateSyntaxError
from jinja2.exceptions import SecurityError

from auto_semver.templates import (
    TemplateEngine,
    TemplateFunction,
    TemplateVariables,
    get_template_engine,
    reset_template_engine,
)


class TestTemplateEngine:
    """Test cases for TemplateEngine class functionality."""

    def setup_method(self) -> None:
        """Reset the global template engine before each test."""
        reset_template_engine()

    @pytest.mark.unit
    def test_engine_initialization(self) -> None:
        """Test basic template engine initialization."""
        engine = TemplateEngine()

        # Check that built-in functions are registered
        functions = engine.list_functions()
        assert "format_date" in functions
        assert "title_case" in functions
        assert "list_join" in functions
        assert "truncate_text" in functions
        assert "pluralize" in functions
        assert "format_date_custom" in functions

    @pytest.mark.unit
    def test_sandbox_blocks_attribute_escape(self) -> None:
        """Consumer templates must not reach object subclasses via attribute access."""
        engine = TemplateEngine()
        with pytest.raises(SecurityError):
            engine.render_template("{{ ''.__class__.__mro__[1].__subclasses__() }}", {})

    @pytest.mark.unit
    def test_reset_engine(self) -> None:
        """Test that reset_template_engine creates a new instance."""
        engine1 = get_template_engine()
        reset_template_engine()
        engine2 = get_template_engine()

        assert engine1 is not engine2

    @pytest.mark.unit
    def test_register_custom_function(self) -> None:
        """Test registering a custom function."""
        engine = TemplateEngine()

        def custom_func(text: str) -> str:
            return f"custom: {text}"

        engine.register_function("custom_func", custom_func)

        # Check function is registered
        assert "custom_func" in engine.list_functions()

        # Test using the function in a template
        result = engine.render_template("{{ custom_func('test') }}", {})
        assert result == "custom: test"

    @pytest.mark.unit
    def test_register_multiple_functions(self) -> None:
        """Test registering multiple functions at once."""
        engine = TemplateEngine()

        functions: dict[str, TemplateFunction] = {
            "func1": lambda x: f"func1: {x}",
            "func2": lambda x: f"func2: {x}",
        }

        engine.register_functions(functions)

        assert "func1" in engine.list_functions()
        assert "func2" in engine.list_functions()

        result = engine.render_template("{{ func1('test') }} - {{ func2('test') }}", {})
        assert result == "func1: test - func2: test"

    @pytest.mark.unit
    def test_unregister_function(self) -> None:
        """Test unregistering a custom function."""
        engine = TemplateEngine()

        engine.register_function("test_func", lambda x: x)
        assert "test_func" in engine.list_functions()

        result = engine.unregister_function("test_func")
        assert result is True
        assert "test_func" not in engine.list_functions()

        # Test unregistering non-existent function
        result = engine.unregister_function("non_existent")
        assert result is False

    @pytest.mark.unit
    def test_builtin_format_date(self) -> None:
        """Test built-in format_date function."""
        engine = TemplateEngine()

        # Test with string date
        result = engine.render_template("{{ format_date('2024-12-25', '%B %d, %Y') }}", {})
        assert result == "December 25, 2024"

        # Test with datetime object
        date_obj = datetime(2024, 12, 25)
        result = engine.render_template(
            "{{ format_date(date_obj, '%B %d, %Y') }}", {"date_obj": date_obj}
        )
        assert result == "December 25, 2024"

    @pytest.mark.unit
    def test_builtin_title_case(self) -> None:
        """Test built-in title_case function."""
        engine = TemplateEngine()

        result = engine.render_template("{{ title_case('hello world') }}", {})
        assert result == "Hello World"

    @pytest.mark.unit
    def test_builtin_list_join(self) -> None:
        """Test built-in list_join function."""
        engine = TemplateEngine()

        result = engine.render_template("{{ list_join(['a', 'b', 'c'], ' - ') }}", {})
        assert result == "a - b - c"

    @pytest.mark.unit
    def test_builtin_truncate_text(self) -> None:
        """Test built-in truncate_text function."""
        engine = TemplateEngine()

        result = engine.render_template("{{ truncate_text('hello world', 8, '...') }}", {})
        assert result == "hello..."

    @pytest.mark.unit
    def test_builtin_pluralize(self) -> None:
        """Test built-in pluralize function."""
        engine = TemplateEngine()

        # Test singular
        result = engine.render_template("{{ pluralize(1, 'item', 'items') }}", {})
        assert result == "item"

        # Test plural
        result = engine.render_template("{{ pluralize(2, 'item', 'items') }}", {})
        assert result == "items"

        # Test auto-plural (add 's')
        result = engine.render_template("{{ pluralize(2, 'item') }}", {})
        assert result == "items"

    @pytest.mark.unit
    def test_render_template_basic(self) -> None:
        """Test basic template rendering."""
        engine = TemplateEngine()

        result = engine.render_template(
            "Version: {{ version }}, Date: {{ date }}", {"version": "1.0.0", "date": "2024-12-25"}
        )
        assert result == "Version: 1.0.0, Date: 2024-12-25"

    @pytest.mark.unit
    def test_render_template_syntax_error(self) -> None:
        """Test template rendering with syntax error."""
        engine = TemplateEngine()

        with pytest.raises(TemplateSyntaxError):
            engine.render_template("{{ invalid syntax", {})

    @pytest.mark.unit
    def test_validate_template_valid(self) -> None:
        """Test template validation with valid template."""
        engine = TemplateEngine()

        # Valid template should not raise any exception
        try:
            engine.validate_template("{{ version }} - {{ date }}")
        except Exception as e:
            pytest.fail(f"Valid template should not raise exception: {e}")

    @pytest.mark.unit
    def test_validate_template_invalid(self) -> None:
        """Test template validation with invalid template."""
        engine = TemplateEngine()

        # Invalid template should raise TemplateSyntaxError
        with pytest.raises(TemplateSyntaxError):
            engine.validate_template("{{ invalid syntax")

    @pytest.mark.unit
    def test_extract_template_variables(self) -> None:
        """Test extracting variables from a template."""
        engine = TemplateEngine()

        variables = engine.extract_template_variables(
            "Hello {{ name }}, version {{ version }} released on {{ date }}"
        )
        assert variables == ["date", "name", "version"]  # sorted

    @pytest.mark.unit
    def test_extract_template_variables_complex(self) -> None:
        """Test extracting variables from a complex template."""
        engine = TemplateEngine()

        template = """
        ## Version {{ version }}
        {% for item in items %}
        - {{ item.name }}: {{ item.value }}
        {% endfor %}
        Released: {{ date }}
        """

        variables = engine.extract_template_variables(template)
        # Should find template variables (including loop variables in Jinja2 AST)
        assert "version" in variables
        assert "items" in variables
        assert "date" in variables
        # Note: Jinja2 AST includes loop variables, so 'item' will be present

    @pytest.mark.unit
    def test_compare_templates_identical(self) -> None:
        """Test comparing identical templates."""
        engine = TemplateEngine()

        template1 = "{{ version }} - {{ date }}"
        template2 = "{{ version }} - {{ date }}"

        assert engine.compare_templates(template1, template2) is True

    @pytest.mark.unit
    def test_compare_templates_different(self) -> None:
        """Test comparing different templates."""
        engine = TemplateEngine()

        template1 = "{{ version }} - {{ date }}"
        template2 = "{{ version }} + {{ date }}"

        assert engine.compare_templates(template1, template2) is False

    @pytest.mark.unit
    def test_compare_templates_whitespace_difference(self) -> None:
        """Test comparing templates with different whitespace."""
        engine = TemplateEngine()

        template1 = "{{version}}-{{date}}"
        template2 = "{{ version }} - {{ date }}"

        # Templates are structurally different due to different literal content
        # The AST comparison is strict about whitespace in literals
        assert engine.compare_templates(template1, template2) is False

    @pytest.mark.unit
    def test_get_template_with_source(self) -> None:
        """Test creating template with source retention."""
        engine = TemplateEngine()

        template_str = "Version: {{ version }}"
        template, _name = engine.get_template_with_source(template_str, "test_template")

        assert template.name == "test_template"

        # Test retrieving source
        source = engine.get_template_source(template)
        assert source == template_str

    @pytest.mark.unit
    def test_has_required_variables_success(self) -> None:
        """Test checking required variables when all are present."""
        engine = TemplateEngine()

        template_str = "{{ version }} - {{ date }}"
        variables: TemplateVariables = {"version": "1.0.0", "date": "2024-12-25", "extra": "value"}

        result = engine.has_required_variables(template_str, variables)
        assert result is True

    @pytest.mark.unit
    def test_has_required_variables_failure(self) -> None:
        """Test checking required variables when some are missing."""
        engine = TemplateEngine()

        template_str = "{{ version }} - {{ date }}"
        variables: TemplateVariables = {"version": "1.0.0"}  # Missing 'date'

        result = engine.has_required_variables(template_str, variables)
        assert result is False

    @pytest.mark.unit
    def test_complex_template_with_functions(self) -> None:
        """Test rendering a complex template with multiple functions."""
        engine = TemplateEngine()

        template = """
        # Release {{ version }} ({{ format_date(date, '%B %d, %Y') }})
        
        {% for message in messages %}
        - {{ title_case(truncate_text(message, 50)) }}
        {% endfor %}
        
        Total: {{ pluralize(messages|length, 'commit') }}
        """

        variables: TemplateVariables = {
            "version": "1.2.0",
            "date": "2024-12-25",
            "messages": [
                "fix: resolve bug in authentication",
                "feat: add new dashboard feature with comprehensive user interface",
            ],
        }

        result = engine.render_template(template, variables)

        # Check key parts of the rendered template
        assert "# Release 1.2.0 (December 25, 2024)" in result
        assert "Fix: Resolve Bug In Authentication" in result
        assert "Feat: Add New Dashboard Feature With Comprehens..." in result  # Actual truncation
        assert "Total: commits" in result


class TestTemplateEngineWithCommitGroups:
    """Test cases for TemplateEngine with CommitGroup types."""

    def setup_method(self) -> None:
        """Reset the global template engine before each test."""
        reset_template_engine()

    @pytest.mark.unit
    def test_function_returning_commit_group(self) -> None:
        """Test function that returns CommitGroup type."""
        engine = TemplateEngine()

        # Mock CommitGroup-like object for testing
        class MockCommitGroup:
            def __init__(self, title: str, pattern: str, commits: list[str]) -> None:
                self.title = title
                self.pattern = pattern
                self.commits = commits

        def mock_group_function(messages: list[str]) -> list[MockCommitGroup]:
            """Mock function that returns CommitGroup-like list."""
            return [
                MockCommitGroup(
                    title="Features", pattern=r"^feat:", commits=["feat: add new feature"]
                )
            ]

        engine.register_function("group_commits", cast("Any", mock_group_function))

        # This should work without type errors
        template_str = (
            "{% for group in group_commits(['feat: add new feature']) %}"
            "{{ group.title }}: {{ group.commits|length }}"
            "{% endfor %}"
        )
        result = engine.render_template(template_str, {})
        assert "Features: 1" in result

    @pytest.mark.unit
    def test_function_returning_grouped_messages(self) -> None:
        """Test function that returns GroupedMessages type."""
        engine = TemplateEngine()

        # Mock GroupedMessages-like object for testing
        class MockGroupedMessages:
            def __init__(self, data: dict[str, list[Any]]) -> None:
                self.grouped_messages = data.get("grouped_messages", [])
                self.ungrouped_messages = data.get("ungrouped_messages", [])

        def mock_grouped_function(messages: list[str]) -> MockGroupedMessages:
            """Mock function that returns GroupedMessages-like object."""
            return MockGroupedMessages(
                {
                    "grouped_messages": [{"title": "Features", "commits": ["feat: add feature"]}],
                    "ungrouped_messages": [],
                }
            )

        engine.register_function("group_messages", cast("Any", mock_grouped_function))

        # This should work without type errors
        result = engine.render_template(
            "{{ group_messages(['feat: add feature']).grouped_messages|length }}", {}
        )
        assert "1" in result

    @pytest.mark.unit
    def test_get_static_prefix(self) -> None:
        """Test extracting static prefix from templates."""
        engine = TemplateEngine()

        # Case 1: Simple prefix
        assert engine.get_static_prefix("Release {{version}}") == "Release "

        # Case 2: No prefix (starts with var)
        assert engine.get_static_prefix("{{version}} release") is None

        # Case 3: Prefix with newline
        assert engine.get_static_prefix("Release \n {{version}}") == "Release \n "

        # Case 4: Complex prefix
        assert engine.get_static_prefix("Bump to version: {{version}}") == "Bump to version: "
