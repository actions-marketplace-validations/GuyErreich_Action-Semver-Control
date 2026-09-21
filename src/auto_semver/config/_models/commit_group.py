# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Commit group configuration models."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Constants
CONVENTIONAL_COMMIT_PARTS = 2

type RegexPattern = str


@dataclass
class Commit:
    r"""
    Parsed commit message data structure for template rendering.

    This dataclass represents a parsed commit message with extracted components
    that can be used in Jinja2 templates for changelog and PR generation.

    Attributes:
        title (str): The cleaned, display-friendly commit title/summary line.
                    For conventional commits, this extracts just the description part.
                    Used for concise commit listings in changelogs and PRs.
                    Example: "add OAuth2 support" (from "feat(auth): add OAuth2 support")

        body (str | None): The extended commit message body, if present.
                          Contains everything after the first line, preserving internal structure.
                          None if the commit only has a title line.
                          Used for detailed commit information in templates.
                          Example: "Implements OAuth2 authentication flow\n\nBREAKING CHANGE: ..."
    """

    title: str
    body: str | None = None


@dataclass
class CommitGroup:
    """
    Runtime data structure representing a single commit group with its commits.

    This dataclass represents a categorized group of commits that have been matched
    against specific patterns. Used as template data for Jinja2 rendering in
    changelogs and pull requests.

    Attributes:
        title (str): The display title for this group of commits.
            This appears as the section header in generated changelogs and PRs.
            Examples: "🚀 Features", "🐛 Bug Fixes", "📝 Documentation"

        commits (list[Commit]): List of parsed commit objects belonging to this group.
            Each commit contains title and optional body text.
            Sorted in the order they were processed from git history.

        priority (int): Numeric priority for sorting groups in output.
            Lower numbers appear first in generated content.
            Used to ensure consistent ordering (e.g., Features before Bug Fixes).

    Note:
        This is typically created by CommitGroupConfig.group_messages() and consumed
        by Jinja2 templates. Templates can iterate over commits and access their
        title/body for formatting.

    Example:
        Template usage:
        ```jinja2
        {% for group in commit_groups %}
        ## {{ group.title }}
        {% for commit in group.commits %}
        - {{ commit.title }}
        {% endfor %}
        {% endfor %}
        ```
    """

    title: str
    commits: list[Commit]
    priority: int


type CommitGroups = list[CommitGroup]
"""
Collection of commit groups for template rendering.

This type alias represents the complete data structure returned by commit grouping
operations and consumed by changelog/PR templates. It contains all categorized
commits organized by their matching patterns.

Note:
    This is the primary data structure passed to Jinja2 templates for rendering
    changelogs and pull request descriptions. Templates iterate over this list
    to generate formatted output with proper grouping and ordering.

Example:
    ```python
    commit_groups = CommitGroupConfig.group_messages(messages, config_groups)
    # Returns:
    [
        {"title": "🚀 Features", "commits": [...], "priority": 1},
        {"title": "🐛 Bug Fixes", "commits": [...], "priority": 2}
    ]
    ```

    Template usage:
    ```jinja2
    {% for group in commit_groups %}
    ## {{ group.title }}
    {% for commit in group.commits %}
    - {{ commit.title }}
    {% endfor %}
    {% endfor %}
    ```

Note:
    Processing details:
    - Groups are sorted by priority (lower numbers first)
    - Empty groups (no matching commits) are filtered out
    - Unmatched commits are placed in a catch-all or "Other Changes" group
    - Each group maintains the original git history order of its commits
"""


class CommitGroupConfig(BaseModel):
    """
    Defines a group for categorizing commit messages by regex patterns.

    Attributes:
        title (str): Display title for this group of commits.
        patterns (list[str]): List of regex patterns to match commit messages.
        priority (int): Sort priority (lower numbers appear first).
    """

    title: str = Field(..., description="Display title for this commit group")
    patterns: list[RegexPattern] = Field(..., description="List of regex patterns to match commits")
    match_groups: list[str] = Field(
        default_factory=list,
        description="List of exact commit section headers to match (e.g. 'Bug Fixes')",
    )
    priority: int = Field(..., description="Sort priority (lower numbers first)")

    @field_validator("patterns")
    @classmethod
    def validate_patterns(cls, patterns: list[RegexPattern]) -> list[RegexPattern]:
        """Validate that all patterns are valid regex."""
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as err:
                raise ValueError(f"Invalid regex pattern '{pattern}': {err}") from err
        return patterns
