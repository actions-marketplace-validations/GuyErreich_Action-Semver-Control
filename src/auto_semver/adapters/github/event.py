# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""
GitHub Actions context utilities.

This module provides helper classes and functions to extract relevant data
(branch name, commit SHA, etc.) from GitHub-provided event payloads.
It is typically used inside CI/CD pipelines triggered by pull request or push events.

Typical usage::

    event = GitHubEvent()
    branch_name = event.get_branch_name()
    commit_sha = event.get_commit_sha()
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__package__)

_GITHUB_EVENT_PATH_ENV = "GITHUB_EVENT_PATH"
_PULL_REQUEST_KEY = "pull_request"


class GitHubEvent:
    """
    Encapsulates GitHub event data for convenient access to pull request information.

    Loads and parses the event payload once during instantiation, and provides methods
    to extract specific fields like branch name, commit SHA, and merge status.
    """

    def __init__(self) -> None:
        """Initialize the GitHubEvent by loading the event payload once."""
        self._event_data = self._load_event_data()

    def _load_event_data(self) -> dict[str, Any]:
        """
        Load GitHub event data from a JSON file defined by the environment variable.

        Returns:
            dict[str, Any]: Parsed JSON data.

        Raises:
            RuntimeError: If the environment variable is missing or the file can't be read.

        """

        event_path = os.getenv(_GITHUB_EVENT_PATH_ENV)
        if not event_path:
            logger.error(f"{_GITHUB_EVENT_PATH_ENV} is not set.")
            raise RuntimeError(f"{_GITHUB_EVENT_PATH_ENV} is not set in environment.")

        logger.debug(f"Reading event data from {event_path}")
        try:
            with open(event_path) as f:
                return dict[str, Any](json.load(f))
        except (OSError, json.JSONDecodeError) as err:
            logger.error(f"Failed to load event data: {err}")
            raise RuntimeError(f"Failed to load GitHub event data: {err}") from err

    def _get(self, path: list[str]) -> Any:
        """
        Retrieve a nested value from the loaded event data.

        Args:
            path: A list of keys forming the path to the desired value.

        Returns:
            Any: The value at the given path.

        Raises:
            RuntimeError: If a key along the path is missing.

        """

        try:
            data = self._event_data
            for key in path:
                data = data[key]
            return data
        except KeyError as err:
            dotted_path = ".".join(path)
            logger.error(f"Missing key in event data at path '{dotted_path}': {err}")
            raise RuntimeError(f"Malformed event data: missing '{dotted_path}'") from err

    def is_merged(self) -> bool:
        """
        Check whether the pull request was merged.

        Returns:
            bool: True if merged, False otherwise.

        Raises:
            RuntimeError: If the merged key is missing in the event data.

        """

        return bool(self._get([_PULL_REQUEST_KEY, "merged"]))

    def get_source_branch_name(self) -> str:
        """
        Get the source branch name from the pull request event data.

        Returns:
            str: The name of the source branch.

        Raises:
            RuntimeError: If the branch name is missing in the event data.

        """

        return str(self._get([_PULL_REQUEST_KEY, "head", "ref"]))

    def get_source_commit_sha(self) -> str:
        """
        Get the commit SHA of the source branch from the pull request event data.

        Returns:
            str: The commit SHA of the source branch.

        Raises:
            RuntimeError: If the sha is missing in the event data.

        """

        return str(self._get([_PULL_REQUEST_KEY, "head", "sha"]))

    def get_target_branch_name(self) -> str:
        """
        Get the target branch name from the pull request event data.

        Returns:
            str: The name of the target branch.

        Raises:
            RuntimeError: If the branch name is missing in the event data.

        """

        return str(self._get([_PULL_REQUEST_KEY, "base", "ref"]))

    def get_target_commit_sha(self) -> str:
        """
        Get the commit SHA of the target branch from the pull request event data.

        Returns:
            str: The commit SHA of the target branch.

        Raises:
            RuntimeError: If the sha is missing in the event data.

        """

        return str(self._get([_PULL_REQUEST_KEY, "base", "sha"]))

    def get_merged_commit_sha(self) -> str:
        """
        Get the commit SHA of the merged pull request.

        Returns:
            str: The merge commit SHA.

        Raises:
            RuntimeError: If the pull request was not merged.
            RuntimeError: If the merge commit SHA is missing in the event data.

        """

        if not self.is_merged():
            logger.error("The pull request was closed but not merged.")
            raise RuntimeError("The pull request was closed but not merged.")

        return str(self._get([_PULL_REQUEST_KEY, "merge_commit_sha"]))

    def get_body(self) -> str:
        """Return the PR body."""
        return str(self._get([_PULL_REQUEST_KEY, "body"]))

    def get_title(self) -> str:
        """Return the PR title."""
        return str(self._get([_PULL_REQUEST_KEY, "title"]))

    def get_labels(self) -> list[str]:
        """Return the PR labels."""
        labels: list[dict[str, Any]] = self._get([_PULL_REQUEST_KEY, "labels"])

        if not labels:
            raise ValueError("No labels found")

        labels_str: list[str] = [label["name"] for label in labels]

        return labels_str

    def get_labels_safe(self) -> list[str]:
        """
        Return the PR labels safely.

        If no labels are found return an empty list.
        """
        try:
            return self.get_labels()
        except ValueError:
            return []

    def get_repository(self) -> str:
        """Return the repository full name."""
        return str(self._get(["repository", "full_name"]))
