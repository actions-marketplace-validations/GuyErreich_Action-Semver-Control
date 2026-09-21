"""Unit tests for the GitOps class push failure scenarios."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from git import Repo
from git.remote import PushInfo
from pytest_mock import MockerFixture

from auto_semver.adapters.git.ops import GitOps


class TestGitOpsPushFailure:
    """Test cases for the GitOps class push failure scenarios."""

    @pytest.fixture
    def mock_repo(self, mocker: MockerFixture) -> Any:
        """Create a mock Git repository."""
        mock = mocker.MagicMock(spec=Repo)
        mock.git = mocker.MagicMock()
        mock_remote = mocker.MagicMock()
        mock_remote.url = "git@github.com:owner/repo.git"
        mock.remote.return_value = mock_remote
        mock.config_writer.return_value.get_values.return_value = []
        return mock

    @pytest.fixture(autouse=True)
    def patch_github(self, mocker: MockerFixture) -> Any:
        """Patch the Github class."""
        return mocker.patch("auto_semver.adapters.git.verified.Github")

    @pytest.fixture(autouse=True)
    def patch_parse_repository_name(self, mocker: MockerFixture) -> Any:
        """Patch _parse_repository_name."""
        return mocker.patch(
            "auto_semver.adapters.git.local.GitLocal._parse_repository_name",
            return_value="owner/repo",
        )

    def test_push_rejected(self, mocker: MockerFixture, mock_repo: Any) -> None:
        """Test that a rejected push raises a RuntimeError."""
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # Create a mock PushInfo with REJECTED flag
        mock_push_info = MagicMock(spec=PushInfo)
        mock_push_info.flags = PushInfo.REJECTED
        mock_push_info.summary = "Rejected (non-fast-forward)"

        # Set up the remote to return this push info
        mock_repo.remote.return_value.push.return_value = [mock_push_info]

        gitops = GitOps()

        with pytest.raises(RuntimeError, match=r"Push failed.*Rejected"):
            gitops.push(branch_name="test-branch")

    def test_push_error(self, mocker: MockerFixture, mock_repo: Any) -> None:
        """Test that a push with ERROR flag raises a RuntimeError."""
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # Create a mock PushInfo with ERROR flag
        mock_push_info = MagicMock(spec=PushInfo)
        mock_push_info.flags = PushInfo.ERROR
        mock_push_info.summary = "Remote error"

        # Set up the remote to return this push info
        mock_repo.remote.return_value.push.return_value = [mock_push_info]

        gitops = GitOps()

        with pytest.raises(RuntimeError, match=r"Push failed.*Remote error"):
            gitops.push(branch_name="test-branch")

    def test_push_remote_rejected(self, mocker: MockerFixture, mock_repo: Any) -> None:
        """Test that a push with REMOTE_REJECTED flag raises a RuntimeError."""
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        mock_push_info = MagicMock(spec=PushInfo)
        # Simulate REMOTE_REJECTED
        mock_push_info.flags = PushInfo.REMOTE_REJECTED
        mock_push_info.summary = "Remote rejected (pre-receive hook declined)"

        mock_repo.remote.return_value.push.return_value = [mock_push_info]

        gitops = GitOps()

        with pytest.raises(RuntimeError, match=r"Push failed.*Remote rejected"):
            gitops.push(branch_name="test-branch")

    def test_push_success(self, mocker: MockerFixture, mock_repo: Any) -> None:
        """Test that a successful push does not raise."""
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        mock_push_info = MagicMock(spec=PushInfo)
        mock_push_info.flags = PushInfo.FAST_FORWARD
        mock_push_info.summary = "Success"

        mock_repo.remote.return_value.push.return_value = [mock_push_info]

        gitops = GitOps()
        gitops.push(branch_name="test-branch")
