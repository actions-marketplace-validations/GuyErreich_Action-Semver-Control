"""
Unit tests for promotion scenarios in auto_semver.cli.bump.

This module tests the promotion workflow where versions are promoted from
one branch to another with suffix changes but no version bumps.
"""

from pathlib import Path
from typing import Any

import pytest
from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_mock import MockerFixture

from auto_semver.adapters.git import GitOps
from auto_semver.adapters.github import GitHubEvent
from auto_semver.cli.bump import _detect_tag_source_branch, _is_tag_promotion_scenario, run
from auto_semver.config import (
    ChangelogConfig,
    CommitGroupsConfig,
    Config,
    ConfigData,
    PromotionRule,
    PullRequestConfig,
)
from auto_semver.core.changelog.manager import ChangelogManager
from auto_semver.core.semver import Version
from auto_semver.core.semver.lock import SemverLock
from tests.fixtures.config_fixture import ConfigFixture
from tests.fixtures.github_event_fixture import GitHubEventFixture


def create_test_config(
    config_fixture: ConfigFixture, suffixes: dict[str, str], promotions: list[tuple[str, str]]
) -> Config:
    """Helper to create a properly configured test config using the fixture."""
    promotion_dicts = [
        {"from_branch": from_branch, "to_branch": to_branch}
        for from_branch, to_branch in promotions
    ]

    config_fixture.create(suffixes=suffixes, promotions=promotion_dicts)

    return Config(config_fixture.config_path)


class TestDetectTagSourceBranch:
    """Test cases for _detect_tag_source_branch function."""

    @pytest.mark.unit
    def test_detect_dev_branch_from_suffix(self, config_fixture: ConfigFixture) -> None:
        """Test detecting dev branch from -dev suffix."""
        config = create_test_config(
            config_fixture, suffixes={"dev": "-dev", "staging": "-rc", "master": ""}, promotions=[]
        )

        version = Version(major=1, minor=2, patch=3, suffix="-dev")

        result = _detect_tag_source_branch(version=version, config=config)

        assert result == "dev"

    @pytest.mark.unit
    def test_detect_staging_branch_from_suffix(self, config_fixture: ConfigFixture) -> None:
        """Test detecting staging branch from -rc suffix."""
        config = create_test_config(
            config_fixture, suffixes={"dev": "-dev", "staging": "-rc", "master": ""}, promotions=[]
        )

        version = Version(major=1, minor=2, patch=3, suffix="-rc")

        result = _detect_tag_source_branch(version=version, config=config)

        assert result == "staging"

    @pytest.mark.unit
    def test_detect_master_branch_from_empty_suffix(self, config_fixture: ConfigFixture) -> None:
        """Test detecting master branch from empty suffix."""
        config = create_test_config(
            config_fixture, suffixes={"dev": "-dev", "staging": "-rc", "master": ""}, promotions=[]
        )

        version = Version(major=1, minor=2, patch=3, suffix=None)

        result = _detect_tag_source_branch(version=version, config=config)

        assert result == "master"

    @pytest.mark.unit
    def test_unknown_suffix_returns_none(self, config_fixture: ConfigFixture) -> None:
        """Test that unknown suffix returns None."""
        config = create_test_config(
            config_fixture, suffixes={"dev": "-dev", "staging": "-rc", "master": ""}, promotions=[]
        )

        version = Version(major=1, minor=2, patch=3, suffix="-unknown")

        result = _detect_tag_source_branch(version=version, config=config)

        assert result is None


class TestIsTagPromotionScenario:
    """Test cases for _is_tag_promotion_scenario function."""

    @pytest.mark.unit
    def test_valid_dev_to_staging_promotion(self, config_fixture: ConfigFixture) -> None:
        """Test valid promotion from dev to staging."""
        config = create_test_config(
            config_fixture,
            suffixes={"dev": "-dev", "staging": "-rc", "master": ""},
            promotions=[("dev", "staging"), ("staging", "master")],
        )

        version = Version(major=1, minor=2, patch=3, suffix="-dev")

        result = _is_tag_promotion_scenario(version=version, target_branch="staging", config=config)

        assert result is True

    @pytest.mark.unit
    def test_valid_staging_to_master_promotion(self, config_fixture: ConfigFixture) -> None:
        """Test valid promotion from staging to master."""
        config = create_test_config(
            config_fixture,
            suffixes={"dev": "-dev", "staging": "-rc", "master": ""},
            promotions=[("dev", "staging"), ("staging", "master")],
        )

        version = Version(major=1, minor=2, patch=3, suffix="-rc")

        result = _is_tag_promotion_scenario(version=version, target_branch="master", config=config)

        assert result is True

    @pytest.mark.unit
    def test_invalid_promotion_no_rule(self, config_fixture: ConfigFixture) -> None:
        """Test invalid promotion when no rule exists."""
        config = create_test_config(
            config_fixture,
            suffixes={"dev": "-dev", "staging": "-rc", "master": ""},
            promotions=[("dev", "staging"), ("staging", "master")],
        )

        version = Version(major=1, minor=2, patch=3, suffix="-dev")

        # Try to promote directly from dev to master (no direct rule)
        result = _is_tag_promotion_scenario(version=version, target_branch="master", config=config)

        assert result is False

    @pytest.mark.unit
    def test_unknown_source_branch_raises_error(self, config_fixture: ConfigFixture) -> None:
        """Test that unknown source branch raises ValueError."""
        config = create_test_config(
            config_fixture,
            suffixes={"dev": "-dev", "staging": "-rc", "master": ""},
            promotions=[("dev", "staging"), ("staging", "master")],
        )

        # Version with unknown suffix
        version = Version(major=1, minor=2, patch=3, suffix="-unknown")

        with pytest.raises(ValueError) as exc_info:
            _is_tag_promotion_scenario(version=version, target_branch="staging", config=config)

        assert (
            "Version 1.2.3-unknown has suffix '-unknown' that doesn't match any configured branch suffix"
            in str(exc_info.value)
        )

    @pytest.mark.unit
    def test_no_promotions_configured_returns_false(self, config_fixture: ConfigFixture) -> None:
        """Test that no configured promotions returns False."""
        config = create_test_config(
            config_fixture,
            suffixes={"dev": "-dev", "staging": "-rc", "master": ""},
            promotions=[],  # No promotions configured
        )

        version = Version(major=1, minor=2, patch=3, suffix="-dev")

        result = _is_tag_promotion_scenario(version=version, target_branch="staging", config=config)

        assert result is False


class TestPromotionWorkflow:
    """Test cases for the promotion workflow in bump.run()."""

    @pytest.fixture
    def mock_gitops(self, mocker: MockerFixture) -> Any:
        """Create a mock GitOps object."""
        mock = mocker.Mock(spec=GitOps)
        mock.get_lock_version_from_branch.return_value = None
        mock.get_open_release_version.return_value = None
        mock.fetch.return_value = None
        mock.get_recent_commits.return_value = ["feat: promotion feature"]
        return mock

    @pytest.fixture
    def mock_promotion_config(self, fs: FakeFilesystem) -> Config:
        """Create a real Config for promotion testing using ConfigData directly."""
        # Create ConfigData directly with all required fields
        config_data = ConfigData(
            start_version=Version.parse("1.0.0"),
            suffixes={"dev": "-dev", "staging": "-rc", "master": ""},
            promotions=[
                PromotionRule(from_branch="dev", to_branch="staging"),
                PromotionRule(from_branch="staging", to_branch="master"),
            ],
            version_files=["version.txt"],
            commit_groups=CommitGroupsConfig(),
            pull_request=PullRequestConfig(
                title="Release {{version}}", body="Promotion notes", labels=["semver-bump"]
            ),
            changelog=ChangelogConfig(
                file=Path("CHANGELOG.md"), truncate=False, template="## [{{version}}] - {{date}}\n"
            ),
        )

        # Generate the config file using the clean API (uses default path)
        Config.generate_config_file(config_data=config_data)

        return Config()

    @pytest.fixture
    def mock_changelog_manager(self, mocker: MockerFixture) -> Any:
        """Create a mock ChangelogManager."""
        mock = mocker.Mock(spec=ChangelogManager)
        mock.update.return_value = None
        mock.path = Path("CHANGELOG.md")
        mocker.patch.object(ChangelogManager, "from_config", return_value=mock)
        return mock

    @pytest.fixture
    def mock_semver_lock(self, mocker: MockerFixture) -> Any:
        """Create a mock SemverLock."""
        mock = mocker.Mock(spec=SemverLock)
        mock.version = Version.parse("1.0.0")
        mock.target_base_sha = "abc123"
        mock.path = "semver.lock"
        mock.save_to_file.return_value = None

        # Mock the class methods - avoid patching __new__ to prevent interference
        mocker.patch.object(SemverLock, "load_from_file", side_effect=FileNotFoundError)
        # Instead of patching __new__, patch the constructor call in the module
        mocker.patch("auto_semver.cli.bump.SemverLock", return_value=mock)
        return mock

    @pytest.mark.unit
    def test_promotion_preserves_version_numbers(
        self,
        mock_gitops: Any,
        github_event: GitHubEventFixture,
        mock_promotion_config: Any,
        mock_changelog_manager: Any,
        mock_semver_lock: Any,
        fs: FakeFilesystem,
        mocker: MockerFixture,
    ) -> None:
        """Test that promotion scenarios preserve version numbers and only change suffix."""
        # Set up event for promotion scenario (dev → staging)
        github_event.create(
            title="Promote to staging",
            body="Promoting dev to staging",
            source_branch="dev",
            target_branch="staging",
            labels=["semver-bump"],
        )

        event = GitHubEvent()

        # Create version file using pyfakefs
        fs.create_file("version.txt", contents="1.0.0-dev")
        mock_version_updater = mocker.patch("auto_semver.cli.bump.VersionFileUpdater")

        # Run the bump function
        run(
            gitops=mock_gitops, event=event, config=mock_promotion_config, github_token="fake-token"
        )

        # Verify version was NOT bumped (should remain 1.0.0)
        # The version should only have suffix changed from -dev to -rc
        mock_version_updater.assert_called()
        version_updater_call = mock_version_updater.call_args[1]
        assert str(version_updater_call["version"]) == "1.0.0-rc"

        # Verify PR was created with promotion
        mock_gitops.create_pr.assert_called_once()

    @pytest.mark.unit
    def test_non_promotion_bumps_version(
        self,
        mock_gitops: Any,
        github_event: GitHubEventFixture,
        mock_promotion_config: Any,
        mock_changelog_manager: Any,
        mock_semver_lock: Any,
        fs: FakeFilesystem,
        mocker: MockerFixture,
    ) -> None:
        """Test that non-promotion scenarios still bump version numbers."""
        # Set up event for regular feature branch (feature/new → dev)
        github_event.create(
            title="Add new feature",
            body="Adding new feature",
            source_branch="feature/new-feature",
            target_branch="dev",
            labels=["semver-bump"],
        )

        event = GitHubEvent()

        # Create version file using pyfakefs
        fs.create_file("version.txt", contents="1.0.0-dev")
        mock_version_updater = mocker.patch("auto_semver.cli.bump.VersionFileUpdater")

        # Run the bump function
        run(
            gitops=mock_gitops, event=event, config=mock_promotion_config, github_token="fake-token"
        )

        # Verify version was bumped (should be 1.1.0-dev for a feature)
        mock_version_updater.assert_called()
        version_updater_call = mock_version_updater.call_args[1]
        assert str(version_updater_call["version"]) == "1.1.0-dev"

        # Verify PR was created
        mock_gitops.create_pr.assert_called_once()
