"""
GitHub event fixtures for testing.

This module provides a fixture class for creating GitHub events for testing.
"""

import os
from pathlib import Path

from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_mock import MockerFixture

from auto_semver.adapters.github.event import _GITHUB_EVENT_PATH_ENV
from tests.fixtures.github_event_helpers import GitHubPullRequestEventData


class GitHubEventFixture:
    """
    A fixture class that provides real GitHubEvent instances for tests.

    This class provides methods to create GitHubEvent instances with various
    configurations, making it easier to test different scenarios.
    """

    def __init__(self, tmp_path: Path, mocker: MockerFixture, fs: FakeFilesystem):
        """
        Initialize the fixture.

        Args:
            tmp_path: Pytest fixture that provides a temporary directory
            mocker: Pytest fixture for mocking
            fs: Fake filesystem for testing
        """
        self.tmp_path = tmp_path
        self.mocker = mocker
        self.fs = fs
        self.create()

    def create(
        self,
        *,
        title: str = "Test PR",
        body: str = "This is a test PR",
        source_branch: str = "feature/test-branch",
        target_branch: str = "main",
        source_sha: str = "abcd1234",
        target_sha: str = "efgh5678",
        merge_commit_sha: str = "ijkl9012",
        merged: bool = True,
        labels: list[str] | None = None,
        repository: str = "owner/repo",
    ) -> None:
        """
        Create a GitHub event environment with the specified parameters.

        Args:
            title: The PR title
            body: The PR body
            source_branch: The source branch name
            target_branch: The target branch name
            source_sha: The SHA of the source branch
            target_sha: The SHA of the target branch
            merge_commit_sha: The SHA of the merge commit
            merged: Whether the PR is merged
            labels: A list of labels applied to the PR
            repository: The repository in "owner/repo" format
        """
        # Set default value for labels
        if labels is None:
            labels = ["semver:minor"]

        # Create the event data
        event_data = GitHubPullRequestEventData(
            title=title,
            body=body,
            source_branch=source_branch,
            target_branch=target_branch,
            source_sha=source_sha,
            target_sha=target_sha,
            merge_commit_sha=merge_commit_sha,
            merged=merged,
            labels=labels,
            repository=repository,
        )

        # Write the event data to a file
        event_file = self.tmp_path / "github_event.json"
        if self.fs.exists(event_file):
            self.fs.remove_object(str(event_file))
        self.fs.create_file(event_file, contents=event_data.to_event_dict())

        # Mock the environment variable
        self.mocker.patch.dict(os.environ, {_GITHUB_EVENT_PATH_ENV: str(event_file)})

    def __call__(self) -> None:
        """
        Sets up the default GitHub event environment.

        This method allows the fixture to be used as a callable that sets up
        the default GitHub event environment.
        """
        self.create()

    def for_bump(self) -> None:
        """Sets up a GitHub event environment suitable for testing bump operations."""
        self.create(
            title="Feature PR",
            source_branch="feature/new-feature",
            target_branch="main",
            labels=["semver:minor"],
        )

    def for_finalize(self) -> None:
        """Sets up a GitHub event environment suitable for testing finalize operations."""
        self.create(title="Release 1.0.0", target_branch="main", labels=["semver-bump"])
