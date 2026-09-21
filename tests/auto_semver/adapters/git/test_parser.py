"""Tests for the CommitParser class."""

import logging

import pytest

from auto_semver.core.commits.parser import CommitParser


class TestCommitParser:
    """Test suite for CommitParser."""

    def setup_method(self) -> None:
        """Set up the parser for tests."""
        self.parser = CommitParser()

    def test_parse_type_1_simple_header(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test Type 1: Simple header commit."""
        message = "Add new feature"
        with caplog.at_level(logging.DEBUG, logger="auto_semver.core.commits.parser"):
            result = self.parser.parse(message)

        assert result.header == "Add new feature"
        assert result.body is None
        assert result.bullet_points == []
        assert result.sectioned_changes == {}
        assert any("Parsed commit" in r.message for r in caplog.records)

    def test_parse_type_2_header_and_body(self) -> None:
        """Test Type 2: Commit with header and body (prose)."""
        message = """Fix login bug

This fixes the issue where users could not login.
It was caused by a database timeout."""

        result = self.parser.parse(message)

        assert result.header == "Fix login bug"
        assert result.body is not None
        assert "This fixes the issue" in result.body
        # Should be no items as there are no bullets
        assert result.bullet_points == []
        assert result.sectioned_changes == {}

    def test_parse_type_3_header_and_list(self) -> None:
        """Test Type 3: Commit with header and list of changes."""
        message = """Update dependencies

- Upgrade pytorch to 2.0
- Upgrade numpy
- Remove unused lib"""

        result = self.parser.parse(message)

        assert result.header == "Update dependencies"
        assert len(result.bullet_points) == 3
        assert result.bullet_points[0] == "Upgrade pytorch to 2.0"
        assert result.bullet_points[1] == "Upgrade numpy"
        assert result.bullet_points[2] == "Remove unused lib"
        assert result.sectioned_changes == {}

    def test_parse_type_4_header_and_groups(self) -> None:
        """Test Type 4: Commit with header and complex body (groups)."""
        message = """Release v1.0.0

Features:
- Add dark mode
- Add user profile

Bug Fixes:
- Fix crash on startup
"""

        result = self.parser.parse(message)

        assert result.header == "Release v1.0.0"

        # Check Sections
        assert "Features" in result.sectioned_changes
        assert "Bug Fixes" in result.sectioned_changes

        # Features group
        assert len(result.sectioned_changes["Features"]) == 2
        assert result.sectioned_changes["Features"][0] == "Add dark mode"
        assert result.sectioned_changes["Features"][1] == "Add user profile"

        # Bug Fixes group
        assert len(result.sectioned_changes["Bug Fixes"]) == 1
        assert result.sectioned_changes["Bug Fixes"][0] == "Fix crash on startup"

    def test_parse_mixed_content(self) -> None:
        """Test parsing with mixed content (prose and lists)."""
        message = """Refactor core logic

This is a major refactor.

Core:
- Rename class A to B

API:
- Update endpoint /v1"""

        result = self.parser.parse(message)

        assert result.header == "Refactor core logic"
        assert "Core" in result.sectioned_changes
        assert "API" in result.sectioned_changes
        assert result.sectioned_changes["Core"][0] == "Rename class A to B"
        assert result.sectioned_changes["API"][0] == "Update endpoint /v1"

    def test_parse_numbered_list(self) -> None:
        """Test parsing of numbered lists (e.g. 1. Item)."""
        message = """Steps to reproduce:
1. Open app
2. Click button
3. Crash"""
        result = self.parser.parse(message)

        # "Steps to reproduce:" is the commit header because it's the first line.
        # The body contains the numbered list, which are simple bullet points.
        assert result.header == "Steps to reproduce:"
        assert len(result.bullet_points) == 3
        assert result.bullet_points[0] == "Open app"
        assert result.bullet_points[1] == "Click button"
        assert result.bullet_points[2] == "Crash"
        assert result.sectioned_changes == {}

    def test_parse_multiline_bullets(self) -> None:
        """Test parsing bullet points that span multiple lines."""
        message = """Fixed parsing issue
- Previously, it might have been falling back to default GITHUB_TOKEN
  when the token was not provided explicitly.
- Another point
  that also spans
  multiple lines."""

        result = self.parser.parse(message)

        assert result.header == "Fixed parsing issue"
        assert len(result.bullet_points) == 2
        assert (
            result.bullet_points[0]
            == "Previously, it might have been falling back to default GITHUB_TOKEN "
            "when the token was not provided explicitly."
        )
        assert result.bullet_points[1] == "Another point that also spans multiple lines."

    def test_parse_multiline_groups_complex(self) -> None:
        """Test parsing complex structure with sections and multiline bullets."""
        message = """Pass GitHub token to release action

Workflows:
- Update publish-staging.yml
  to pass github_token
- Update publish-production.yml
  to pass github_token

Bug Fix:
- Fixes HTTP 403 Forbidden error when creating releases
  - Ensures gh-release action has correct permissions via App token"""

        result = self.parser.parse(message)

        assert result.header == "Pass GitHub token to release action"

        # Check Workflows section
        assert "Workflows" in result.sectioned_changes
        assert len(result.sectioned_changes["Workflows"]) == 2
        assert (
            result.sectioned_changes["Workflows"][0]
            == "Update publish-staging.yml to pass github_token"
        )
        assert (
            result.sectioned_changes["Workflows"][1]
            == "Update publish-production.yml to pass github_token"
        )

        # Check Bug Fix section
        assert "Bug Fix" in result.sectioned_changes
        # Since the second line starts with '-', it currently gets treated as a new list item by the regex
        # even if indented. The parser is simple and sees `- ...`.
        assert len(result.sectioned_changes["Bug Fix"]) == 2
        assert (
            result.sectioned_changes["Bug Fix"][0]
            == "Fixes HTTP 403 Forbidden error when creating releases"
        )
        assert (
            result.sectioned_changes["Bug Fix"][1]
            == "Ensures gh-release action has correct permissions via App token"
        )
