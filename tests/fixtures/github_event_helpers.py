"""
Test utilities for generating GitHub event data.

This module provides a data class and helper functions to generate GitHub pull request
event data for testing purposes.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class GitHubPullRequestEventData:
    """
    Data class for generating GitHub pull request event data.

    This class provides a convenient way to create GitHub pull request event
    data for testing purposes with sensible defaults.

    Attributes:
        title: The title of the pull request.
        body: The body/description of the pull request.
        source_branch: The source branch name.
        target_branch: The target branch name.
        source_sha: The SHA of the source branch head.
        target_sha: The SHA of the target branch head.
        merge_commit_sha: The SHA of the merge commit.
        merged: Whether the pull request is merged.
        labels: List of label names applied to the pull request.
        repository: The repository in "owner/repo" format.

    """

    title: str
    body: str = ""
    source_branch: str = "feature-branch"
    target_branch: str = "main"
    source_sha: str = "abcd1234abcd1234abcd1234abcd1234abcd1234"
    target_sha: str = "efgh5678efgh5678efgh5678efgh5678efgh5678"
    merge_commit_sha: str = "ijkl9012ijkl9012ijkl9012ijkl9012ijkl9012"
    merged: bool = True
    labels: Sequence[str] = field(default_factory=lambda: ["semver-bump"])
    repository: str = "owner/repo"

    def to_event_dict(self) -> str:
        """
        Convert the data class into a pretty-printed JSON string representing a GitHub pull request event.

        Returns:
            str: A pretty-printed JSON string of the GitHub pull request event.

        """

        # Ensure labels are in the correct format: [{"name": label}, ...]
        formatted_labels = [{"name": label} for label in self.labels]

        event_dict = {
            "pull_request": {
                "title": self.title,
                "body": self.body,
                "head": {
                    "ref": self.source_branch,
                    "sha": self.source_sha,
                },
                "base": {
                    "ref": self.target_branch,
                    "sha": self.target_sha,
                },
                "merge_commit_sha": self.merge_commit_sha,
                "merged": self.merged,
                "labels": formatted_labels,
            },
            "repository": {
                "full_name": self.repository,
            },
        }

        return json.dumps(event_dict, indent=2)
