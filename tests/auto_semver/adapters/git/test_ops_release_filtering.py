"""Tests for internal/release commit filtering logic in GitOps."""

from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock

import pytest

from auto_semver.adapters.git import GitOps
from auto_semver.config import Config

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestGitOpsInternalCommitFiltering:
    """Test suite for internal commit filtering in GitOps."""

    @pytest.fixture
    def mock_repo(self, mocker: "MockerFixture") -> MagicMock:
        """Mock git repository instance."""
        # Create the mock repo object
        mock_repo = mocker.MagicMock()

        # Configure the remote mock
        mock_remote = mocker.MagicMock()
        mock_remote.configure_mock(url="https://github.com/owner/repo.git")

        # Configure repo.remote() to return our remote mock
        mock_repo.remote.return_value = mock_remote

        # Other necessary attributes
        mock_repo.working_tree_dir = "/tmp/repo"
        mock_repo.config_writer.return_value.__enter__.return_value = MagicMock()
        mock_repo.config_reader.return_value.__enter__.return_value = MagicMock()

        # Patch the Repo class to return our mock instance
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        return cast("MagicMock", mock_repo)

    @pytest.mark.unit
    def test_filter_internal_commits_with_config_prefix(self, mock_repo: MagicMock) -> None:
        """Test filtering when config provides a specific prefix."""
        # Initialize GitOps
        # The __init__ will call Repo(), which returns mock_repo.
        # Then _parse_repository_name calls mock_repo.remote("origin").url
        gitops = GitOps(repo_path=".", ensure_safe=False)

        # Mock config
        mock_config = MagicMock(spec=Config)
        mock_config.data = MagicMock()
        mock_config.data.pull_request = MagicMock()
        mock_config.data.pull_request.get_release_commit_prefix.return_value = "MyRelease "

        messages = ["feat: new feature", "MyRelease 1.2.0", "fix: bug fix", "MyRelease 1.1.0"]

        filtered = gitops._filter_internal_commits(messages, mock_config)

        assert len(filtered) == 2
        assert "feat: new feature" in filtered
        assert "fix: bug fix" in filtered
        assert "MyRelease 1.2.0" not in filtered

    @pytest.mark.unit
    def test_filter_internal_commits_fallback(self, mock_repo: MagicMock) -> None:
        """Test filtering falls back to 'Release ' when config returns None."""
        gitops = GitOps(repo_path=".", ensure_safe=False)

        # Mock config to return None for prefix
        mock_config = MagicMock(spec=Config)
        mock_config.data = MagicMock()
        mock_config.data.pull_request = MagicMock()
        mock_config.data.pull_request.get_release_commit_prefix.return_value = None

        messages = ["feat: cool stuff", "Release 1.2.0", "chore: cleanup", "Release 1.0.0"]

        filtered = gitops._filter_internal_commits(messages, mock_config)

        assert len(filtered) == 2

        # Case specific checks
        assert "feat: cool stuff" in filtered
        assert "chore: cleanup" in filtered
        assert "Release 1.2.0" not in filtered
        assert "Release 1.0.0" not in filtered

    @pytest.mark.unit
    def test_filter_internal_commits_drops_housekeeping(self, mock_repo: MagicMock) -> None:
        """Housekeeping finalize/metadata commits are dropped; unrelated chores stay."""
        gitops = GitOps(repo_path=".", ensure_safe=False)

        mock_config = MagicMock(spec=Config)
        mock_config.data = MagicMock()
        mock_config.data.pull_request = MagicMock()
        mock_config.data.pull_request.get_release_commit_prefix.return_value = "Release "

        messages = [
            "feat: add verified REST fallback",
            "chore: finalize semver lock for 1.6.15-dev",
            "chore: update version metadata for 1.6.16-rc",
            "chore: cleanup",
            "Release 1.6.15-dev",
        ]

        filtered = gitops._filter_internal_commits(messages, mock_config)

        assert filtered == [
            "feat: add verified REST fallback",
            "chore: cleanup",
        ]
