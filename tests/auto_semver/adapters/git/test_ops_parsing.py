"""Tests for GitOps parsing functionality."""

import pytest
from git import Repo
from pytest_mock import MockerFixture

from auto_semver.adapters.git.ops import GitOps


class TestGitOpsParsing:
    """Test cases for repository parsing in GitOps class."""

    def test_parse_repository_name_ssh(self, mocker: MockerFixture) -> None:
        """Test parsing of SSH repository URL."""
        mock_repo = mocker.MagicMock(spec=Repo)
        mock_remote = mocker.MagicMock()
        mock_remote.url = "git@github.com:owner/repo.git"
        mock_repo.remote.return_value = mock_remote
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # We need to ensure we don't init the full object which might do other things,
        # but _parse_repository_name is called in __init__.
        # So we can just init GitOps.

        # We also need to mock Github auth probably if it happens in init
        mocker.patch("auto_semver.adapters.git.verified.Github")

        ops = GitOps()
        assert ops._repo_full_name == "owner/repo"

    def test_parse_repository_name_https(self, mocker: MockerFixture) -> None:
        """Test parsing of HTTPS repository URL."""
        mock_repo = mocker.MagicMock(spec=Repo)
        mock_remote = mocker.MagicMock()
        mock_remote.url = "https://github.com/owner/repo.git"
        mock_repo.remote.return_value = mock_remote
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        mocker.patch("auto_semver.adapters.git.verified.Github")

        ops = GitOps()
        assert ops._repo_full_name == "owner/repo"

    def test_parse_repository_name_https_with_token(self, mocker: MockerFixture) -> None:
        """Test parsing of HTTPS repository URL with token."""
        mock_repo = mocker.MagicMock(spec=Repo)
        mock_remote = mocker.MagicMock()
        mock_remote.url = "https://x-access-token:token@github.com/owner/repo.git"
        mock_repo.remote.return_value = mock_remote
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        mocker.patch("auto_semver.adapters.git.verified.Github")

        ops = GitOps()
        assert ops._repo_full_name == "owner/repo"

    def test_parse_repository_name_https_with_stateless_jwt_token(
        self, mocker: MockerFixture
    ) -> None:
        """Stateless ghs_ JWT tokens (~520 chars, with dots) must not break URL parsing."""
        header = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
        payload = "eyJpc3MiOiIxMjM0NSJ9"
        signature = "A" * 452
        token = f"ghs_12345_{header}.{payload}.{signature}"
        assert len(token) >= 520
        assert token.count(".") == 2

        mock_repo = mocker.MagicMock(spec=Repo)
        mock_remote = mocker.MagicMock()
        mock_remote.url = f"https://x-access-token:{token}@github.com/owner/repo.git"
        mock_repo.remote.return_value = mock_remote
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        mocker.patch("auto_semver.adapters.git.verified.Github")

        ops = GitOps()
        assert ops._repo_full_name == "owner/repo"
        assert ops.get_repository_name() == "owner/repo"
        assert token in mock_remote.url

    def test_parse_repository_name_https_with_user_pass(self, mocker: MockerFixture) -> None:
        """Test parsing of HTTPS repository URL with username and password."""
        mock_repo = mocker.MagicMock(spec=Repo)
        mock_remote = mocker.MagicMock()
        mock_remote.url = "https://user:password@github.com/owner/repo.git"
        mock_repo.remote.return_value = mock_remote
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        mocker.patch("auto_semver.adapters.git.verified.Github")

        ops = GitOps()
        assert ops._repo_full_name == "owner/repo"

    def test_parse_repository_name_failure(self, mocker: MockerFixture) -> None:
        """Test parsing failure for non-GitHub URL."""
        mock_repo = mocker.MagicMock(spec=Repo)
        mock_remote = mocker.MagicMock()
        mock_remote.url = "https://gitlab.com/owner/repo.git"
        mock_repo.remote.return_value = mock_remote
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        mocker.patch("auto_semver.adapters.git.verified.Github")

        with pytest.raises(ValueError, match="Unable to parse GitHub repository"):
            GitOps()

    def test_parse_repository_name_failure_redacts_token(self, mocker: MockerFixture) -> None:
        """Tokens in remote URLs must never appear in raised ValueError messages."""
        token = "x-access-token:ghs_SUPER_SECRET_TOKEN_DO_NOT_LEAK"
        mock_repo = mocker.MagicMock(spec=Repo)
        mock_remote = mocker.MagicMock()
        mock_remote.url = f"https://{token}@gitlab.com/owner/repo.git"
        mock_repo.remote.return_value = mock_remote
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        mocker.patch("auto_semver.adapters.git.verified.Github")

        with pytest.raises(ValueError) as exc_info:
            GitOps()

        message = str(exc_info.value)
        assert "ghs_SUPER_SECRET_TOKEN_DO_NOT_LEAK" not in message
        assert "x-access-token" not in message
        assert "gitlab.com/owner/repo.git" in message
