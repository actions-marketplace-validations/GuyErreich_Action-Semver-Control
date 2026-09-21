"""
Unit tests for the finalize module in auto_semver.cli.finalize.

This module contains tests for the run function in the finalize module,
which handles creating and pushing Git tags for finalized releases.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from auto_semver.adapters.git import GitOps
from auto_semver.adapters.github.event import GitHubEvent
from auto_semver.cli.finalize import create_auto_promotion_prs, run
from auto_semver.config import Config, ConfigData, ReleaseConfig
from auto_semver.core.semver import Version
from auto_semver.core.semver.lock import SemverLock


class TestFinalize:
    """Test cases for the finalize.run function."""

    @pytest.fixture
    def mock_gitops(self, mocker: MockerFixture) -> Any:
        """Create a mock GitOps object."""
        mock = mocker.Mock(spec=GitOps)
        # Set default behaviors
        mock.tag.return_value = "v1.0.0"
        return mock

    @pytest.fixture
    def mock_event(self, github_event: Any, mocker: MockerFixture) -> Any:
        """Create a GitHubEvent object for finalization tests."""
        # Use the github_event.for_finalize() method for a finalization-specific configuration
        github_event.for_finalize()
        # Create and return the GitHubEvent instance
        event = mocker.Mock(spec=GitHubEvent)
        # Set up necessary methods that are used in finalize.py
        event.get_target_branch_name.return_value = "main"  # Default to main branch
        return event

    @pytest.fixture
    def mock_config(self, mocker: MockerFixture) -> Any:
        """Create a mock Config object."""
        mock = mocker.Mock(spec=Config)
        mock_data = mocker.Mock(spec=ConfigData)
        mock.data = mock_data

        # Set default behavior
        mock.data.suffixes = {"main": "", "develop": "-dev"}
        mock.data.get_auto_promotion_targets.return_value = []
        mock.data.release = ReleaseConfig(cleanup_merged=False)
        mock_pr = mocker.Mock()
        mock_pr.labels = ["semver-bump"]
        mock.data.pull_request = mock_pr
        return mock

    @pytest.fixture
    def mock_semver_lock(self, mocker: MockerFixture) -> Any:
        """Create a mock SemverLock."""
        mock = mocker.Mock(spec=SemverLock)
        mock.version = Version.parse("1.0.0")
        mock.as_finalized_baseline = mocker.Mock()
        mock.save_to_file = mocker.Mock()
        mocker.patch.object(SemverLock, "load_from_file", return_value=mock)
        return mock

    @pytest.mark.unit
    def test_finalize_tags_and_pushes(
        self,
        mock_gitops: Any,
        mock_event: Any,
        mock_config: Any,
        mock_semver_lock: Any,
    ) -> None:
        """Test that finalize creates and pushes a tag when target branch is valid."""
        # Run the finalize function
        run(gitops=mock_gitops, event=mock_event, config=mock_config)

        # Verify version was loaded from lock file
        # The SemverLock.load_from_file method was mocked and called

        # Verify tag was created with the correct version
        mock_gitops.tag.assert_called_once_with(tag="1.0.0", branch="main")

        # Verify tag was pushed
        mock_gitops.push.assert_called_once_with(branch_name="v1.0.0")

    @pytest.mark.unit
    def test_finalize_fails_with_invalid_target_branch(
        self,
        mock_gitops: Any,
        mock_event: Any,
        mock_config: Any,
        mock_semver_lock: Any,
    ) -> None:
        """Test that finalize raises error when target branch is not allowed."""
        # Set target branch to something not in allowed targets
        mock_event.get_target_branch_name.return_value = "feature"

        # Run the finalize function and expect ValueError
        with pytest.raises(ValueError, match=r"Tagging not allowed on branch 'feature'"):
            run(gitops=mock_gitops, event=mock_event, config=mock_config)

        # Verify version was loaded from lock file
        # The SemverLock.load_from_file method was mocked and called

        # Verify tag was NOT created
        mock_gitops.tag.assert_not_called()

        # Verify tag was NOT pushed
        mock_gitops.push.assert_not_called()

    @pytest.mark.unit
    def test_finalize_with_develop_branch(
        self,
        mock_gitops: Any,
        mock_event: Any,
        mock_config: Any,
        mock_semver_lock: Any,
    ) -> None:
        """Test finalize works with a non-main branch that is allowed."""
        # Set target branch to develop (which is allowed)
        mock_event.get_target_branch_name.return_value = "develop"

        # Run the finalize function
        run(gitops=mock_gitops, event=mock_event, config=mock_config)

        # Verify tag was created with the correct version
        mock_gitops.tag.assert_called_once_with(tag="1.0.0", branch="develop")

        # Verify tag was pushed
        mock_gitops.push.assert_called_once_with(branch_name="v1.0.0")

    @pytest.mark.unit
    def test_auto_promotion_failure_raises(
        self,
        mock_gitops: Any,
        mock_event: Any,
        mock_config: Any,
    ) -> None:
        """Auto-promotion failures must propagate so CI exits non-zero."""
        mock_config.data.suffixes = {"dev": "-dev", "staging": "-rc"}
        mock_config.data.get_auto_promotion_targets.return_value = ["staging"]
        mock_config.data.changelog = None
        mock_config.data.version_files = ["version.txt"]
        mock_gitops.auto_promote.side_effect = RuntimeError(
            "Merge conflict detected when merging 'origin/dev'."
        )

        with pytest.raises(RuntimeError, match=r"Auto-promotion failed for dev → staging"):
            create_auto_promotion_prs(
                gitops=mock_gitops,
                event=mock_event,
                config=mock_config,
                target_branch="dev",
                version="1.4.6-dev",
            )

        mock_gitops.auto_promote.assert_called_once()
        create_call = mock_gitops.auto_promote.call_args
        assert create_call[1]["source_branch"] == "1.4.6-dev"
        assert create_call[1]["is_source_tag"] is True

    @pytest.mark.unit
    def test_auto_promotion_metadata_hook_uses_config_branch_pair(
        self,
        mocker: MockerFixture,
        mock_gitops: Any,
        mock_event: Any,
        mock_config: Any,
    ) -> None:
        """Metadata hook must record dev as source and staging as target from config."""
        mock_config.data.suffixes = {"dev": "-dev", "staging": "-rc"}
        mock_config.data.get_auto_promotion_targets.return_value = ["staging"]
        mock_config.data.changelog = None
        mock_config.data.version_files = ["version.txt"]
        mock_build_hook = mocker.patch("auto_semver.cli.finalize.build_promotion_metadata_hook")
        mock_gitops.auto_promote.return_value = None

        create_auto_promotion_prs(
            gitops=mock_gitops,
            event=mock_event,
            config=mock_config,
            target_branch="dev",
            version="1.4.6-dev",
        )

        mock_build_hook.assert_called_once_with(
            config=mock_config,
            source_branch="dev",
            target_branch="staging",
            gitops=mock_gitops,
        )
