"""
Unit tests for the utils functions in auto_semver.cli.utils module.

This module contains comprehensive tests for all utility functions in the CLI module,
especially focusing on the is_finalized function which determines the workflow path.
"""

from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from auto_semver.adapters.github.event import GitHubEvent
from auto_semver.cli.utils import is_finalized, promotion_prefer_source_paths
from auto_semver.config import Config
from auto_semver.config.constants import PR_HIDDEN_MARKER
from auto_semver.core.semver import SemverLock, Version


class TestIsFinalized:
    """Test cases for is_finalized() function."""

    @pytest.fixture
    def mock_event(self, github_event: Any) -> None:
        """Create a GitHubEvent instance for finalization tests."""
        # Create a customized event for finalization tests with hidden marker in body
        github_event.create(
            title="Release 1.0.0",
            body=f"This is a test PR body\n{PR_HIDDEN_MARKER}",
            labels=["semver-bump"],
        )

    @pytest.fixture
    def mock_config(self, mocker: MockerFixture) -> Any:
        """Create a mock Config instance."""
        mock = mocker.Mock(spec=Config)
        mock_data = mocker.Mock()
        mock.data = mock_data

        # Set up pull_request mock
        mock_pull_request = mocker.Mock()
        mock_pull_request.labels = ["semver-bump"]
        mock_pull_request.render_title.return_value = "Release 1.0.0"
        mock_pull_request.render_body.return_value = "Release notes"
        mock.data.pull_request = mock_pull_request

        return mock

    @pytest.fixture
    def mock_semver_lock(self, mocker: MockerFixture) -> None:
        """Mock SemverLock.load_from_file to return a predetermined version."""
        mock_lock = mocker.Mock(spec=SemverLock)
        mock_lock.version = Version(major=1, minor=0, patch=0)
        mocker.patch.object(SemverLock, "load_from_file", return_value=mock_lock)

    @pytest.mark.unit
    def test_is_finalized_true(
        self, mock_event: None, mock_config: Any, mock_semver_lock: None
    ) -> None:
        """Test when PR matches expected finalized state."""
        # Use real GitHubEvent instance
        event = GitHubEvent()  # Will read from the mocked environment

        # All conditions match, should return True
        result = is_finalized(config=mock_config, event=event)

        assert result is True

    @pytest.mark.unit
    def test_is_finalized_missing_labels(
        self, github_event: Any, mock_config: Any, mock_semver_lock: None
    ) -> None:
        """Test when PR is missing expected labels."""
        # Create event with no labels
        github_event.create(
            title="Release 1.0.0",
            body=f"This is a test PR body\n{PR_HIDDEN_MARKER}",
            labels=[],  # No labels
        )
        event = GitHubEvent()  # Create real instance from the mock environment

        # Configure config to expect multiple labels
        mock_config.data.pull_request.labels = ["semver-bump", "automatic"]

        result = is_finalized(config=mock_config, event=event)

        assert result is False

    @pytest.mark.unit
    def test_is_finalized_title_mismatch(
        self, github_event: Any, mock_config: Any, mock_semver_lock: None
    ) -> None:
        """Title is not part of finalize identity — date-rich titles still match."""
        github_event.create(
            title="Release candidate 1.0.0 — 19-09-2026",
            body=f"This is a test PR body\n{PR_HIDDEN_MARKER}",
            labels=["semver-bump"],
        )

        event = GitHubEvent()
        mock_config.data.pull_request.render_title.return_value = "Release 1.0.0"

        result = is_finalized(config=mock_config, event=event)

        assert result is True

    @pytest.mark.unit
    def test_is_finalized_with_date_in_title_template(
        self, github_event: Any, mock_config: Any, mock_semver_lock: None
    ) -> None:
        """A title that was rendered with {{date}} is still recognised as finalized."""
        github_event.create(
            title="Release 1.0.0 (19-09-2026)",
            body=f"notes\n{PR_HIDDEN_MARKER}",
            labels=["semver-bump"],
        )
        event = GitHubEvent()
        # Simulate what a naive re-render with date="" would produce — must not matter
        mock_config.data.pull_request.render_title.return_value = "Release 1.0.0 ()"

        assert is_finalized(config=mock_config, event=event) is True

    @pytest.mark.unit
    def test_is_finalized_missing_marker(
        self, github_event: Any, mock_config: Any, mock_semver_lock: None
    ) -> None:
        """Test when PR body is missing the hidden marker."""
        # Create event with body missing the marker
        github_event.create(
            title="Release 1.0.0",
            body="This is a PR without the hidden marker",  # No marker
            labels=["semver-bump"],
        )

        event = GitHubEvent()

        result = is_finalized(config=mock_config, event=event)

        assert result is False

    @pytest.mark.unit
    def test_is_finalized_multiple_reasons(
        self,
        github_event: Any,
        mock_config: Any,
        mock_semver_lock: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test when PR fails multiple finalization checks."""
        # Create event that fails on labels + marker (title is no longer checked)
        github_event.create(
            title="Wrong title",
            body="Body without marker",
            labels=[],
        )

        event = GitHubEvent()

        # Configure expected values
        mock_config.data.pull_request.labels = ["semver-bump", "automatic"]

        caplog.set_level("DEBUG")
        result = is_finalized(config=mock_config, event=event)

        assert result is False
        # Check logs to ensure remaining reasons were logged
        assert "Missing labels" in caplog.text
        assert "Body mismatch" in caplog.text
        assert "Title mismatch" not in caplog.text


class TestPromotionPreferSourcePaths:
    """Tests for promotion conflict allowlist helper."""

    @pytest.mark.unit
    def test_includes_lock_changelog_and_version_files(self, mocker: MockerFixture) -> None:
        """Allowlist should cover semver metadata files that diverge during promotion."""
        mock_config = mocker.Mock(spec=Config)
        mock_data = mocker.Mock()
        mock_data.version_files = ["version.txt", "pyproject.toml"]
        mock_changelog = mocker.Mock()
        mock_changelog.file = Path("CHANGELOG.md")
        mock_data.changelog = mock_changelog
        mock_config.data = mock_data

        paths = promotion_prefer_source_paths(mock_config)

        assert paths == [".semver.lock", "CHANGELOG.md", "version.txt", "pyproject.toml"]
