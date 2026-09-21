# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Commit message parsing utilities.

This module provides functionality to parse Git commit messages into structured data,
handling various formats including simple headers, detailed bodies, and complex
grouped changes within a single commit.
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ParsedCommit:
    """
    Structured representation of a parsed Git commit message.

    Attributes:
        header (str): The first line of the commit message.
        body (str | None): The raw body of the commit message (everything after the header).
        bullet_points (list[str]): List of simple bullet points found in the body (Type 2).
        sectioned_changes (dict[str, list[str]]): Map of section headers to lists of bullet points (Type 3).
    """

    header: str
    body: str | None = None
    bullet_points: list[str] = field(default_factory=list)
    sectioned_changes: dict[str, list[str]] = field(default_factory=dict)


class CommitParser:
    """
    Parses raw commit messages into structured ParsedCommit objects.

    Supports multiple formats:
    1. Simple header only.
    2. Header + simple body.
    3. Header + list of changes (bullet points).
    4. Header + grouped changes (sections with headers and bullet points).
    """

    def __init__(self, *, ignore_line_patterns: list[re.Pattern[str]] | None = None) -> None:
        """Initialize parser with optional line patterns to skip during body expansion."""
        self._ignore_line_patterns = ignore_line_patterns or []

    # Regex for identifying list items (-, *, or numeric 1.)
    _ITEM_PATTERN = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$")

    # Regex for identifying section headers in the body (e.g., "Bug Fixes:")
    # multiline mode is handled by processing line by line
    # Supports optional Markdown header prefix (e.g., "### Bug Fixes:")
    # Logic:
    # 1. Starts with # -> treated as header (colon optional)
    # 2. Starts with Capital letter -> must end with colon to be a header
    _SECTION_HEADER_PATTERN = re.compile(r"^(?:#+\s+(.*?)(?::)?|([A-Z].*?):)\s*$")

    # Regex for finding embedded headers (e.g. "text... ### Header:")
    # We look for " ## " or " ### " followed by text, to split lines.
    _EMBEDDED_HEADER_SPLIT = re.compile(r"(\s+)(#{2,}\s+[A-Z].*?)(?:\s|$)")

    def parse(self, message: str) -> ParsedCommit:
        """
        Parse a raw commit message string.

        Args:
            message (str): The raw Git commit message.

        Returns:
            ParsedCommit: The structured commit data.
        """
        if not message:
            logger.debug("Parsed empty commit message")
            return ParsedCommit(header="", body=None)

        parts = message.split("\n", 1)
        header = parts[0].strip()
        body = parts[1].strip() if len(parts) > 1 else None

        bullet_points, sectioned_changes = self._extract_structure(body) if body else ([], {})

        parsed = ParsedCommit(
            header=header,
            body=body,
            bullet_points=bullet_points,
            sectioned_changes=sectioned_changes,
        )
        logger.debug(
            "Parsed commit header=%r bullets=%d sections=%d",
            header,
            len(bullet_points),
            len(sectioned_changes),
        )
        return parsed

    def _extract_structure(self, body: str) -> tuple[list[str], dict[str, list[str]]]:
        """
        Extract detailed structure (bullets and sections) from the commit body.

        Returns:
            tuple: (bullet_points, sectioned_changes)
        """
        bullet_points: list[str] = []
        sectioned_changes: dict[str, list[str]] = {}
        current_group: str | None = None

        # Pre-process body to split embedded headers onto new lines
        # This handles cases like: "Added feature. ### Testing:"
        body = self._EMBEDDED_HEADER_SPLIT.sub(r"\n\2\n", body)

        # Split body into lines and process
        lines = body.splitlines()

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            # Check for section header
            section_match = self._SECTION_HEADER_PATTERN.match(line)
            if section_match:
                # If group 1 matched (Markdown style), use it.
                # If group 2 matched (Legacy style without #), use it.
                header_text = section_match.group(1) or section_match.group(2)
                current_group = header_text.strip()
                if current_group not in sectioned_changes:
                    sectioned_changes[current_group] = []
                continue

            # Check for generic markdown headers (structural break)
            # If a line starts with '#' but wasn't matched as a section header,
            # it's a structural break (e.g., "## 🧪 Testing").
            if line.startswith("#"):
                current_group = None
                continue

            # Check for list item
            item_match = self._ITEM_PATTERN.match(line)
            if item_match:
                description = item_match.group(1).strip()
                if self._should_ignore(description):
                    continue
                if current_group:
                    sectioned_changes[current_group].append(description)
                else:
                    bullet_points.append(description)
                continue

            # If line is text but not a header or list item, it's a continuation of the previous item
            if current_group and sectioned_changes[current_group]:
                sectioned_changes[current_group][-1] += f" {line}"
            elif bullet_points:
                bullet_points[-1] += f" {line}"

        return bullet_points, sectioned_changes

    def _should_ignore(self, text: str) -> bool:
        """Return True when text matches a configured ignore pattern."""
        return any(pattern.search(text.strip()) for pattern in self._ignore_line_patterns)
