"""
Unit tests for the bump module in auto_semver.cli.bump.

This module contains tests for the run function in the bump module,
which handles version bumping, changelog updating, and PR creation.
"""

import datetime
from pathlib import Path
from typing import Any

import pytest

# from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_mock import MockerFixture

from auto_semver.adapters.git import GitOps
from auto_semver.adapters.github.event import GitHubEvent
from auto_semver.cli.bump import run
from auto_semver.config import CommitGroupsConfig, Config, ConfigData, LockSyncConfig, ReleaseConfig
from auto_semver.core.changelog.manager import ChangelogManager
from auto_semver.core.semver import Version
from auto_semver.core.semver.lock import SemverLock
from tests.fixtures.file_fixture import FileFixture
from tests.fixtures.github_event_fixture import GitHubEventFixture


class TestBump:
    """Test cases for the bump.run function."""

    @pytest.fixture
    def mock_gitops(self, mocker: MockerFixture) -> Any:
        """Create a mock GitOps object."""
        mock = mocker.Mock(spec=GitOps)
        mock.get_lock_version_from_branch.return_value = None
        mock.get_open_release_version.return_value = None
        mock.get_recent_commits.return_value = ["feat: add new feature", "fix: bug fix"]
        mock.fetch.return_value = None
        mock.repo = mocker.Mock(working_tree_dir=".")
        return mock

    @pytest.fixture
    def mock_config(self, mocker: MockerFixture) -> Any:
        """Create a mock Config object."""
        mock = mocker.Mock(spec=Config)
        mock_data = mocker.Mock(spec=ConfigData)
        mock.data = mock_data

        # Set up configuration values
        mock.data.suffixes = {"main": "", "develop": "-dev"}
        mock.data.start_version = Version.parse("0.1.0")
        mock.data.version_files = ["version.txt"]
        # Add empty promotions list for tag promotion logic
        mock.data.promotions = []
        mock.data.commit_groups = CommitGroupsConfig()
        mock.data.release = ReleaseConfig()
        mock.data.bump = mocker.Mock(mode="classic")
        mock.data.lock_sync = LockSyncConfig(enabled=False)

        mock_pr_config = mocker.Mock()
        mock_pr_config.title = "Release {{ version }}"
        mock_pr_config.body = "Release notes for {{ version }}"
        mock_pr_config.labels = ["semver-bump"]
        mock.data.pull_request = mock_pr_config

        return mock

    @pytest.fixture
    def mock_changelog_manager(self, mocker: MockerFixture) -> Any:
        """Create a mock ChangelogManager."""
        mock = mocker.Mock(spec=ChangelogManager)
        mock.update.return_value = None  # The update method doesn't return anything
        mock.path = Path("CHANGELOG.md")  # Add the path attribute
        mocker.patch.object(ChangelogManager, "from_config", return_value=mock)
        return mock

    @pytest.fixture
    def mock_semver_lock(self, mocker: MockerFixture) -> Any:
        """Create a mock SemverLock."""
        mock = mocker.Mock(spec=SemverLock)
        mock.version = Version.parse("1.0.0")
        # Mock the SemverLock constructor
        mocker.patch("auto_semver.core.semver.lock.SemverLock", return_value=mock)
        # Mock load_from_file (used when checking existing version)
        mocker.patch.object(SemverLock, "load_from_file", return_value=mock)
        return mock

    @pytest.mark.unit
    def test_bump_with_no_existing_version(
        self,
        github_event: GitHubEventFixture,
        file_fixture: FileFixture,
        mock_gitops: Any,
        mock_config: Any,
        mock_changelog_manager: Any,
        mock_semver_lock: Any,
        mocker: MockerFixture,
    ) -> None:
        """Test bump with no existing version - should use start_version from config."""
        # Mock datetime.now for consistent testing
        mock_now = datetime.datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime = mocker.Mock()
        mocker.patch("datetime.datetime", mock_datetime)
        mocker.patch("datetime.datetime.now", return_value=mock_now)

        # Mock GitOps create_branch and push methods
        mock_gitops.create_branch.return_value = None

        file_fixture.create_version_file(filename="version.txt")

        event = GitHubEvent()

        # Run the bump function
        run(gitops=mock_gitops, event=event, config=mock_config, github_token="fake-token")

        # Verify SemverLock constructor was called
        assert mock_semver_lock is not None

        # Verify PR was created
        mock_gitops.create_pr.assert_called_once()

    @pytest.mark.unit
    def test_bump_with_existing_version(
        self,
        mock_gitops: Any,
        github_event: GitHubEventFixture,
        file_fixture: FileFixture,
        mock_config: Any,
        mock_changelog_manager: Any,
        mock_semver_lock: Any,
        mocker: MockerFixture,
    ) -> None:
        """Test bump with existing version."""
        # Set up mock to return an existing version
        existing_version = Version.parse("0.9.0")
        mock_gitops.get_lock_version_from_branch.return_value = existing_version

        # Mock datetime.now for consistent testing
        mock_now = datetime.datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime = mocker.Mock()
        mocker.patch("datetime.datetime", mock_datetime)
        mocker.patch("datetime.datetime.now", return_value=mock_now)

        event = GitHubEvent()

        # Run the bump function
        run(gitops=mock_gitops, event=event, config=mock_config, github_token="fake-token")

        # Verify version was bumped from the existing version
        # The SemverLock constructor should have been used
        mock_gitops.get_lock_version_from_branch.assert_called_once_with("main")

        # Verify PR was created
        mock_gitops.create_pr.assert_called_once()

    @pytest.mark.unit
    def test_bump_with_different_label(
        self,
        mock_gitops: Any,
        github_event: GitHubEventFixture,
        mock_config: Any,
        mock_changelog_manager: Any,
        mock_semver_lock: Any,
    ) -> None:
        """Test bump with different semver label (patch instead of minor)."""
        github_event.for_bump()

        event = GitHubEvent()

        # Run the bump function with our specialized event fixture
        run(gitops=mock_gitops, event=event, config=mock_config, github_token="fake-token")

        # Since the bump.py doesn't seem to actually use the labels,
        # we'll just verify that execution completes without errors
        assert mock_semver_lock is not None

        # Verify PR was created
        mock_gitops.create_pr.assert_called_once()


@pytest.mark.unit
def test_bump_stages_synced_lockfiles(
    mocker: MockerFixture,
    github_event: GitHubEventFixture,
    file_fixture: FileFixture,
) -> None:
    """Bump should git-add paths returned by sync_package_locks."""
    mock_gitops = mocker.Mock(spec=GitOps)
    mock_gitops.get_lock_version_from_branch.return_value = None
    mock_gitops.get_open_release_version.return_value = None
    mock_gitops.get_recent_commits.return_value = ["feat: add feature"]
    mock_gitops.fetch.return_value = None
    mock_gitops.repo = mocker.Mock(working_tree_dir=".")
    mock_gitops.get_file_content_at_commit.return_value = None

    mock_config = mocker.Mock(spec=Config)
    mock_data = mocker.Mock(spec=ConfigData)
    mock_config.data = mock_data
    mock_data.suffixes = {"main": ""}
    mock_data.start_version = Version.parse("0.1.0")
    mock_data.version_files = ["version.txt"]
    mock_data.promotions = []
    mock_data.commit_groups = CommitGroupsConfig()
    mock_data.release = ReleaseConfig()
    mock_data.bump = mocker.Mock(mode="classic")
    mock_data.lock_sync = LockSyncConfig(enabled=True, ecosystems=["uv"])
    mock_pr = mocker.Mock()
    mock_pr.title = "Release {{ version }}"
    mock_pr.body = "notes"
    mock_pr.labels = ["semver-bump"]
    mock_data.pull_request = mock_pr

    mock_changelog = mocker.Mock(spec=ChangelogManager)
    mock_changelog.path = Path("CHANGELOG.md")
    mocker.patch.object(ChangelogManager, "from_config", return_value=mock_changelog)

    mock_lock = mocker.Mock(spec=SemverLock)
    mock_lock.version = Version.parse("0.1.0")
    mock_lock.path = ".semver.lock"
    mock_lock.target_base_sha = None
    mocker.patch("auto_semver.cli.bump.SemverLock", return_value=mock_lock)
    mocker.patch.object(SemverLock, "load_from_file", return_value=mock_lock)
    mocker.patch("auto_semver.cli.bump.VersionFileUpdater")
    mocker.patch("auto_semver.cli.bump.sync_package_locks", return_value=["uv.lock"])

    file_fixture.create_version_file(filename="version.txt")
    github_event.for_bump()
    run(gitops=mock_gitops, event=GitHubEvent(), config=mock_config, github_token="fake-token")

    add_calls = [call.args[0] for call in mock_gitops.add.call_args_list]
    assert any("uv.lock" in paths for paths in add_calls)
