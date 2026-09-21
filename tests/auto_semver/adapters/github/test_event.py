"""
Unit tests for the GitHubEvent class in auto_semver.adapters.github.event module.

This module contains comprehensive tests for all methods and functionality
of the GitHubEvent class, including event data loading and accessing specific
pull request information.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from auto_semver.adapters.github.event import _GITHUB_EVENT_PATH_ENV, GitHubEvent
from tests.fixtures.github_event_fixture import GitHubEventFixture
from tests.fixtures.github_event_helpers import GitHubPullRequestEventData


@pytest.fixture
def mock_pr_event() -> Any:
    """Return a mock PR event object."""
    # Using the GitHubPullRequestEventData utility class
    event_data = GitHubPullRequestEventData(
        title="Add new feature",
        body="This PR adds a new feature",
        source_branch="feature/new-feature",
        target_branch="main",
        source_sha="abc123head",
        target_sha="def456base",
        merge_commit_sha="abc123merge",
        merged=True,
        labels=["enhancement", "semver:minor"],
        repository="owner/repo",
    )
    # Parse the JSON string back to a dictionary
    return json.loads(event_data.to_event_dict())


@pytest.fixture
def mock_event_path(tmp_path: Path, mock_pr_event: dict[str, Any]) -> Path:
    """Create a mock event file and return its path."""
    event_file = tmp_path / "github_event.json"
    event_file.write_text(json.dumps(mock_pr_event))
    return event_file


class TestGitHubEventInit:
    """Test cases for GitHubEvent.__init__() and _load_event_data()."""

    @pytest.mark.unit
    def test_init_loads_event_data(
        self, mocker: MockerFixture, mock_event_path: Path, mock_pr_event: dict[str, Any]
    ) -> None:
        """Test GitHubEvent initialization loads data from the event file."""
        mocker.patch.dict(os.environ, {_GITHUB_EVENT_PATH_ENV: str(mock_event_path)})

        event = GitHubEvent()

        assert event._event_data == mock_pr_event

    @pytest.mark.unit
    def test_init_missing_env_var(self, mocker: MockerFixture) -> None:
        """Test initialization when GITHUB_EVENT_PATH env var is missing."""
        mocker.patch.dict(os.environ, {_GITHUB_EVENT_PATH_ENV: ""}, clear=True)

        with pytest.raises(
            RuntimeError, match=f"{_GITHUB_EVENT_PATH_ENV} is not set in environment"
        ):
            GitHubEvent()

    @pytest.mark.unit
    def test_init_file_not_found(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Test initialization when event file doesn't exist."""
        non_existent_path = tmp_path / "non_existent.json"
        mocker.patch.dict(os.environ, {_GITHUB_EVENT_PATH_ENV: str(non_existent_path)})

        with pytest.raises(RuntimeError, match="Failed to load GitHub event data"):
            GitHubEvent()

    @pytest.mark.unit
    def test_init_invalid_json(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Test initialization when event file contains invalid JSON."""
        invalid_json_path = tmp_path / "invalid.json"
        invalid_json_path.write_text("{ invalid: json }")
        mocker.patch.dict(os.environ, {_GITHUB_EVENT_PATH_ENV: str(invalid_json_path)})

        with pytest.raises(RuntimeError, match="Failed to load GitHub event data"):
            GitHubEvent()


class TestGitHubEventGetMethod:
    """Test cases for GitHubEvent._get() private method."""

    @pytest.mark.unit
    def test_get_valid_path(self, mocker: MockerFixture, mock_event_path: Path) -> None:
        """Test getting a value from a valid path in the event data."""
        mocker.patch.dict(os.environ, {_GITHUB_EVENT_PATH_ENV: str(mock_event_path)})
        event = GitHubEvent()

        result = event._get(["pull_request", "merged"])

        assert result is True

    @pytest.mark.unit
    def test_get_invalid_path(self, mocker: MockerFixture, mock_event_path: Path) -> None:
        """Test getting a value from an invalid path in the event data."""
        mocker.patch.dict(os.environ, {_GITHUB_EVENT_PATH_ENV: str(mock_event_path)})
        event = GitHubEvent()

        with pytest.raises(RuntimeError, match="Malformed event data: missing"):
            event._get(["pull_request", "non_existent"])


class TestGitHubEventMergeStatus:
    """Test cases for GitHubEvent.is_merged() method."""

    @pytest.mark.unit
    def test_is_merged_true(self, mocker: MockerFixture, mock_event_path: Path) -> None:
        """Test when PR is merged."""
        mocker.patch.dict(os.environ, {_GITHUB_EVENT_PATH_ENV: str(mock_event_path)})
        event = GitHubEvent()

        assert event.is_merged() is True

    @pytest.mark.unit
    def test_is_merged_false(
        self, mocker: MockerFixture, mock_event_path: Path, mock_pr_event: dict[str, Any]
    ) -> None:
        """Test when PR is not merged."""
        mock_pr_event["pull_request"]["merged"] = False

        # Create updated event file
        updated_event_path = Path(str(mock_event_path) + ".updated")
        updated_event_path.write_text(json.dumps(mock_pr_event))

        mocker.patch.dict(os.environ, {_GITHUB_EVENT_PATH_ENV: str(updated_event_path)})
        event = GitHubEvent()

        assert event.is_merged() is False


class TestGitHubEventBranchAndCommitInfo:
    """Test cases for branch and commit info methods."""

    @pytest.mark.unit
    def test_get_source_branch_name(self, github_event: GitHubEventFixture) -> None:
        """Test getting source branch name."""
        github_event.create(source_branch="feature/new-feature")
        event = GitHubEvent()

        assert event.get_source_branch_name() == "feature/new-feature"

    @pytest.mark.unit
    def test_get_source_commit_sha(self, github_event: GitHubEventFixture) -> None:
        """Test getting source commit SHA."""
        github_event.create(source_sha="abc123head")
        event = GitHubEvent()

        assert event.get_source_commit_sha() == "abc123head"

    @pytest.mark.unit
    def test_get_target_branch_name(self, github_event: GitHubEventFixture) -> None:
        """Test getting target branch name."""
        github_event.create(target_branch="main")
        event = GitHubEvent()

        assert event.get_target_branch_name() == "main"

    @pytest.mark.unit
    def test_get_target_commit_sha(self, github_event: GitHubEventFixture) -> None:
        """Test getting target commit SHA."""
        github_event.create(target_sha="def456base")
        event = GitHubEvent()

        assert event.get_target_commit_sha() == "def456base"

    @pytest.mark.unit
    def test_get_merged_commit_sha(self, github_event: GitHubEventFixture) -> None:
        """Test getting merged commit SHA when PR is merged."""
        github_event.create(merge_commit_sha="abc123merge", merged=True)
        event = GitHubEvent()

        assert event.get_merged_commit_sha() == "abc123merge"

    @pytest.mark.unit
    def test_get_merged_commit_sha_not_merged(self, github_event: GitHubEventFixture) -> None:
        """Test getting merged commit SHA when PR is not merged raises error."""
        github_event.create(merge_commit_sha="abc123merge", merged=False)
        event = GitHubEvent()

        with pytest.raises(RuntimeError, match="The pull request was closed but not merged"):
            event.get_merged_commit_sha()


class TestGitHubEventPRInfo:
    """Test cases for PR info methods: title, body, labels."""

    @pytest.mark.unit
    def test_get_title(self, github_event: GitHubEventFixture) -> None:
        """Test getting PR title."""
        github_event.create(title="Add new feature")
        event = GitHubEvent()

        assert event.get_title() == "Add new feature"

    @pytest.mark.unit
    def test_get_body(self, github_event: GitHubEventFixture) -> None:
        """Test getting PR body."""
        github_event.create(body="This PR adds a new feature")
        event = GitHubEvent()

        assert event.get_body() == "This PR adds a new feature"

    @pytest.mark.unit
    def test_get_labels(self, github_event: GitHubEventFixture) -> None:
        """Test getting PR labels."""
        github_event.create(labels=["enhancement", "semver:minor"])
        event = GitHubEvent()

        assert event.get_labels() == ["enhancement", "semver:minor"]

    @pytest.mark.unit
    def test_get_labels_empty(self, github_event: GitHubEventFixture) -> None:
        """Test getting PR labels when none exist raises ValueError."""
        github_event.create(labels=[])
        event = GitHubEvent()

        with pytest.raises(ValueError, match="No labels found"):
            event.get_labels()

    @pytest.mark.unit
    def test_get_labels_safe_with_labels(self, github_event: GitHubEventFixture) -> None:
        """Test getting PR labels safely when labels exist."""
        github_event.create(labels=["enhancement", "semver:minor"])
        event = GitHubEvent()

        assert event.get_labels_safe() == ["enhancement", "semver:minor"]

    @pytest.mark.unit
    def test_get_labels_safe_no_labels(self, github_event: GitHubEventFixture) -> None:
        """Test getting PR labels safely when no labels exist returns empty list."""
        github_event.create(labels=[])
        event = GitHubEvent()

        assert event.get_labels_safe() == []


class TestGitHubEventRepository:
    """Test cases for repository info methods."""

    @pytest.mark.unit
    def test_get_repository(self, github_event: GitHubEventFixture) -> None:
        """Test getting repository full name."""
        github_event.create(repository="owner/repo")
        event = GitHubEvent()

        assert event.get_repository() == "owner/repo"
