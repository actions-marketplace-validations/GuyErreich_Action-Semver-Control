"""
Global fixtures for pytest.

This module contains global fixtures that are available to all test files.
"""

from pathlib import Path

import pytest
from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_mock import MockerFixture

from auto_semver.compat._notice import reset_deprecation_warnings
from tests.fixtures.changelog_fixture import ChangelogFixture
from tests.fixtures.config_fixture import ConfigFixture
from tests.fixtures.env_isolation_fixture import isolated_env
from tests.fixtures.file_fixture import FileFixture
from tests.fixtures.git_repo_fixture import temp_git_repo
from tests.fixtures.github_api_mock_fixture import mock_github_api
from tests.fixtures.github_event_fixture import GitHubEventFixture

__all__ = ["isolated_env", "mock_github_api", "temp_git_repo"]


@pytest.fixture(autouse=True)
def reset_deprecation_warnings_between_tests() -> None:
    """Let each test observe a deprecation warning on first use of an old name."""
    reset_deprecation_warnings()


@pytest.fixture
def config_fixture(fs: FakeFilesystem) -> ConfigFixture:
    """
    Create a ConfigFixture instance.

    This fixture provides methods to create different types of configuration files
    for testing configuration loading, parsing, and validation.

    Args:
        fs: Fake filesystem for testing

    Returns:
        A ConfigFixture instance for creating test configuration files
    """
    return ConfigFixture(fs)


@pytest.fixture
def github_event(tmp_path: Path, mocker: MockerFixture, fs: FakeFilesystem) -> GitHubEventFixture:
    """
    Create a GitHubEventFixture instance.

    This fixture sets up the GitHub event environment and provides methods
    to customize it for different test scenarios.

    Args:
        tmp_path: Pytest fixture that provides a temporary directory
        mocker: Pytest fixture for mocking
        fs: Fake filesystem for testing

    Returns:
        A GitHubEventFixture instance for further configuration
    """
    return GitHubEventFixture(tmp_path, mocker, fs)


@pytest.fixture
def file_fixture(tmp_path: Path, fs: FakeFilesystem) -> FileFixture:
    """
    Create a FileFixture instance.

    This fixture provides methods to create different types of files with version strings
    for testing version detection, parsing, and updating.

    Args:
        tmp_path: Pytest fixture that provides a temporary directory
        fs: Fake filesystem for testing

    Returns:
        A FileFixture instance for creating test files
    """
    return FileFixture(tmp_path, fs)


@pytest.fixture
def changelog_fixture(tmp_path: Path, fs: FakeFilesystem) -> ChangelogFixture:
    """
    Create a ChangelogFixture instance using the fake filesystem.

    Args:
        tmp_path: Pytest fixture that provides a temporary directory
        fs: Fake filesystem for testing

    Returns:
        A ChangelogFixture instance for creating and managing a fake changelog file
    """
    return ChangelogFixture(tmp_path, fs)


@pytest.fixture
def empty_changelog_path(changelog_fixture: ChangelogFixture) -> Path:
    """
    Create and return an empty CHANGELOG.md path in the fake filesystem.

    Useful for tests that need an existing, empty changelog file without
    writing to the real filesystem.
    """
    return changelog_fixture.create()
