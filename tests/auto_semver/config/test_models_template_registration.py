"""
Unit tests for config model template function registration.

Tests that the _ChangelogConfig and _PullRequestConfig models properly
register their template functions automatically on instantiation.
"""

from pathlib import Path

import pytest
from jinja2 import TemplateSyntaxError

from auto_semver.config import ChangelogConfig, PullRequestConfig, PullRequestTemplateVars
from auto_semver.core.changelog.manager import ChangelogManager
from auto_semver.templates.engine import get_template_engine, reset_template_engine


class TestChangelogConfigTemplateRegistration:
    """Test template function registration in ChangelogConfig."""

    def setup_method(self) -> None:
        """Reset the global template engine before each test."""
        reset_template_engine()

    @pytest.mark.unit
    def test_changelog_config_auto_registers_functions(self) -> None:
        """Test that ChangelogManager registers changelog template functions."""
        # Reset the engine to clean state
        reset_template_engine()

        # Get initial functions
        engine = get_template_engine()
        functions_before = set(engine.list_functions())

        # Create changelog manager (should trigger registration)
        _manager = ChangelogManager(
            path=Path("test.md"), truncate=False, template="test", header="", footer=""
        )

        # After creating manager, changelog functions should be registered
        # Use the same engine instance to check for new functions
        functions_after = set(engine.list_functions())
        new_functions = functions_after - functions_before

        assert "format_date_changelog" in new_functions
        # Note: title_case is already a built-in function, so not in new_functions

    @pytest.mark.unit
    def test_changelog_template_functions_work(self) -> None:
        """Test that registered changelog template functions work correctly."""
        # Create ChangelogManager to register functions
        _manager = ChangelogManager(
            path=Path("test.md"), truncate=False, template="test", header="", footer=""
        )
        engine = get_template_engine()

        # Test format_date_changelog function
        result = engine.render_template(
            "{{ format_date_changelog('2024-12-25', '%B %d, %Y') }}", {}
        )
        assert result == "December 25, 2024"

        # Test title_case function
        result = engine.render_template("{{ title_case('hello world') }}", {})
        assert result == "Hello World"

    @pytest.mark.unit
    def test_changelog_template_functions_as_filters(self) -> None:
        """Test that changelog functions work as filters too."""
        # Create ChangelogManager to register functions
        _manager = ChangelogManager(
            path=Path("test.md"), truncate=False, template="test", header="", footer=""
        )
        engine = get_template_engine()

        # Test format_date_changelog as function
        result = engine.render_template(
            "{{ format_date_changelog('2024-12-25', '%B %d, %Y') }}", {}
        )
        assert result == "December 25, 2024"

        # Test title_case as function
        result = engine.render_template("{{ title_case('hello world') }}", {})
        assert result == "Hello World"

    @pytest.mark.unit
    def test_changelog_config_template_validation(self) -> None:
        """Test that changelog config validates templates using the engine."""
        # This should work (valid template)
        _config = ChangelogConfig(template="## [{{ version }}] - {{ date }}")

        # Test validation by setting template after initialization
        _config2 = ChangelogConfig()
        engine = get_template_engine()

        # This should raise an exception for invalid template syntax
        with pytest.raises(TemplateSyntaxError):
            engine.validate_template("## [{{ version ] - {{ date }}")  # Missing closing brace

    @pytest.mark.unit
    def test_multiple_changelog_configs_share_functions(self) -> None:
        """Test that multiple changelog configs share the same registered functions."""
        _config1 = ChangelogConfig()
        _config2 = ChangelogConfig()

        engine = get_template_engine()

        # Both configs should be able to use the same functions
        result1 = engine.render_template("{{ title_case('test1') }}", {})
        result2 = engine.render_template("{{ title_case('test2') }}", {})

        assert result1 == "Test1"
        assert result2 == "Test2"


class TestPullRequestConfigTemplateRegistration:
    """Test template function registration in _PullRequestConfig."""

    def setup_method(self) -> None:
        """Reset the global template engine before each test."""
        reset_template_engine()

    @pytest.mark.unit
    def test_pr_config_does_not_register_on_construction(self) -> None:
        """PullRequestConfig must not mutate the global engine as a construction side effect."""
        engine = get_template_engine()
        # Functions are already built-ins on a fresh engine
        assert "format_date_custom" in engine.list_functions()
        before = set(engine.list_functions())
        _config = PullRequestConfig()
        assert set(engine.list_functions()) == before

    @pytest.mark.unit
    def test_pr_template_functions_work(self) -> None:
        """Test that registered PR template functions work correctly."""
        engine = get_template_engine()

        # Test truncate_commit function
        result = engine.render_template(
            "{{ truncate_commit('This is a very long commit message that should be truncated', 20) }}",
            {},
        )
        assert result == "This is a very lo..."

        # Test conventional_type function
        result = engine.render_template("{{ conventional_type('feat: add new feature') }}", {})
        assert result == "feat"

        # Test capitalize_first function
        result = engine.render_template("{{ capitalize_first('hello world') }}", {})
        assert result == "Hello world"

    @pytest.mark.unit
    def test_format_date_custom_accepts_day_first_date(self) -> None:
        """%d-%m-%Y strings (as bump supplies) must format, not raise."""
        engine = get_template_engine()
        result = engine.render_template(
            "{{ format_date_custom('19-09-2026', '%Y-%m-%d') }}",
            {},
        )
        assert result == "2026-09-19"

    @pytest.mark.unit
    def test_pr_template_functions_as_filters(self) -> None:
        """Test that PR functions work as filters too."""
        _config = PullRequestConfig()
        engine = get_template_engine()

        # Test truncate_commit as function
        result = engine.render_template("{{ truncate_commit('This is a long message', 10) }}", {})
        assert result == "This is..."

        # Test conventional_type as function
        result = engine.render_template("{{ conventional_type('fix: resolve bug') }}", {})
        assert result == "fix"

    @pytest.mark.unit
    def test_pr_config_template_validation(self) -> None:
        """Test that PR config validates templates using the engine."""
        # This should work (valid templates)
        _config = PullRequestConfig(title="Release {{ version }}", body="Released on {{ date }}")

        # Test validation using engine directly
        _config2 = PullRequestConfig()
        engine = get_template_engine()

        # This should raise an exception for invalid template syntax
        with pytest.raises(TemplateSyntaxError):
            engine.validate_template("Release {{ version")  # Missing closing brace

    @pytest.mark.unit
    def test_pr_render_methods_use_engine(self) -> None:
        """Test that PR config render methods use the centralized engine."""
        config = PullRequestConfig(
            title="Release {{ version }} ({{ capitalize_first('major') }})",
            body="Commits: {{ count_commits(groups) }}",
        )

        # Test render_title
        vars = PullRequestTemplateVars(version="1.2.0", date="2025-01-01", messages=[])
        title = config.render_title(vars)
        assert title == "Release 1.2.0 (Major)"

        # For this test, we'll test with empty variables since the template function is being tested
        # The count_commits function expects groups but this tests the function registration
        body_vars = PullRequestTemplateVars(version="0.0.0", date="2025-01-01", messages=[])
        body = config.render_body(body_vars)
        # Should contain the PR hidden marker, but groups will be empty so count will be 0
        assert "Commits: 0" in body
        assert "<!-- auto-semver:pr -->" in body


class TestConfigModelInteraction:
    """Test interaction between different config models."""

    def setup_method(self) -> None:
        """Reset the global template engine before each test."""
        reset_template_engine()

    @pytest.mark.unit
    def test_both_configs_register_together(self) -> None:
        """Test that both managers can register functions together."""
        # Create ChangelogManager to register changelog functions
        _changelog_manager = ChangelogManager(
            path=Path("test.md"), truncate=False, template="test", header="", footer=""
        )
        # PR functions are built into the engine; PullRequestConfig no longer registers
        _pr_config = PullRequestConfig()

        engine = get_template_engine()

        # Should have functions from both managers
        functions = engine.list_functions()

        # Changelog functions
        assert "format_date_changelog" in functions
        assert "title_case" in functions

        # PR functions
        assert "truncate_commit" in functions
        assert "conventional_type" in functions

        # Built-in functions should still be there
        assert "format_date" in functions
        assert "pluralize" in functions

    @pytest.mark.unit
    def test_function_name_conflicts_handled(self) -> None:
        """Test handling of function name conflicts between configs."""
        # Both configs register 'title_case' - last one should win
        _changelog_config = ChangelogConfig()  # Registers title_case
        _pr_config = PullRequestConfig()  # May also register title_case

        engine = get_template_engine()

        # Function should still work
        result = engine.render_template("{{ title_case('test') }}", {})
        assert result == "Test"

    @pytest.mark.unit
    def test_engine_reset_clears_config_functions(self) -> None:
        """Test that resetting engine clears config-registered functions."""
        # Register functions through configs
        _changelog_config = ChangelogConfig()
        _pr_config = PullRequestConfig()

        engine = get_template_engine()
        _functions_with_configs = set(engine.list_functions())

        # Reset engine
        reset_template_engine()
        new_engine = get_template_engine()
        functions_after_reset = set(new_engine.list_functions())

        # Changelog-manager registration is gone after reset
        assert "format_date_changelog" not in functions_after_reset

        # PR helpers are engine built-ins and remain after reset
        assert "truncate_commit" in functions_after_reset
        assert "format_date_custom" in functions_after_reset

        # Core built-in functions should still be there
        assert "format_date" in functions_after_reset
        assert "pluralize" in functions_after_reset
