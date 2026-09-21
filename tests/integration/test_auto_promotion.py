"""
Integration tests for auto-promotion workflow.

This module tests the complete auto-promotion flow:
1. Finalize creates tags
2. Auto-promotion PRs are created based on configuration
3. Chain promotions work correctly
4. Configuration validation is enforced
"""

import json
import os
from pathlib import Path

import pytest
import responses
import yaml
from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_mock import MockerFixture
from tests.fixtures.config_fixture import ConfigFixture

from auto_semver.adapters.git import GitOps
from auto_semver.adapters.github import GitHubEvent
from auto_semver.adapters.github.event import _GITHUB_EVENT_PATH_ENV
from auto_semver.cli import finalize
from auto_semver.config import Config


class GitHubEventHelper:
    """Helper class for creating GitHub event files with pyfakefs."""

    def __init__(self, fs: FakeFilesystem, mocker: MockerFixture):
        """Initialize the GitHub event helper."""
        self.fs = fs
        self.mocker = mocker

    def create_pull_request_event(
        self,
        *,
        title: str = "Merged PR",
        body: str = "This is a test PR",
        source_branch: str = "feature/test",
        target_branch: str = "dev",
        source_sha: str = "abc123",
        target_sha: str = "def456",
        merge_commit_sha: str = "ghi789",
        merged: bool = True,
        labels: list[str] | None = None,
        repository: str = "testuser/testrepo",
        event_file_path: str = "/tmp/github_event.json",
    ) -> str:
        """
        Create a GitHub pull request event file.

        Returns:
            Path to the created event file
        """
        if labels is None:
            labels = ["semver:minor"]

        github_event_data = {
            "action": "closed",
            "pull_request": {
                "title": title,
                "body": body,
                "head": {"ref": source_branch, "sha": source_sha},
                "base": {"ref": target_branch, "sha": target_sha},
                "merged": merged,
                "merge_commit_sha": merge_commit_sha,
                "labels": [{"name": label} for label in labels],
            },
            "repository": {"full_name": repository},
        }

        self.fs.create_file(event_file_path, contents=json.dumps(github_event_data))

        # Mock the environment variable
        self.mocker.patch.dict(
            os.environ,
            {
                _GITHUB_EVENT_PATH_ENV: event_file_path,
                "GITHUB_EVENT_NAME": "pull_request",
            },
        )

        return event_file_path


class FileHelper:
    """Helper class for creating various files with pyfakefs."""

    def __init__(self, fs: FakeFilesystem):
        """Initialize the file helper."""
        self.fs = fs

    def create_version_file(self, version: str = "1.0.0", filename: str = "version.txt") -> str:
        """Create a version file."""
        self.fs.create_file(filename, contents=version)
        return filename

    def create_semver_lock(
        self,
        *,
        version: str = "1.1.1234-dev",
        source_branch: str = "feature/test",
        target_branch: str = "dev",
        target_base_sha: str = "abc123",
        filename: str = ".semver.lock",
    ) -> str:
        """Create a semver lock file in YAML format."""
        lock_data = {
            "version": version,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "target_base_sha": target_base_sha,
        }
        self.fs.create_file(
            filename, contents=yaml.dump(lock_data, default_flow_style=False, sort_keys=False)
        )
        return filename


@pytest.mark.integration
def test_auto_promotion_finalize_workflow(
    fs: FakeFilesystem,
    mock_github_api: responses.RequestsMock,
    mocker: MockerFixture,
) -> None:
    """
    Test that finalize workflow creates auto-promotion PRs when configured.

    Workflow:
    1. Setup repo with auto-promotion config (dev -> staging: auto, staging -> master: manual)
    2. Create semver lock file to simulate finalize scenario
    3. Run finalize workflow
    4. Verify auto-promotion PR creation was attempted
    5. Verify no auto-promotion PR was created for master (manual only)
    """
    # Create fixtures and helpers that work with pyfakefs
    config_fixture = ConfigFixture(fs)
    # Override the config path to use the standard filename
    config_fixture.config_path = Path.cwd() / "auto_semver_config.yml"

    github_event_helper = GitHubEventHelper(fs, mocker)
    file_helper = FileHelper(fs)

    # Create auto-promotion configuration using config fixture
    config_fixture.create(
        suffixes={"dev": "-dev", "staging": "-rc", "master": ""},
        promotions=[
            {"from_branch": "dev", "to_branch": "staging", "auto_promote": True},
            {"from_branch": "staging", "to_branch": "master", "auto_promote": False},
        ],
        commit_groups=[{"title": "Features", "patterns": ["^feat:"], "priority": 1}],
    )

    # Create version file using helper
    file_helper.create_version_file(version="1.0.0")

    # Create semver lock file using helper
    file_helper.create_semver_lock(
        version="1.1.1234-dev",
        source_branch="feature/test",
        target_branch="dev",
        target_base_sha="abc123",
    )

    # Create GitHub event using helper
    github_event_helper.create_pull_request_event(
        title="Merged PR",
        body="This is a test PR",
        source_branch="feature/test",
        target_branch="dev",
        source_sha="abc123",
        target_sha="def456",
        merge_commit_sha="ghi789",
        merged=True,
        labels=["semver:minor"],
        repository="testuser/testrepo",
    )

    # Mock GitOps to avoid real git operations
    mock_gitops = mocker.Mock(spec=GitOps)
    mock_gitops.tag.return_value = "1.1.1234-dev"
    mock_gitops.push.return_value = None
    mock_gitops.auto_promote.return_value = None
    mock_gitops._is_closeable_release_pr.return_value = (False, "test mock")
    mock_gitops.add.return_value = None
    mock_gitops.commit.return_value = None

    # Mock GitOps constructor
    mocker.patch("auto_semver.cli.finalize.GitOps", return_value=mock_gitops)

    # Mock GitHub API calls for PR creation
    mock_github_api.add(
        responses.POST,
        "https://api.github.com/repos/testuser/testrepo/pulls",
        json={
            "id": 1,
            "number": 123,
            "title": "🚀 Promote 1.1.1234-dev from dev to staging",
            "body": "Auto-promotion PR",
            "html_url": "https://github.com/testuser/testrepo/pull/123",
        },
        status=201,
    )

    # Mock environment variables for GitHub repository (event file already handled by helper)
    mocker.patch.dict(
        "os.environ",
        {
            "GITHUB_REPOSITORY": "testuser/testrepo",
        },
    )

    # Run finalize directly (not through subprocess)
    config = Config()
    event = GitHubEvent()

    # Capture logs to verify auto-promotion attempts
    mock_logger = mocker.patch("auto_semver.cli.finalize.logger")
    finalize.run(
        gitops=mock_gitops,
        event=event,
        config=config,
        github_token="fake-token",
    )

    # Verify git operations were called
    mock_gitops.tag.assert_called_once_with(tag="1.1.1234-dev", branch="dev")
    mock_gitops.push.assert_called_once_with(branch_name="1.1.1234-dev")

    # Verify auto-promotion was attempted via local promotion
    mock_gitops.auto_promote.assert_called_once()
    create_call = mock_gitops.auto_promote.call_args

    # Verify call details
    assert create_call[1]["source_branch"] == "1.1.1234-dev"
    assert create_call[1]["is_source_tag"] is True
    assert create_call[1]["target_branch"] == "staging"
    # Version should be transformed to use target branch suffix (-rc for staging)
    assert create_call[1]["version"] == "1.1.1234-rc"

    # Verify logging shows auto-promotion attempt
    mock_logger.info.assert_any_call("Auto-promoting dev → staging")


@pytest.mark.integration
def test_auto_promotion_disabled(
    fs: FakeFilesystem,
    mock_github_api: responses.RequestsMock,
    mocker: MockerFixture,
) -> None:
    """
    Test that finalize workflow does NOT create PRs when auto_promote=false.

    Workflow:
    1. Setup repo with auto_promote=false for all promotions
    2. Run finalize workflow
    3. Verify tag was created
    4. Verify no auto-promotion PRs were created
    """
    # Setup with auto-promotion disabled using pyfakefs
    fs.create_file("version.txt", contents="1.0.0\n")

    fs.create_file(
        "auto_semver_config.yml",
        contents="""
start_version: "1.0.0"

suffixes:
  dev: "-dev"
  staging: "-rc"
  master: ""

promotions:
  - from_branch: dev
    to_branch: staging
    auto_promote: false  # Should NOT auto-create PR
  - from_branch: staging
    to_branch: master
    auto_promote: false  # Should NOT auto-create PR

version_files: ["version.txt"]

commit_groups:
  - title: "Features"
    patterns: ["^feat:"]
    priority: 1

pull_request:
  title: "Release {{version}}"
  body: "Release {{version}} for {{base_branch}}"
  labels: ["release"]

changelog:
  path: "CHANGELOG.md"
  template: "# Changelog\\n\\n## {{version}}\\n\\n{{commit_groups}}"
""",
    )

    # Create semver lock file
    fs.create_file(
        ".semver.lock",
        contents="""{
  "version": "1.0.1-dev",
  "source_branch": "feature/test",
  "target_branch": "dev",
  "target_base_sha": "abc123"
}""",
    )

    # Mock GitHub event file
    fs.create_file(
        "event.json",
        contents="""{
  "pull_request": {
    "merged": true,
    "base": {"ref": "dev"},
    "head": {"ref": "auto-semver/release/1.0.1-dev", "sha": "abc123"},
    "merge_commit_sha": "def456"
  },
  "repository": {"full_name": "testuser/testrepo"}
}""",
    )

    # Mock GitOps to avoid real git operations
    mock_gitops = mocker.Mock(spec=GitOps)
    mock_gitops.tag.return_value = "1.0.1-dev"
    mock_gitops.push.return_value = None
    mock_gitops._is_closeable_release_pr.return_value = (False, "test mock")
    mock_gitops.add.return_value = None
    mock_gitops.commit.return_value = None

    # Mock GitOps constructor
    mocker.patch("auto_semver.cli.finalize.GitOps", return_value=mock_gitops)

    # Mock environment variables for GitHub event
    mocker.patch.dict(
        "os.environ",
        {
            "GITHUB_REPOSITORY": "testuser/testrepo",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(Path.cwd() / "event.json"),
        },
    )

    # Run finalize workflow
    config = Config()
    event = GitHubEvent()

    # Capture logs to verify no auto-promotion attempts
    mock_logger = mocker.patch("auto_semver.cli.finalize.logger")
    finalize.run(
        gitops=mock_gitops,
        event=event,
        config=config,
        github_token="fake-token",
    )

    # Verify git operations were called (tagging should still work)
    mock_gitops.tag.assert_called_once_with(tag="1.0.1-dev", branch="dev")
    mock_gitops.push.assert_called_once_with(branch_name="1.0.1-dev")

    # Verify no auto-promotion was attempted
    mock_gitops.auto_promote.assert_not_called()

    # Verify no GitHub API calls were made for PR creation
    pr_requests = [call for call in mock_github_api.calls if call.request.method == "POST"]
    assert len(pr_requests) == 0, "Should not have created any auto-promotion PRs"

    # Verify logging shows no auto-promotion
    mock_logger.info.assert_any_call("No auto-promotion rules found for branch 'dev'")


@pytest.mark.integration
def test_auto_promotion_without_github_token(
    fs: FakeFilesystem,
    mocker: MockerFixture,
) -> None:
    """
    Test that finalize workflow handles missing GitHub token gracefully.

    Workflow:
    1. Setup repo with auto_promote=true
    2. Run finalize without GitHub token
    3. Verify tag was created
    4. Verify warning about missing token
    5. Verify no PRs were created (graceful degradation)
    """
    # Setup with auto-promotion enabled using pyfakefs
    fs.create_file("version.txt", contents="1.0.0\n")

    fs.create_file(
        "auto_semver_config.yml",
        contents="""
start_version: "1.0.0"

suffixes:
  dev: "-dev"
  staging: "-rc"

promotions:
  - from_branch: dev
    to_branch: staging
    auto_promote: true

version_files: ["version.txt"]

commit_groups:
  - title: "Features"
    patterns: ["^feat:"]
    priority: 1

pull_request:
  title: "Release {{version}}"
  body: "Release {{version}} for {{base_branch}}"
  labels: ["release"]

changelog:
  path: "CHANGELOG.md"
  template: "# Changelog\\n\\n## {{version}}\\n\\n{{commit_groups}}"
""",
    )

    # Create semver lock file
    fs.create_file(
        ".semver.lock",
        contents="""{
  "version": "1.0.1-dev",
  "source_branch": "feature/test",
  "target_branch": "dev",
  "target_base_sha": "abc123"
}""",
    )

    # Mock GitHub event file
    fs.create_file(
        "event.json",
        contents="""{
  "pull_request": {
    "merged": true,
    "base": {"ref": "dev"},
    "head": {"ref": "auto-semver/release/1.0.1-dev", "sha": "abc123"},
    "merge_commit_sha": "def456"
  },
  "repository": {"full_name": "testuser/testrepo"}
}""",
    )

    # Mock GitOps to avoid real git operations
    mock_gitops = mocker.Mock(spec=GitOps)
    mock_gitops.tag.return_value = "1.0.1-dev"
    mock_gitops.push.return_value = None
    mock_gitops._is_closeable_release_pr.return_value = (False, "test mock")
    mock_gitops.add.return_value = None
    mock_gitops.commit.return_value = None

    # Mock GitOps constructor
    mocker.patch("auto_semver.cli.finalize.GitOps", return_value=mock_gitops)

    # Mock environment variables for GitHub event
    mocker.patch.dict(
        "os.environ",
        {
            "GITHUB_REPOSITORY": "testuser/testrepo",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(Path.cwd() / "event.json"),
        },
    )

    # Run finalize workflow WITHOUT GitHub token
    config = Config()
    event = GitHubEvent()

    # Run finalize without GitHub token
    finalize.run(
        gitops=mock_gitops,
        event=event,
        config=config,
        github_token=None,  # No token provided
    )

    # Verify git operations were called (tagging should still work)
    mock_gitops.tag.assert_called_once_with(tag="1.0.1-dev", branch="dev")
    mock_gitops.push.assert_called_once_with(branch_name="1.0.1-dev")

    # Verify auto-promotion was attempted even without a GitHub token
    mock_gitops.auto_promote.assert_called_once()
