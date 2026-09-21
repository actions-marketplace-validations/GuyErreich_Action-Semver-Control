"""
Unit tests for the main entry point in auto_semver.cli.main module.

This module contains comprehensive tests for the main function, which is the entry point
for the auto-semver command-line tool, covering argument parsing, logging setup, and
workflow selection and execution.
"""

import argparse
from typing import Any

import pytest
from pytest_mock import MockerFixture

from auto_semver.adapters.git import GitOps
from auto_semver.adapters.github.event import GitHubEvent
from auto_semver.cli.main import main
from auto_semver.config import Config
from tests.fixtures.github_event_fixture import GitHubEventFixture


class TestMain:
    """Test cases for the main() function."""

    @pytest.fixture
    def mock_args(self) -> argparse.Namespace:
        """Create mock command line arguments."""
        args = argparse.Namespace()
        args.github_token = "mock-token"
        args.debug = True
        args.command = None
        args.signed_commits = False
        args.log_file = None
        return args

    @pytest.fixture
    def mock_parser(self, mocker: MockerFixture, mock_args: argparse.Namespace) -> Any:
        """Create a mock ArgumentParser that returns mock_args."""
        mock_parser = mocker.Mock(spec=argparse.ArgumentParser)
        mock_parser.parse_args.return_value = mock_args
        mocker.patch.object(argparse, "ArgumentParser", return_value=mock_parser)
        return mock_parser

    @pytest.fixture
    def mock_setup_logger(self, mocker: MockerFixture) -> Any:
        """Mock the runview install function."""
        mocker.patch("auto_semver.cli.main.close")
        return mocker.patch("auto_semver.cli.main.install")

    @pytest.fixture
    def mock_config(self, mocker: MockerFixture) -> Any:
        """Create a mock Config instance."""
        mock_config = mocker.Mock(spec=Config)
        # Mock the _load_and_parse method to avoid validation errors
        mock_config.data = mocker.Mock()
        mock_config.data.suffixes = {"main": "", "develop": "-dev"}
        mock_config.data.pull_request = mocker.Mock()
        mock_config.data.pull_request.labels = ["semver-bump"]
        # Create a mock Config constructor that returns our mock
        mocker.patch("auto_semver.config.Config", return_value=mock_config)
        # Mock the _load_and_parse method to prevent it from being called
        mocker.patch.object(Config, "_load_and_parse")
        return mock_config

    @pytest.fixture
    def mock_gitops(self, mocker: MockerFixture) -> Any:
        """Create a mock GitOps instance."""
        mock_gitops = mocker.Mock(spec=GitOps)
        mocker.patch("auto_semver.adapters.git.GitOps", return_value=mock_gitops)
        return mock_gitops

    @pytest.fixture
    def mock_is_finalized(self, mocker: MockerFixture) -> Any:
        """Mock the is_finalized function."""
        # Create a proper mock with a controllable return value
        return mocker.patch("auto_semver.cli.main.is_finalized")

    @pytest.fixture
    def mock_finalize(self, mocker: MockerFixture) -> Any:
        """Mock the finalize.run function."""
        return mocker.patch("auto_semver.cli.finalize.run")

    @pytest.fixture
    def mock_bump(self, mocker: MockerFixture) -> Any:
        """Mock the bump.run function."""
        return mocker.patch("auto_semver.cli.bump.run")

    @pytest.fixture(autouse=True)
    def patch_main_dependencies(
        self, mocker: MockerFixture, mock_config: Any, mock_gitops: Any
    ) -> None:
        """Patch main dependencies to use our mocks."""
        mocker.patch("auto_semver.cli.main.Config", return_value=mock_config)
        mocker.patch("auto_semver.cli.main.GitOps", return_value=mock_gitops)

    @pytest.mark.unit
    def test_main_calls_finalize_when_is_finalized_true(
        self,
        mock_parser: Any,
        mock_setup_logger: Any,
        mock_config: Any,
        mock_gitops: Any,
        github_event: GitHubEventFixture,
        mock_is_finalized: Any,
        mock_finalize: Any,
        mock_bump: Any,
        mock_args: argparse.Namespace,
        mocker: MockerFixture,
    ) -> None:
        """Test that main calls finalize.run when is_finalized returns True."""
        # Setup is_finalized to return True
        mock_is_finalized.return_value = True

        # Set up GitHub event
        github_event.for_finalize()

        event = GitHubEvent()

        # Patch GitHubEvent constructor to return our event instance
        mocker.patch("auto_semver.cli.main.GitHubEvent", return_value=event)

        # Call main function
        main()

        # Verify logger was set up with debug flag
        assert mock_setup_logger.call_count == 1
        cfg = mock_setup_logger.call_args.args[0]
        assert cfg.debug is mock_args.debug
        assert cfg.command == "bump"
        assert cfg.log_file is None

        # Verify is_finalized was called (we can't verify exact args due to object differences)
        assert mock_is_finalized.call_count == 1
        # Check that the call had the right argument types
        call_args = mock_is_finalized.call_args
        assert "config" in call_args.kwargs
        assert "event" in call_args.kwargs

        # Verify finalize.run was called with correct arguments
        mock_finalize.assert_called_once_with(
            gitops=mock_gitops, event=event, config=mock_config, github_token="mock-token"
        )

        # Verify bump.run was not called
        mock_bump.assert_not_called()

    @pytest.mark.unit
    def test_main_calls_bump_when_is_finalized_false(
        self,
        mock_parser: Any,
        mock_setup_logger: Any,
        mock_config: Any,
        mock_gitops: Any,
        github_event: GitHubEventFixture,
        mock_is_finalized: Any,
        mock_finalize: Any,
        mock_bump: Any,
        mock_args: argparse.Namespace,
        mocker: MockerFixture,
    ) -> None:
        """Test that main calls bump.run when is_finalized returns False."""
        # Setup is_finalized to return False - use the fixture instead of patching again
        mock_is_finalized.return_value = False

        # Set up GitHub event for bump
        github_event.for_bump()

        event = GitHubEvent()

        # Patch GitHubEvent constructor to return our event instance
        mocker.patch("auto_semver.cli.main.GitHubEvent", return_value=event)

        # Call main function
        main()

        # Verify logger was set up with debug flag
        assert mock_setup_logger.call_count == 1
        cfg = mock_setup_logger.call_args.args[0]
        assert cfg.debug is mock_args.debug
        assert cfg.command == "bump"
        assert cfg.log_file is None

        # Verify is_finalized was called (we can't verify exact args due to object differences)
        assert mock_is_finalized.call_count == 1
        # Check that the call had the right argument types
        call_args = mock_is_finalized.call_args
        assert "config" in call_args.kwargs
        assert "event" in call_args.kwargs

        # Verify bump.run was called with correct arguments
        mock_bump.assert_called_once_with(
            gitops=mock_gitops, event=event, config=mock_config, github_token=mock_args.github_token
        )

        # Verify finalize.run was not called
        mock_finalize.assert_not_called()
