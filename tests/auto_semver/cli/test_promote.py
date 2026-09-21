"""Tests for promote CLI command."""

import re
from unittest.mock import ANY, MagicMock, patch

import pytest

from auto_semver.adapters.git import GitOps
from auto_semver.cli.promote import run
from auto_semver.config import Config, PromotionRule
from auto_semver.core.semver import Version


class TestPromoteCLI:
    """Tests for the promote CLI command."""

    @patch("auto_semver.adapters.git.GitOps.get_lock_version_from_branch")
    @patch("auto_semver.adapters.git.GitOps.get_lock_version_from_tag")
    @patch("auto_semver.adapters.git.GitOps.auto_promote")
    def test_successful_promotion_manual(
        self,
        mock_auto_promote: MagicMock,
        mock_get_tag_version: MagicMock,
        mock_get_branch_version: MagicMock,
    ) -> None:
        """Test successful manual promotion (direct merge)."""
        # Setup mocks
        mock_rule = PromotionRule(from_branch="dev", to_branch="staging", auto_promote=True)
        mock_get_tag_version.return_value = Version.parse("1.2.3-dev")
        # Mock target branch version to be lower
        mock_get_branch_version.return_value = Version.parse("1.0.0-rc")

        # Create mock objects
        gitops = MagicMock(spec=GitOps)
        gitops.get_lock_version_from_tag = mock_get_tag_version
        gitops.get_lock_version_from_branch = mock_get_branch_version
        gitops.auto_promote = mock_auto_promote

        # Mock the config with proper data attribute
        config = MagicMock(spec=Config)
        mock_data = MagicMock()
        mock_data.validate_promotion.return_value = mock_rule
        # Mock suffixes for branch detection
        mock_data.suffixes = {"dev": "-dev", "staging": "-rc"}
        config.data = mock_data

        # Run the function
        run(
            gitops=gitops,
            config=config,
            from_branch="dev",
            to_branch="staging",
            from_tag="v1.2.3-dev",
        )

        # Verify calls
        config.data.validate_promotion.assert_called_once_with(
            from_branch="dev", to_branch="staging", require_auto_promote=False
        )
        # mock_get_tag_version.assert_called_once_with(tag_name="v1.2.3-dev")
        mock_get_branch_version.assert_called_once_with(branch_name="staging")

        # Verify auto_promote called with correct version (suffix changed)
        mock_auto_promote.assert_called_once_with(
            source_branch="v1.2.3-dev",
            target_branch="staging",
            version="1.2.3-rc",
            source_version="1.2.3-dev",
            is_source_tag=True,
            post_merge_hook=ANY,
            prefer_source_paths=ANY,
        )

    @patch("auto_semver.adapters.git.GitOps.get_lock_version_from_branch")
    @patch("auto_semver.adapters.git.GitOps.get_lock_version_from_tag")
    @patch("auto_semver.adapters.git.GitOps.auto_promote")
    def test_successful_promotion_manual_inferred_branch(
        self,
        mock_auto_promote: MagicMock,
        mock_get_tag_version: MagicMock,
        mock_get_branch_version: MagicMock,
    ) -> None:
        """Test successful manual promotion with inferred source branch."""
        # Setup mocks
        mock_rule = PromotionRule(from_branch="dev", to_branch="staging", auto_promote=True)
        mock_get_tag_version.return_value = Version.parse("1.2.3-dev")
        mock_get_branch_version.return_value = Version.parse("1.0.0-rc")

        # Create mock objects
        gitops = MagicMock(spec=GitOps)
        gitops.get_lock_version_from_tag = mock_get_tag_version
        gitops.get_lock_version_from_branch = mock_get_branch_version
        gitops.auto_promote = mock_auto_promote

        # Mock the config with proper data attribute and suffixes
        config = MagicMock(spec=Config)
        mock_data = MagicMock()
        mock_data.validate_promotion.return_value = mock_rule
        mock_data.suffixes = {"dev": "-dev", "staging": "-rc"}
        config.data = mock_data

        # Run the function (no from_branch)
        run(
            gitops=gitops,
            config=config,
            to_branch="staging",
            from_tag="v1.2.3-dev",
            from_branch=None,
        )

        # Verify calls
        config.data.validate_promotion.assert_called_once_with(
            from_branch="dev", to_branch="staging", require_auto_promote=False
        )
        # mock_get_tag_version.assert_called_once_with(tag_name="v1.2.3-dev")

        # Verify auto_promote called with correct version
        mock_auto_promote.assert_called_once_with(
            source_branch="v1.2.3-dev",
            target_branch="staging",
            version="1.2.3-rc",
            source_version="1.2.3-dev",
            is_source_tag=True,
            post_merge_hook=ANY,
            prefer_source_paths=ANY,
        )

    def test_promotion_validation_failure(self) -> None:
        """Test handling of promotion validation failure."""
        gitops = MagicMock(spec=GitOps)
        # Mock get_lock_version_from_tag to return a version with a known suffix
        gitops.get_lock_version_from_tag.return_value = Version.parse("1.0.0-dev")

        # Mock the config with proper data attribute
        config = MagicMock(spec=Config)
        mock_data = MagicMock()
        mock_data.validate_promotion.side_effect = ValueError("No promotion rule found")
        # Add suffixes for branch inference
        mock_data.suffixes = {"dev": "-dev"}
        config.data = mock_data

        # Should raise the validation error
        with pytest.raises(ValueError, match="No promotion rule found"):
            run(
                gitops=gitops,
                config=config,
                from_branch="dev",
                to_branch="invalid",
                from_tag="v1.0.0-dev",
            )

    @patch("auto_semver.adapters.git.GitOps.get_lock_version_from_tag")
    def test_no_version_found(self, mock_get_version: MagicMock) -> None:
        """Test handling when no version is found for source tag."""
        mock_rule = PromotionRule(from_branch="dev", to_branch="staging")
        mock_get_version.return_value = None

        gitops = MagicMock(spec=GitOps)
        gitops.get_lock_version_from_tag = mock_get_version

        # Mock the config with proper data attribute
        config = MagicMock(spec=Config)
        mock_data = MagicMock()
        mock_data.validate_promotion.return_value = mock_rule
        config.data = mock_data

        with pytest.raises(ValueError, match=re.escape("No version found for tag 'invalid-tag'")):
            run(
                gitops=gitops,
                config=config,
                from_branch="dev",
                to_branch="staging",
                from_tag="invalid-tag",
            )

    @patch("auto_semver.adapters.git.GitOps.get_lock_version_from_branch")
    @patch("auto_semver.adapters.git.GitOps.get_lock_version_from_tag")
    def test_lower_version_promotion_failure(
        self, mock_get_tag_version: MagicMock, mock_get_branch_version: MagicMock
    ) -> None:
        """Test failure when promoting a version lower than target branch version."""
        mock_rule = PromotionRule(from_branch="staging", to_branch="master")
        mock_get_tag_version.return_value = Version.parse("1.0.0-rc.1")
        mock_get_branch_version.return_value = Version.parse("1.0.0-rc.2")

        gitops = MagicMock(spec=GitOps)
        gitops.get_lock_version_from_tag = mock_get_tag_version
        gitops.get_lock_version_from_branch = mock_get_branch_version

        config = MagicMock(spec=Config)
        mock_data = MagicMock()
        mock_data.validate_promotion.return_value = mock_rule
        # Add suffixes for branch inference
        mock_data.suffixes = {"staging": "-rc.1"}
        config.data = mock_data

        with pytest.raises(ValueError, match="Cannot promote version"):
            run(
                gitops=gitops,
                config=config,
                from_branch="staging",
                to_branch="master",
                from_tag="v1.0.0-rc.1",
            )
