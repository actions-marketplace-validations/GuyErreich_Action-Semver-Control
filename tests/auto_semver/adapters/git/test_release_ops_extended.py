"""Extended GitOps tests for release branch lifecycle."""

import pytest
from git import GitCommandError
from pytest_mock import MockerFixture

from auto_semver.adapters.git.ops import GitOps
from auto_semver.config.constants import PR_HIDDEN_MARKER
from auto_semver.core.semver import Version
from auto_semver.core.semver.lock import SemverLock


@pytest.mark.unit
def test_get_open_release_version_returns_highest(mocker: MockerFixture) -> None:
    """Pick the highest semver among open owned release PRs."""
    gitops = GitOps()
    mocker.patch.object(gitops, "get_repository_name", return_value="owner/repo")

    mock_pr_low = mocker.MagicMock()
    mock_pr_low.base.ref = "dev"
    mock_pr_low.head.ref = "auto-semver/release/1.3.0-dev"
    mock_pr_low.labels = [mocker.MagicMock(name="semver-bump")]
    mock_pr_low.labels[0].name = "semver-bump"
    mock_pr_low.body = PR_HIDDEN_MARKER

    mock_pr_high = mocker.MagicMock()
    mock_pr_high.base.ref = "dev"
    mock_pr_high.head.ref = "auto-semver/release/1.4.0-dev"
    mock_pr_high.labels = mock_pr_low.labels
    mock_pr_high.body = PR_HIDDEN_MARKER

    mock_repo = mocker.MagicMock()
    mock_repo.get_pulls.return_value = [mock_pr_low, mock_pr_high]
    mocker.patch(
        "auto_semver.adapters.git.verified.Github"
    ).return_value.get_repo.return_value = mock_repo

    def lock_side_effect(ref: str) -> SemverLock | None:
        version_str = ref.split("/")[-1]
        return SemverLock(
            version=Version.parse(version_str),
            source_branch="feature/x",
            target_branch="dev",
        )

    mocker.patch.object(gitops, "get_lock_at_ref", side_effect=lock_side_effect)

    result = gitops.get_open_release_version(
        github_token="token",
        target_branch="dev",
        branch_prefix="auto-semver/release/",
        labels=["semver-bump"],
    )

    assert result is not None
    assert str(result) == "1.4.0-dev"


@pytest.mark.unit
def test_get_merged_source_branches_since(mocker: MockerFixture) -> None:
    """Collect merged PR branch names after base_sha."""
    mock_repo = mocker.MagicMock()
    mock_repo.remote.return_value.url = "git@github.com:owner/repo.git"
    mock_repo.git.merge_base.return_value = "ok"
    mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
    gitops = GitOps()
    mocker.patch.object(gitops, "get_repository_name", return_value="owner/repo")

    mock_pr = mocker.MagicMock()
    mock_pr.merged = True
    mock_pr.merge_commit_sha = "sha1"
    mock_pr.head.ref = "feature/one"

    gh_repo = mocker.MagicMock()
    gh_repo.get_pulls.return_value = [mock_pr]
    mocker.patch(
        "auto_semver.adapters.git.verified.Github"
    ).return_value.get_repo.return_value = gh_repo

    branches = gitops.get_merged_source_branches_since(
        base_sha="base",
        target_branch="dev",
        github_token="token",
    )

    assert branches == ["feature/one"]


@pytest.mark.unit
def test_get_merged_source_branches_skips_non_ancestor(mocker: MockerFixture) -> None:
    """PRs not descended from base_sha are excluded."""
    mock_repo = mocker.MagicMock()
    mock_repo.remote.return_value.url = "git@github.com:owner/repo.git"
    mock_repo.git.merge_base.side_effect = GitCommandError("merge-base", "not ancestor")
    mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
    gitops = GitOps()
    mocker.patch.object(gitops, "get_repository_name", return_value="owner/repo")

    mock_pr = mocker.MagicMock()
    mock_pr.merged = True
    mock_pr.merge_commit_sha = "sha1"
    mock_pr.head.ref = "feature/old"

    gh_repo = mocker.MagicMock()
    gh_repo.get_pulls.return_value = [mock_pr]
    mocker.patch(
        "auto_semver.adapters.git.verified.Github"
    ).return_value.get_repo.return_value = gh_repo

    branches = gitops.get_merged_source_branches_since(
        base_sha="base",
        target_branch="dev",
        github_token="token",
    )

    assert branches == []


@pytest.mark.unit
def test_branch_matches_prefix() -> None:
    """Release branch prefix regex accepts semver suffixes."""
    assert GitOps._branch_matches_prefix("auto-semver/release/1.4.0-dev", "auto-semver/release/")
    assert not GitOps._branch_matches_prefix("release/manual-hotfix", "auto-semver/release/")


@pytest.mark.unit
def test_is_closeable_release_pr_accepts_preownership_lock(mocker: MockerFixture) -> None:
    """Legacy release/* PRs with old lockfiles can be superseded in single mode."""
    gitops = GitOps()
    lock = SemverLock(
        version=Version.parse("1.4.0-dev"),
        source_branch="feature/x",
        target_branch="dev",
    )
    mocker.patch.object(gitops, "get_lock_at_ref", return_value=lock)
    mocker.patch.object(
        gitops,
        "is_auto_semver_release_branch",
        return_value=(False, "lock is not auto-semver managed"),
    )

    closeable, reason = gitops._is_closeable_release_pr(
        branch_name="release/1.4.0-dev",
        github_token="token",
        branch_prefix="auto-semver/release/",
        labels=["semver-bump"],
    )

    assert closeable is True
    assert reason == ""


@pytest.mark.unit
def test_cleanup_stale_release_branches_deletes_closed_pr_refs(mocker: MockerFixture) -> None:
    """Delete remote release branches whose PRs are already closed."""
    gitops = GitOps()
    mocker.patch.object(gitops, "fetch")
    mocker.patch.object(gitops, "get_repository_name", return_value="owner/repo")

    mock_ref = mocker.MagicMock()
    mock_ref.name = "origin/auto-semver/release/1.4.1-dev"
    mock_repo = mocker.MagicMock()
    mock_repo.remote.return_value.refs = [mock_ref]
    gitops.repo = mock_repo

    mock_pr = mocker.MagicMock()
    mock_pr.state = "closed"
    mock_pr.base.ref = "dev"
    mock_pr.labels = [mocker.MagicMock(name="semver-bump")]
    mock_pr.labels[0].name = "semver-bump"
    mock_pr.body = PR_HIDDEN_MARKER
    mocker.patch.object(gitops, "_find_release_pr", return_value=mock_pr)
    mocker.patch.object(gitops, "_is_closeable_release_pr", return_value=(True, ""))
    delete_mock = mocker.patch.object(gitops, "_delete_superseded_release_branch")

    gitops.cleanup_stale_release_branches(
        github_token="token",
        target_branch="dev",
        branch_prefix="auto-semver/release/",
        labels=["semver-bump"],
        exclude_branch="auto-semver/release/1.4.3-dev",
    )

    delete_mock.assert_called_once_with(branch_name="auto-semver/release/1.4.1-dev")
