# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""
Commit message grouping logic.

This module provides the core logic for categorizing commit messages into groups
based on configuration. It is responsible for parsing commits, matching them
against patterns/sections, and organizing them into structure ready for templates.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

# Runtime construction of schema value objects when applying Config — see AGENT.md.
from auto_semver.config import Commit, CommitGroup, CommitGroupsConfig
from auto_semver.core.commits.parser import CommitParser

if TYPE_CHECKING:
    from auto_semver.config import CommitGroupConfig, CommitGroups

logger = logging.getLogger(__name__)

# Constants
CONVENTIONAL_COMMIT_PARTS = 2


class CommitGrouper:
    """Logic for grouping commit messages based on configuration."""

    @staticmethod
    def group_messages(
        messages: list[str],
        commit_groups: list[CommitGroupConfig] | CommitGroupsConfig,
    ) -> CommitGroups:
        """
        Group commit messages by patterns and return data ready for Jinja templates.

        Args:
            messages: List of raw commit messages from git.
            commit_groups: Group definitions, optionally wrapped with summary settings.

        Returns:
            CommitGroups containing grouped_messages with parsed commits organized by group.
        """
        settings = (
            commit_groups
            if isinstance(commit_groups, CommitGroupsConfig)
            else CommitGroupsConfig(groups=commit_groups)
        )
        groups_config = settings.groups

        if not messages:
            logger.info("Grouped 0 messages into 0 commit groups")
            return []

        if not groups_config:
            commits = [CommitGrouper._parse_commit(msg) for msg in messages]
            default_group = CommitGroup(title="📝 Changes", commits=commits, priority=1)
            logger.info(
                "Grouped %d messages into 1 commit groups",
                len(messages),
            )
            return [default_group]

        sorted_groups = sorted(groups_config, key=lambda g: g.priority)
        ignore_patterns = [re.compile(p) for p in settings.ignore_line_patterns]
        parser = CommitParser(ignore_line_patterns=ignore_patterns)

        groups: dict[str, CommitGroup] = {
            g.title: CommitGroup(title=g.title, commits=[], priority=g.priority)
            for g in sorted_groups
        }

        unmatched_commits: list[Commit] = []

        for message in messages:
            CommitGrouper._process_message(
                parser,
                message,
                sorted_groups,
                groups,
                unmatched_commits,
                summary_mode=settings.summary_mode,
            )

        if unmatched_commits:
            CommitGrouper._handle_unmatched(unmatched_commits, sorted_groups, groups)

        result: CommitGroups = []
        for group in groups.values():
            if group.commits:
                result.append(group)

        result = sorted(result, key=lambda g: g.priority)
        logger.info(
            "Grouped %d messages into %d commit groups",
            len(messages),
            len(result),
        )
        return result

    @staticmethod
    def _resolve_group(
        text: str, section: str | None, groups: list[CommitGroupConfig]
    ) -> CommitGroupConfig | None:
        """Find matching group for text/section."""
        if section:
            for group in groups:
                if section in group.match_groups:
                    return group

        for group in groups:
            if CommitGrouper._message_matches(text, group.patterns):
                return group
        return None

    @staticmethod
    def _process_message(
        parser: CommitParser,
        message: str,
        sorted_groups: list[CommitGroupConfig],
        groups: dict[str, CommitGroup],
        unmatched_commits: list[Commit],
        *,
        summary_mode: str = "header_only",
    ) -> None:
        """Process a single commit message and sort into groups."""
        parsed = parser.parse(message)

        if summary_mode == "header_only":
            CommitGrouper._process_header(
                parsed.header, parsed.body, sorted_groups, groups, unmatched_commits
            )
            return

        if parsed.sectioned_changes:
            CommitGrouper._process_sections(
                parsed.sectioned_changes, sorted_groups, groups, unmatched_commits
            )

        if parsed.bullet_points:
            CommitGrouper._process_bullets(
                parsed.bullet_points, sorted_groups, groups, unmatched_commits
            )

        if not parsed.sectioned_changes and not parsed.bullet_points:
            CommitGrouper._process_header(
                parsed.header, parsed.body, sorted_groups, groups, unmatched_commits
            )

    @staticmethod
    def _should_ignore_line(text: str, ignore_patterns: list[re.Pattern[str]]) -> bool:
        """Return True when a parsed line matches an ignore pattern."""
        stripped = text.strip()
        return any(pattern.search(stripped) for pattern in ignore_patterns)

    @staticmethod
    def _process_sections(
        sections: dict[str, list[str]],
        sorted_groups: list[CommitGroupConfig],
        groups: dict[str, CommitGroup],
        unmatched_commits: list[Commit],
    ) -> None:
        """Process Type 3 commits (grouped sections)."""
        for section, items in sections.items():
            group = CommitGrouper._resolve_group("", section, sorted_groups)

            if group:
                for item_text in items:
                    groups[group.title].commits.append(Commit(title=item_text))
            else:
                for item_text in items:
                    item_group = CommitGrouper._resolve_group(item_text, None, sorted_groups)
                    commit = Commit(title=item_text)
                    if item_group:
                        groups[item_group.title].commits.append(commit)
                    else:
                        unmatched_commits.append(commit)

    @staticmethod
    def _process_bullets(
        bullets: list[str],
        sorted_groups: list[CommitGroupConfig],
        groups: dict[str, CommitGroup],
        unmatched_commits: list[Commit],
    ) -> None:
        """Process Type 2 commits (flat bullet points)."""
        for item_text in bullets:
            group = CommitGrouper._resolve_group(item_text, None, sorted_groups)
            commit = Commit(title=item_text)

            if group:
                groups[group.title].commits.append(commit)
            else:
                unmatched_commits.append(commit)

    @staticmethod
    def _process_header(
        header: str,
        body: str | None,
        sorted_groups: list[CommitGroupConfig],
        groups: dict[str, CommitGroup],
        unmatched_commits: list[Commit],
    ) -> None:
        """Process Type 1 commits (header only)."""
        group = CommitGrouper._resolve_group(header, None, sorted_groups)
        title = CommitGrouper._clean_conv_title(header)
        commit = Commit(title=title, body=body)

        if group:
            groups[group.title].commits.append(commit)
        else:
            unmatched_commits.append(commit)

    @staticmethod
    def _clean_conv_title(title: str) -> str:
        """Clean conventional commit title."""
        if ":" in title:
            parts = title.split(":", 1)
            if len(parts) == CONVENTIONAL_COMMIT_PARTS:
                clean_title = parts[1].strip()
                if clean_title:
                    return clean_title
        return title

    @staticmethod
    def _handle_unmatched(
        commits: list[Commit],
        config_groups: list[CommitGroupConfig],
        groups: dict[str, CommitGroup],
    ) -> None:
        """Handle unmatched commits by adding to catch-all or default group."""
        catch_all_config = next((g for g in config_groups if ".*" in g.patterns), None)

        if catch_all_config:
            groups[catch_all_config.title].commits.extend(commits)
        else:
            other_title = "Other Changes"
            if other_title not in groups:
                groups[other_title] = CommitGroup(title=other_title, commits=[], priority=999)
            groups[other_title].commits.extend(commits)

    @staticmethod
    def _message_matches(message: str, patterns: list[str]) -> bool:
        """Check if message matches any of the regex patterns (case insensitive)."""
        for pattern in patterns:
            try:
                if re.match(pattern, message, re.IGNORECASE):
                    return True
            except re.error as err:
                logger.warning(f"Invalid regex pattern '{pattern}': {err}")
        return False

    @staticmethod
    def _parse_commit(message: str) -> Commit:
        """
        Parse commit message into title and body.

        For conventional commits like "feat: add thing", extracts "add thing" as title.
        """
        lines = message.strip().split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 and lines[1].strip() else None

        if ":" in title:
            parts = title.split(":", 1)
            if len(parts) == CONVENTIONAL_COMMIT_PARTS:
                clean_title = parts[1].strip()
                if clean_title:
                    title = clean_title

        return Commit(title=title, body=body)
