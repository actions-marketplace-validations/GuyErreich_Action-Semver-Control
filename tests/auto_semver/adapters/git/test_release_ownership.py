"""Tests for release branch ownership helpers."""

import pytest
from pytest_mock import MockerFixture

from auto_semver.adapters.git.ops import GitOps
from auto_semver.core.semver import Version
from auto_semver.core.semver.lock import SemverLock


@pytest.mark.unit
def test_is_auto_semver_release_branch_requires_release_role(mocker: MockerFixture) -> None:
    """Branches without release-role lock at tip are not owned."""
    gitops = GitOps()
    mocker.patch.object(gitops, "get_repository_name", return_value="owner/repo")

    lock = SemverLock(
        version=Version.parse("1.4.0-dev"),
        source_branch="feature/x",
        target_branch="dev",
    )
    mocker.patch.object(gitops, "get_lock_at_ref", return_value=lock)

    owned, reason = gitops.is_auto_semver_release_branch(
        branch_name="auto-semver/release/1.4.0-dev",
        github_token="token",
        branch_prefix="auto-semver/release/",
        labels=["semver-bump"],
        skip_pr_check=True,
    )

    assert owned is False
    assert "not auto-semver managed" in reason


@pytest.mark.unit
def test_is_auto_semver_release_branch_with_release_role(mocker: MockerFixture) -> None:
    """Release-role lock at branch tip passes ownership when PR checks skipped."""
    gitops = GitOps()
    mocker.patch.object(gitops, "get_repository_name", return_value="owner/repo")

    lock = SemverLock(
        version=Version.parse("1.4.0-dev"),
        source_branch="feature/x",
        target_branch="dev",
    )
    lock.as_release_branch_lock()
    mocker.patch.object(gitops, "get_lock_at_ref", return_value=lock)

    owned, reason = gitops.is_auto_semver_release_branch(
        branch_name="auto-semver/release/1.4.0-dev",
        github_token="token",
        branch_prefix="auto-semver/release/",
        skip_pr_check=True,
    )

    assert owned is True
    assert reason == ""
