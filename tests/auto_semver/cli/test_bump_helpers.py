"""Tests for bump helper functions."""

import pytest
from pytest_mock import MockerFixture

from auto_semver.cli import bump as bump_module
from auto_semver.config import BumpConfig
from auto_semver.core.semver import Version


@pytest.mark.unit
def test_apply_version_bump_cumulative_mode(mocker: MockerFixture) -> None:
    """Cumulative mode scans merged branches since baseline."""
    gitops = mocker.Mock()
    gitops.get_merged_source_branches_since.return_value = ["fix/a", "feature/b"]

    config = mocker.Mock()
    config.data.bump = BumpConfig(mode="cumulative")

    version = Version.parse("1.3.14")
    counts = bump_module._apply_version_bump(
        version=version,
        config=config,
        current_branch="fix/c",
        gitops=gitops,
        target_branch="dev",
        baseline_sha="abc",
        github_token="token",
    )

    assert str(version) == "1.4.16"
    assert counts is not None
    assert counts.feature_count == 1
    assert counts.fix_count == 2
