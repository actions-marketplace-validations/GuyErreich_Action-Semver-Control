"""Release notes keep changes from a finalized version that never shipped."""

from __future__ import annotations

from typing import Any

import pytest
from github import GithubException
from pytest_mock import MockerFixture

from auto_semver.adapters.git.release_pr import GitReleasePr
from auto_semver.cli.bump import _unpublished_notes_base
from auto_semver.core.semver import Version
from auto_semver.core.semver.lock import SemverLock


def _lock(*, version: str, base: str, finalized: bool) -> SemverLock:
    return SemverLock(
        version=Version.parse(version),
        source_branch="dev",
        target_branch="dev",
        target_base_sha=base,
        finalized=finalized,
    )


def _history(mocker: MockerFixture, locks: list[SemverLock]) -> Any:
    gitops = mocker.Mock()
    commits = [mocker.Mock(hexsha=f"sha-{index}") for index, _lock in enumerate(locks)]
    gitops.repo.iter_commits.return_value = commits
    gitops.get_lock_at_ref.side_effect = locks
    return gitops


@pytest.mark.unit
def test_shipped_release_keeps_current_baseline(mocker: MockerFixture) -> None:
    """A version that already has a GitHub Release does not pull older notes."""
    lock = _lock(version="1.8.6-dev", base="failed-merge", finalized=True)
    gitops = mocker.Mock()
    gitops.github_release_exists.return_value = True

    assert _unpublished_notes_base(gitops=gitops, lockfile=lock, github_token="token") is None
    gitops.repo.iter_commits.assert_not_called()


@pytest.mark.unit
def test_missing_release_uses_previous_finalized_baseline(mocker: MockerFixture) -> None:
    """Notes for an unpublished version start at the previous shipped baseline."""
    current = _lock(version="1.8.6-dev", base="failed-merge", finalized=True)
    same_version = _lock(version="1.8.6-dev", base="failed-merge", finalized=True)
    previous = _lock(version="1.7.6-dev", base="shipped-merge", finalized=True)
    gitops = _history(mocker, [same_version, previous])
    gitops.github_release_exists.return_value = False

    assert (
        _unpublished_notes_base(gitops=gitops, lockfile=current, github_token="token")
        == "shipped-merge"
    )


@pytest.mark.unit
def test_unfinalized_lock_does_not_check_github(mocker: MockerFixture) -> None:
    """An in-progress lock keeps its own baseline."""
    lock = _lock(version="1.8.6-dev", base="current", finalized=False)
    gitops = mocker.Mock()

    assert _unpublished_notes_base(gitops=gitops, lockfile=lock, github_token="token") is None
    gitops.github_release_exists.assert_not_called()


@pytest.mark.unit
def test_github_release_exists_treats_404_as_missing(mocker: MockerFixture) -> None:
    """A 404 from the releases API means that tag was not published."""
    repo = mocker.Mock()
    repo.get_release.side_effect = GithubException(404, {"message": "Not Found"}, None)
    client = mocker.Mock()
    client.get_repo.return_value = repo
    host = mocker.Mock()
    host._repo_full_name = "GuyErreich/Action-Semver-Control"
    host._github_client_for.return_value = client

    assert GitReleasePr.github_release_exists(host, tag="1.8.6-dev", github_token="token") is False
