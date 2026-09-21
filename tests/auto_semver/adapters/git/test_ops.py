"""
Unit tests for the GitOps class in auto_semver.adapters.git.ops module.

This module tests the functionality of the GitOps class which handles Git operations
such as branch creation, commit, push, tag, PR creation, and related operations.
"""

from pathlib import Path
from typing import Any

import pytest
from git import GitCommandError, Repo
from pytest_mock import MockerFixture

from auto_semver.adapters.git.ops import GitOps
from auto_semver.config.constants import PR_HIDDEN_MARKER
from auto_semver.core.semver import Version


class TestGitOps:
    """Test cases for the GitOps class."""

    @pytest.fixture
    def mock_repo(self, mocker: MockerFixture) -> Any:
        """Create a mock Git repository with a properly mocked remote."""
        mock = mocker.MagicMock(spec=Repo)
        mock.git = mocker.MagicMock()

        # Mock the remote with a valid URL for _parse_repository_name
        mock_remote = mocker.MagicMock()
        mock_remote.url = "git@github.com:owner/repo.git"
        mock.remote.return_value = mock_remote

        return mock

    @pytest.fixture
    def mock_config_writer(self, mocker: MockerFixture, mock_repo: Any) -> Any:
        """Create a mock Git config writer."""
        mock = mocker.MagicMock()
        mock.get_values.return_value = []
        mock_repo.config_writer.return_value = mock
        return mock

    @pytest.fixture
    def mock_github_repo(self, mocker: MockerFixture) -> Any:
        """Create a mock GitHub repository."""
        return mocker.MagicMock()

    @pytest.fixture
    def mock_github(self, mocker: MockerFixture, mock_github_repo: Any) -> Any:
        """Create a mock GitHub API client."""
        mock = mocker.MagicMock()
        mock.get_repo.return_value = mock_github_repo
        return mock

    @pytest.fixture(autouse=True)
    def patch_github(self, mocker: MockerFixture, mock_github: Any) -> Any:
        """Patch the Github class."""
        return mocker.patch("auto_semver.adapters.git.verified.Github", return_value=mock_github)

    @pytest.fixture(autouse=True)
    def patch_parse_repository_name(self, mocker: MockerFixture) -> Any:
        """Patch _parse_repository_name to avoid needing real remote URLs in all tests."""
        return mocker.patch(
            "auto_semver.adapters.git.local.GitLocal._parse_repository_name",
            return_value="owner/repo",
        )

    @pytest.mark.unit
    def test_init_with_ensure_safe(self, mocker: MockerFixture, mock_repo: Any) -> None:
        """Test that initializing with ensure_safe=True calls __ensure_git_safe_directory."""
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # Setup the repo working directory path
        mock_repo.working_tree_dir = "/mock/path"

        # Create GitOps instance with ensure_safe=True
        GitOps(ensure_safe=True)

        # Check that config_writer was called with global config
        mock_repo.config_writer.assert_called_once_with(config_level="global")

        # Check that the safe directory was added
        config_writer = mock_repo.config_writer.return_value
        config_writer.set_value.assert_called_once_with(
            section="safe", option="directory", value="/mock/path"
        )

    @pytest.mark.unit
    def test_init_with_ensure_safe_permission_error(
        self, mocker: MockerFixture, mock_repo: Any
    ) -> None:
        """Test that permission errors raise a RuntimeError immediately (no fallbacks)."""
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # Setup the repo working directory path
        mock_repo.working_tree_dir = "/mock/path"

        # Make config_writer raise a permission error
        mock_repo.config_writer.side_effect = PermissionError("Permission denied")

        # This should raise a RuntimeError immediately (simplified approach - no fallbacks)
        with pytest.raises(RuntimeError, match="Unable to configure git safe directory"):
            GitOps(ensure_safe=True)

        # Verify that config_writer was attempted
        mock_repo.config_writer.assert_called_once_with(config_level="global")

    @pytest.mark.unit
    def test_create_branch(self, mocker: MockerFixture) -> None:
        """Test creating a branch with the create_branch method."""
        # Create mocks
        mock_repo = mocker.MagicMock()
        mock_head = mocker.MagicMock()
        mock_repo.create_head.return_value = mock_head

        # Patch the Repo constructor
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # Create GitOps instance and call create_branch
        gitops = GitOps()
        gitops.create_branch(branch_name="test-branch")

        # Check that create_head and checkout were called correctly
        mock_repo.create_head.assert_called_once_with(path="test-branch")
        mock_head.checkout.assert_called_once()

    @pytest.mark.unit
    def test_create_branch_with_force(self, mocker: MockerFixture) -> None:
        """Test creating a branch with force=True."""
        # Create mocks
        mock_repo = mocker.MagicMock()
        mock_head = mocker.MagicMock()
        mock_existing_branch = mocker.MagicMock()
        mock_repo.create_head.return_value = mock_head

        # Setup branch exists and mock the existing branch
        mock_repo.heads.__contains__.return_value = True
        mock_repo.heads.__getitem__.return_value = mock_existing_branch

        # Patch the Repo constructor
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # Create GitOps instance and call create_branch with force=True
        gitops = GitOps()
        gitops.create_branch(branch_name="test-branch", force=True)

        # Check that the existing branch was deleted with force=True
        mock_existing_branch.delete.assert_called_once_with(repo=mock_repo, force=True)

        # Verify branch was created
        mock_repo.create_head.assert_called_once_with(path="test-branch")
        mock_head.checkout.assert_called_once()

    @pytest.mark.unit
    def test_add(self, mocker: MockerFixture) -> None:
        """Test adding files with the add method."""
        # Create mock repo
        mock_repo = mocker.MagicMock()
        # Mock the index to prevent 'add' from actually checking file existence
        mock_repo.index = mocker.MagicMock()
        # Mock is_dirty to return True (files need to be added)
        mock_repo.is_dirty.return_value = True

        # Patch the Repo constructor
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # Create GitOps instance and call add with file paths
        gitops = GitOps()
        files_list = ["file1.txt", Path("file2.txt")]  # List with mix of str and Path

        gitops.add(files=files_list)  # type: ignore

        # Check that index.add was called for each file
        assert mock_repo.index.add.call_count == 2
        # Check the first call (these should be the stringified versions of the paths)
        mock_repo.index.add.assert_any_call(items=["file1.txt"])
        mock_repo.index.add.assert_any_call(items=["file2.txt"])

    @pytest.mark.unit
    def test_commit(self, mocker: MockerFixture) -> None:
        """Local commit pins config identity and skips repository hooks."""
        mock_repo = mocker.MagicMock()
        mock_repo.index.diff.return_value = ["some_change"]

        mock_config = mocker.MagicMock()
        mock_config.get_value.side_effect = lambda _section, option: {
            "email": "test@example.com",
            "name": "Test User",
        }[option]
        mock_repo.config_reader.return_value.__enter__.return_value = mock_config

        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        gitops = GitOps()
        message = "Test commit message"
        gitops.commit(message=message)

        assert gitops._identity.name == "Test User"
        assert gitops._identity.email == "test@example.com"
        mock_repo.index.commit.assert_called_once_with(
            message,
            author=gitops._identity,
            committer=gitops._identity,
            skip_hooks=True,
        )

    @pytest.mark.unit
    def test_commit_uses_default_identity_when_config_write_fails(
        self, mocker: MockerFixture
    ) -> None:
        """Config write failure still commits with the default bot Actor."""
        mock_repo = mocker.MagicMock()
        mock_repo.index.diff.return_value = ["some_change"]

        mock_reader = mocker.MagicMock()
        mock_reader.get_value.side_effect = Exception("missing user identity")
        mock_repo.config_reader.return_value.__enter__.return_value = mock_reader

        mock_writer = mocker.MagicMock()
        mock_writer.__enter__.side_effect = OSError("read-only filesystem")
        mock_repo.config_writer.return_value = mock_writer

        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        gitops = GitOps()
        gitops.commit(message="chore: bump")

        assert gitops._identity.name == "auto-semver-bot[bot]"
        assert gitops._identity.email == "256984269+auto-semver-bot[bot]@users.noreply.github.com"
        mock_repo.index.commit.assert_called_once_with(
            "chore: bump",
            author=gitops._identity,
            committer=gitops._identity,
            skip_hooks=True,
        )

    @pytest.mark.unit
    def test_push(self, mocker: MockerFixture) -> None:
        """Test pushing changes with the push method."""
        # Create mock repo and remote
        mock_repo = mocker.MagicMock()
        mock_remote = mocker.MagicMock()
        mock_repo.remote.return_value = mock_remote

        # Patch the Repo constructor
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # Create GitOps instance and call push
        gitops = GitOps()
        gitops.push(branch_name="test-branch")

        # Check that remote and push were called correctly
        mock_repo.remote.assert_called_once_with(name="origin")
        mock_remote.push.assert_called_once_with(refspec="test-branch", force=False)

    @pytest.mark.unit
    def test_tag(self, mocker: MockerFixture) -> None:
        """Test tagging with the tag method."""
        # Create mock repo and tag
        mock_repo = mocker.MagicMock()
        mock_tag = mocker.MagicMock()
        mock_tag.name = "v1.0.0"
        mock_repo.create_tag.return_value = mock_tag

        # Patch the Repo constructor
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # Create GitOps instance and call tag
        gitops = GitOps()
        tag_name = gitops.tag(tag="v1.0.0", branch="main")

        # Check that create_tag was called correctly
        mock_repo.create_tag.assert_called_once_with(path="v1.0.0", ref="main", message="")
        assert tag_name == "v1.0.0"

    @pytest.mark.unit
    def test_create_pr_success(self, mocker: MockerFixture, mock_github_repo: Any) -> None:
        """Test creating a pull request with create_pr method."""
        # Set up the PR mock
        mock_pr = mocker.MagicMock()
        mock_pr.number = 123
        mock_github_repo.create_pull.return_value = mock_pr
        mock_github_repo.get_pulls.return_value = []

        # Patch the Github class (already done in patch_github fixture)

        # Create GitOps instance
        gitops = GitOps()

        # Mock get_repository_name to return a test repo
        mocker.patch.object(gitops, "get_repository_name", return_value="owner/repo")

        # Call create_pr
        pr_number = gitops.create_pr(
            github_token="token",
            title="Test PR",
            body="Test body",
            source="feature-branch",
            target="main",
            labels=["label1", "label2"],
        )

        # Check results
        assert pr_number == 123
        mock_github_repo.create_pull.assert_called_once_with(
            title="Test PR", body="Test body", head="feature-branch", base="main"
        )
        mock_pr.add_to_labels.assert_called_once_with("label1", "label2")

    @pytest.mark.unit
    def test_create_pr_existing(self, mocker: MockerFixture, mock_github_repo: Any) -> None:
        """Test create_pr when a PR already exists."""
        # Set up the existing PR mock
        mock_existing_pr = mocker.MagicMock()
        mock_existing_pr.number = 123
        mock_existing_pr.head.ref = "feature-branch"
        mock_existing_pr.base.ref = "main"
        mock_github_repo.get_pulls.return_value = [mock_existing_pr]

        # Create GitOps instance
        gitops = GitOps()

        # Mock get_repository_name to return a test repo
        mocker.patch.object(gitops, "get_repository_name", return_value="owner/repo")

        # Call create_pr
        pr_number = gitops.create_pr(
            github_token="token",
            title="Test PR",
            body="Test body",
            source="feature-branch",
            target="main",
        )

        # Check results
        assert pr_number == 123
        mock_github_repo.create_pull.assert_not_called()  # Should not create a new PR

    @pytest.mark.unit
    def test_close_old_release_prs(self, mocker: MockerFixture, mock_github_repo: Any) -> None:
        """Test closing old release PRs with close_old_release_prs method."""
        # Set up mock PRs
        mock_pr1 = mocker.MagicMock()
        mock_pr1.number = 1
        mock_pr1.head.ref = "release/v1.0.0"
        mock_pr1.base.ref = "main"
        mock_pr1.body = PR_HIDDEN_MARKER

        mock_label = mocker.MagicMock()
        mock_label.name = "semver-bump"
        mock_pr1.labels = [mock_label]

        mock_pr2 = mocker.MagicMock()
        mock_pr2.number = 2
        mock_pr2.head.ref = "feature/something"
        mock_pr2.base.ref = "main"
        mock_pr2.labels = []

        mock_github_repo.get_pulls.return_value = [mock_pr1, mock_pr2]

        gitops = GitOps()

        mocker.patch.object(gitops, "get_repository_name", return_value="owner/repo")
        mocker.patch.object(
            gitops,
            "_is_closeable_release_pr",
            return_value=(True, ""),
        )

        # Call close_old_release_prs
        gitops.close_old_release_prs(
            github_token="token",
            target_branch="main",
            labels=["semver-bump"],
        )

        # Check that the correct PR was closed
        mock_pr1.edit.assert_called_once_with(state="closed")
        mock_pr2.edit.assert_not_called()

    @pytest.mark.unit
    def test_close_old_release_prs_deletes_branch_when_configured(
        self, mocker: MockerFixture, mock_github_repo: Any
    ) -> None:
        """Superseded release branches are deleted when delete_branches is enabled."""
        mock_pr = mocker.MagicMock()
        mock_pr.number = 1
        mock_pr.head.ref = "auto-semver/release/1.4.1-dev"
        mock_pr.base.ref = "dev"
        mock_pr.body = PR_HIDDEN_MARKER
        mock_label = mocker.MagicMock()
        mock_label.name = "semver-bump"
        mock_pr.labels = [mock_label]
        mock_github_repo.get_pulls.return_value = [mock_pr]

        gitops = GitOps()
        mocker.patch.object(gitops, "get_repository_name", return_value="owner/repo")
        mocker.patch.object(gitops, "_is_closeable_release_pr", return_value=(True, ""))
        delete_mock = mocker.patch.object(gitops, "_delete_superseded_release_branch")

        gitops.close_old_release_prs(
            github_token="token",
            target_branch="dev",
            labels=["semver-bump"],
            delete_branches=True,
        )

        delete_mock.assert_called_once_with(branch_name="auto-semver/release/1.4.1-dev")

    @pytest.mark.unit
    def test_get_recent_commits(self, mocker: MockerFixture) -> None:
        """Test getting recent commits with get_recent_commits method."""
        # Create mock repo and commits
        mock_repo = mocker.MagicMock()
        mock_commit1 = mocker.MagicMock()
        mock_commit1.message = "Commit 1"
        mock_commit2 = mocker.MagicMock()
        mock_commit2.message = "Commit 2"
        mock_repo.iter_commits.return_value = [mock_commit2, mock_commit1]  # In reverse order

        # Patch the Repo constructor
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # Create GitOps instance
        gitops = GitOps()

        # Call get_recent_commits
        commits = gitops.get_recent_commits(commit_sha="abc123")

        # Check results
        assert commits == ["Commit 1", "Commit 2"]  # Should be in correct order
        mock_repo.git.rev_parse.assert_called_once_with("abc123")
        mock_repo.iter_commits.assert_called_once_with("abc123..HEAD")

    @pytest.mark.unit
    def test_get_lock_version_from_branch(self, mocker: MockerFixture) -> None:
        """Test getting the lock version from a specific branch."""
        # Create mock repo
        mock_repo = mocker.MagicMock()

        # Patch functions
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)

        # Mock lock file data
        lock_data = {"version": "1.2.3", "target_branch": "main", "source_branch": "develop"}
        mocker.patch("auto_semver.adapters.git.release_pr.yaml.safe_load", return_value=lock_data)

        # Mock SemverLock
        mock_version = mocker.MagicMock(spec=Version)
        mock_semver_lock = mocker.MagicMock(version=mock_version)
        mocker.patch(
            "auto_semver.adapters.git.release_pr.SemverLock.from_dict",
            return_value=mock_semver_lock,
        )

        # Create GitOps instance
        gitops = GitOps()

        # Call get_lock_version_from_branch
        version = gitops.get_lock_version_from_branch(branch_name="develop")

        # Check results
        assert version == mock_version
        mock_repo.git.fetch.assert_called_once_with("origin", "develop")
        mock_repo.git.show.assert_called_once_with("origin/develop:.semver.lock")

    @pytest.mark.unit
    def test_merge_resolves_allowlisted_conflicts(
        self, mocker: MockerFixture, mock_repo: Any
    ) -> None:
        """Promotion merges should prefer source for allowlisted metadata files."""
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        gitops = GitOps()

        merge_err = GitCommandError(
            "merge",
            1,
            "CONFLICT (content): Merge conflict in CHANGELOG.md",
        )
        mock_repo.git.merge.side_effect = merge_err
        mock_repo.git.diff.side_effect = ["CHANGELOG.md\n", ""]
        mock_repo.git.checkout = mocker.MagicMock()
        mock_repo.git.add = mocker.MagicMock()
        mock_repo.git.commit = mocker.MagicMock()

        gitops.merge(
            source_ref="dev",
            message="chore: auto-promote",
            prefer_source_paths=["CHANGELOG.md"],
        )

        mock_repo.git.checkout.assert_called_once_with("--theirs", "--", "CHANGELOG.md")
        mock_repo.git.add.assert_called_once_with("--", "CHANGELOG.md")
        mock_repo.git.commit.assert_called_once_with(m="chore: auto-promote", no_edit=False)
        mock_repo.git.merge.assert_called_once()

    @pytest.mark.unit
    def test_merge_aborts_when_disallowed_conflicts(
        self, mocker: MockerFixture, mock_repo: Any
    ) -> None:
        """Non-allowlisted conflicts must still fail the merge."""
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        gitops = GitOps()

        merge_err = GitCommandError("merge", 1, "CONFLICT (content): Merge conflict in README.md")
        mock_repo.git.merge.side_effect = merge_err
        mock_repo.git.diff.return_value = "README.md\n"

        with pytest.raises(RuntimeError, match=r"Merge conflict detected"):
            gitops.merge(
                source_ref="dev",
                message="chore: auto-promote",
                prefer_source_paths=["CHANGELOG.md"],
            )

        mock_repo.git.merge.assert_any_call("--abort")

    @pytest.mark.unit
    def test_integrate_tag_fast_forwards(self, mocker: MockerFixture, mock_repo: Any) -> None:
        """Tag promotion should fast-forward when staging is an ancestor."""
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        gitops = GitOps()

        gitops._integrate_source_for_promotion(
            source_ref="1.4.6-dev",
            message="chore: auto-promote",
            remote_name="origin",
            is_tag=True,
            prefer_source_paths=["CHANGELOG.md"],
        )

        mock_repo.git.merge.assert_called_once_with("1.4.6-dev", ff_only=True)

    @pytest.mark.unit
    def test_integrate_tag_squash_when_not_ff(self, mocker: MockerFixture, mock_repo: Any) -> None:
        """Tag promotion should squash to a single commit when ff is not possible."""
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        gitops = GitOps()
        mock_repo.git.merge.side_effect = GitCommandError(
            "merge", 1, "Not possible to fast-forward"
        )
        mock_head = mocker.MagicMock()
        mock_head.hexsha = "staging-sha"
        mock_repo.head.commit = mock_head
        mock_source = mocker.MagicMock()
        mock_source.tree = mocker.MagicMock()
        mock_repo.commit.return_value = mock_source
        mock_repo.git.commit_tree.return_value = "squash-sha"
        mock_repo.head.set_commit = mocker.MagicMock()

        gitops._integrate_source_for_promotion(
            source_ref="1.4.6-dev",
            message="chore: auto-promote",
            remote_name="origin",
            is_tag=True,
            prefer_source_paths=["CHANGELOG.md"],
        )

        mock_repo.git.commit_tree.assert_called_once()
        mock_repo.head.set_commit.assert_called_once()
        mock_repo.git.reset.assert_called_once_with("--hard", "squash-sha")
        mock_repo.git.merge.assert_called_once_with("1.4.6-dev", ff_only=True)
