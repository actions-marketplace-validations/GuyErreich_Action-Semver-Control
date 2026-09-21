"""Tests for semver lock release-branch metadata."""

import pytest

from auto_semver.core.semver import Version
from auto_semver.core.semver.lock import SemverLock


@pytest.mark.unit
def test_release_lock_markers() -> None:
    """Release branch locks include branch_role release."""
    lock = SemverLock(
        version=Version.parse("1.4.0-dev"),
        source_branch="feature/foo",
        target_branch="dev",
    )
    lock.as_release_branch_lock(managed_by_version="1.3.14")

    assert lock.is_release_branch_lock()
    assert lock.branch_role == "release"
    assert lock.managed_by == "auto-semver"


@pytest.mark.unit
def test_finalized_baseline_strips_release_role() -> None:
    """Finalize rewrites the lock as a baseline without release branch markers."""
    lock = SemverLock(
        version=Version.parse("1.4.0-dev"),
        source_branch="feature/foo",
        target_branch="dev",
        branch_role="release",
        managed_by="auto-semver",
    )
    lock.as_finalized_baseline(merge_sha="abc123")

    assert lock.finalized is True
    assert lock.branch_role is None
    assert lock.target_base_sha == "abc123"


@pytest.mark.unit
def test_promotion_baseline_rewrites_target_branch() -> None:
    """Promotion normalizes the lock for the target channel with the rc version."""
    lock = SemverLock(
        version=Version.parse("1.4.6-dev"),
        source_branch="feature/foo",
        target_branch="dev",
        branch_role="release",
        managed_by="auto-semver",
    )
    lock.as_promotion_baseline(
        source_branch="dev",
        target_branch="staging",
        version=Version.parse("1.4.6-rc"),
        merge_sha="def456",
    )

    assert lock.version == Version.parse("1.4.6-rc")
    assert lock.source_branch == "dev"
    assert lock.target_branch == "staging"
    assert lock.source_branch != lock.target_branch
    assert lock.finalized is True
    assert lock.branch_role is None
    assert lock.target_base_sha == "def456"


@pytest.mark.unit
def test_preownership_release_lock() -> None:
    """Legacy release locks without managed_by metadata are identifiable."""
    lock = SemverLock(
        version=Version.parse("1.4.0-dev"),
        source_branch="feature/foo",
        target_branch="dev",
    )

    assert lock.is_preownership_release_lock()
    assert not lock.is_release_branch_lock()
    assert not lock.is_legacy_managed_lock()
