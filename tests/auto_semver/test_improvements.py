"""
Test to demonstrate the improvements made to the auto-semver codebase.

This file showcases the enhanced error handling, type safety, shared utilities,
and comprehensive documentation added to the template system.
"""

from pathlib import Path

import pytest

from auto_semver.config.constants import PR_HIDDEN_MARKER
from auto_semver.core.changelog.manager import ChangelogManager
from auto_semver.core.pr.github_builder import (
    GitHubPRBuilder,
    GitHubPRTemplateVariables,
)
from auto_semver.templates.utils import (
    capitalize_first_letter,
    count_items_in_groups,
    extract_prefix_before_delimiter,
    format_date_iso_to_custom,
    has_keyword_in_group_titles,
    truncate_commit,
    truncate_text,
)


def test_enhanced_error_handling() -> None:
    """Test that our enhanced error handling provides clear error messages."""
    # Test ChangelogManager validation
    manager = ChangelogManager(
        path=Path("/tmp/test.md"),
        truncate=False,
        template="## [{{version}}] - {{date}}",
        header="",
        footer="",
    )

    # Should raise clear error for missing required variables
    with pytest.raises(ValueError, match="Missing required template variables: \\['version'\\]"):
        manager.render_template({"date": "2025-01-01"})

    # Test GitHubPRBuilder (validation not implemented yet, just test it works)
    # Builder should handle empty version gracefully
    data = GitHubPRTemplateVariables(
        version="",
        previous_version="1.0.0",
        commit_groups=[],
        breaking_changes=[],
        author="test-user",
        repository="test/repo",
        date="2025-01-01",
        branch="release/v1.0.0",
        base_branch="main",
    )
    builder = GitHubPRBuilder(
        data=data,
        title_template="Release {{version}}",
        body_template="Release notes for {{version}}",
    )
    assert builder.title == "Release "  # Empty version renders as empty string


def test_shared_template_utilities() -> None:
    """Test that shared utilities work correctly and consistently."""
    # Test date formatting
    assert format_date_iso_to_custom("2024-12-25", "%B %d, %Y") == "December 25, 2024"
    assert format_date_iso_to_custom("invalid-date") == "invalid-date"

    # Test text truncation
    assert truncate_text("This is a very long message", 20) == "This is a very lo..."
    assert truncate_text("Short", 20) == "Short"

    # Test first letter capitalization
    assert capitalize_first_letter("hello world") == "Hello world"
    assert capitalize_first_letter("") == ""

    # Test prefix extraction
    assert extract_prefix_before_delimiter("feat: add feature") == "feat"
    assert extract_prefix_before_delimiter("no delimiter") == "other"

    # Test commit counting
    groups = [{"commits": ["feat: a", "fix: b"]}, {"commits": ["docs: c"]}]
    assert count_items_in_groups(groups) == 3
    assert count_items_in_groups(None) == 0

    # Test keyword detection
    groups_with_breaking = [{"title": "Breaking Changes"}, {"title": "Features"}]
    assert has_keyword_in_group_titles(groups_with_breaking, ["breaking"])
    assert not has_keyword_in_group_titles(groups_with_breaking, ["docs"])


def test_template_variable_typing() -> None:
    """Test that template variables use proper type hints."""
    # This should work with proper typing
    data = GitHubPRTemplateVariables(
        version="1.2.3",
        previous_version="1.2.2",
        commit_groups=[],
        breaking_changes=[],
        author="test-user",
        repository="test/repo",
        date="2025-01-01",
        branch="release/v1.2.3",
        base_branch="main",
    )
    builder = GitHubPRBuilder(
        data=data,
        title_template="Release {{version}}",
        body_template="Body: {{version}}",
    )

    assert builder.title == "Release 1.2.3"
    assert builder.body == f"{PR_HIDDEN_MARKER}\nBody: 1.2.3"


def test_comprehensive_docstrings() -> None:
    """Test that functions have comprehensive docstrings with examples."""
    # Test that utility functions have proper docstrings
    assert format_date_iso_to_custom.__doc__ is not None
    assert "Examples:" in format_date_iso_to_custom.__doc__

    assert truncate_text.__doc__ is not None
    assert "Examples:" in truncate_text.__doc__

    # Create test data and builder to check docstrings
    data = GitHubPRTemplateVariables(
        version="1.0.0",
        previous_version="0.9.0",
        commit_groups=[],
        breaking_changes=[],
        author="test-user",
        repository="test/repo",
        date="2025-01-01",
        branch="release/v1.0.0",
        base_branch="main",
    )
    builder = GitHubPRBuilder(data)
    _ = builder  # ensure builder still constructs with shared engine functions
    assert truncate_commit.__doc__ is not None
    assert "Truncate" in truncate_commit.__doc__


def test_integration_with_shared_utilities() -> None:
    """Test that builders properly use shared utilities for consistency."""
    data = GitHubPRTemplateVariables(
        version="1.0.0",
        previous_version="0.9.0",
        commit_groups=[],
        breaking_changes=[],
        author="test-user",
        repository="test/repo",
        date="2025-01-01",
        branch="release/v1.0.0",
        base_branch="main",
    )
    builder = GitHubPRBuilder(
        data=data,
        title_template="{{ truncate_commit('This is a very long commit message', 20) }}",
        body_template="{{ format_date_custom('2024-12-25', '%B %d, %Y') }}",
    )

    # These should use the shared utilities internally
    assert builder.title == "This is a very lo..."
    assert builder.body == f"{PR_HIDDEN_MARKER}\nDecember 25, 2024"


if __name__ == "__main__":
    # Run tests to demonstrate improvements
    test_enhanced_error_handling()
    test_shared_template_utilities()
    test_template_variable_typing()
    test_comprehensive_docstrings()
    test_integration_with_shared_utilities()
    print("✅ All improvement tests passed!")
