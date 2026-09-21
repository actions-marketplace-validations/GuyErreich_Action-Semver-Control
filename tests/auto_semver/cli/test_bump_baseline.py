"""Additional tests for bump baseline and release branch helpers."""

import pytest
from pytest_mock import MockerFixture

from auto_semver.cli import bump as bump_module
from auto_semver.config import ReleaseConfig
from auto_semver.core.semver import Version


@pytest.mark.unit
def test_resolve_baseline_uses_open_release_in_single_mode(mocker: MockerFixture) -> None:
    """Single mode should start from max(dev, open release) version."""
    gitops = mocker.Mock()
    gitops.fetch.return_value = None
    gitops.get_lock_version_from_branch.return_value = Version.parse("1.3.14-dev")
    gitops.get_open_release_version.return_value = Version.parse("1.4.0-dev")

    config = mocker.Mock()
    config.data.release = ReleaseConfig(strategy="single")
    config.data.pull_request.labels = ["semver-bump"]

    baseline = bump_module._resolve_baseline_version(
        gitops=gitops,
        config=config,
        target_branch="dev",
        github_token="token",
    )

    assert str(baseline) == "1.4.0-dev"


@pytest.mark.unit
def test_resolve_baseline_ignores_open_release_in_multi_mode(mocker: MockerFixture) -> None:
    """Multi mode always uses dev lock baseline."""
    gitops = mocker.Mock()
    gitops.fetch.return_value = None
    gitops.get_lock_version_from_branch.return_value = Version.parse("1.3.14-dev")

    config = mocker.Mock()
    config.data.release = ReleaseConfig(strategy="multi")

    baseline = bump_module._resolve_baseline_version(
        gitops=gitops,
        config=config,
        target_branch="dev",
        github_token="token",
    )

    gitops.get_open_release_version.assert_not_called()
    assert str(baseline) == "1.3.14-dev"
