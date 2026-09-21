# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""
CHANGELOG management module.

This module provides a class for appending or truncating changelog entries
based on a semantic versioning context. It is typically used during CI/CD release
automation in GitHub Actions workflows.

Typical usage::

    manager = ChangelogManager()
    manager.write("1.0.1", ["Fix bug", "Improve logging"])
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from auto_semver.config import Config
from auto_semver.core.commits.grouper import CommitGrouper
from auto_semver.templates.engine import get_template_engine
from auto_semver.templates.utils import format_date_iso_to_custom

if TYPE_CHECKING:
    from auto_semver.config import CommitGroupConfig

logger = logging.getLogger(__package__)


_DEFAULT_COMMIT_PLACEHOLDER: str = "Miscellaneous changes"


class ChangelogManager:
    """
    Manage the changelog file, allowing updates and truncation.

    This class supports rendering a changelog entry using a customizable template,
    with options to append to or truncate the changelog content.
    It also supports loading configuration from a `Config` instance.
    """

    def __init__(
        self,
        *,
        path: Path,
        truncate: bool,
        template: str,
        header: str,
        footer: str,
    ) -> None:
        """Initialize a changelog manager.

        Args:
            path: Path to the changelog file.
            truncate: Whether to overwrite existing content instead of prepending.
            template: Template string for rendering changelog entries.
            header: Header text.
            footer: Footer text.
        """
        self.path = path
        self.truncate = truncate
        self.template = template
        self.header = header
        self.footer = footer
        # Initialize template engine for this manager
        self._engine = get_template_engine()
        self._register_changelog_functions()

    def _register_changelog_functions(self) -> None:
        """Register changelog-specific template functions."""
        # Register changelog-specific functions
        self._engine.register_function("format_date_changelog", self._format_date_changelog)

    def _format_date_changelog(self, date_str: str, fmt: str = "%d-%m-%Y") -> str:
        """Format date strings for changelog display.

        Args:
            date_str: Date string in YYYY-MM-DD format.
            fmt: Target format string (default: "%d-%m-%Y").

        Returns:
            Formatted date string, or original string if parsing fails.

        Examples:
            >>> manager = ChangelogManager(Path("test.md"), False, "", "", "")
            >>> manager._format_date_changelog("2024-12-25", "%B %d, %Y")
            'December 25, 2024'
            >>> manager._format_date_changelog("invalid-date")
            'invalid-date'
        """
        return format_date_iso_to_custom(date_str, fmt)

    @classmethod
    def from_config(cls, config: Config) -> ChangelogManager:
        """
        Instantiate the manager using values from a Config instance.

        Args:
            config: The Config instance to extract changelog parameters from.

        Returns:
            ChangelogManager instance initialized from the config.

        """
        return cls(
            path=Path(config.data.changelog.file),
            truncate=config.data.changelog.truncate,
            template=config.data.changelog.template,
            header=config.data.changelog.header or "",
            footer=config.data.changelog.footer or "",
        )

    def render_template(self, template_vars: dict[str, object]) -> str:
        """
        Render the changelog template with the provided variables.

        Args:
            template_vars: Dictionary of variables to use in template rendering.

        Returns:
            Rendered template string.

        Raises:
            ValueError: If template rendering fails due to missing variables or syntax errors.
            TypeError: If template variables are of incorrect type.
        """
        # Validate required template variables
        required_vars = ["version", "date"]
        missing_vars = [var for var in required_vars if var not in template_vars]
        if missing_vars:
            raise ValueError(f"Missing required template variables: {missing_vars}")

        try:
            # Add backward compatibility alias for grouped_messages
            enhanced_vars = template_vars.copy()
            if "commit_groups" in enhanced_vars and "grouped_messages" not in enhanced_vars:
                enhanced_vars["grouped_messages"] = enhanced_vars["commit_groups"]

            return self._engine.render_template(self.template, enhanced_vars)
        except Exception as e:
            logger.error(f"Failed to render changelog template: {e}")
            logger.debug(f"Template: {self.template}")
            logger.debug(f"Variables: {list(template_vars.keys())}")
            raise ValueError(f"Changelog template rendering failed: {e}") from e

    def update(
        self,
        *,
        version: str,
        messages: list[str],
        commit_groups: list[CommitGroupConfig] | None = None,
    ) -> None:
        """
        Update the changelog file with the provided version and commit messages.

        Args:
            version: The version string to record (e.g., 1.2.3).
            messages: A list of commit messages to include under the version.
            commit_groups: Optional commit groups for grouping messages.

        Raises:
            IOError: If writing to the changelog file fails.

        """
        logger.info("Updating changelog file.")

        if not messages:
            logger.warning("No commit messages provided. Adding default message.")
            messages = [_DEFAULT_COMMIT_PLACEHOLDER]

        grouped_data = (
            CommitGrouper.group_messages(messages, commit_groups) if commit_groups else None
        )

        # Manager handles all template rendering
        template_vars: dict[str, object] = {
            "version": version,
            "date": date.today().strftime("%d-%m-%Y"),
            "messages": messages,
        }

        # Add both canonical and legacy names for commit groups
        if grouped_data is not None:
            template_vars["commit_groups"] = grouped_data
            template_vars["grouped_messages"] = grouped_data  # backward compatibility

        # Use manager's template engine with registered functions
        rendered = self._engine.render_template(self.template, template_vars)

        # Compose updated content
        if not self.path.exists():
            content = self._compose_new_changelog(rendered)
        else:
            with open(self.path, encoding="utf-8") as f:
                existing = f.read().strip()
            content = self._compose_updated_changelog(existing=existing, rendered=rendered)

        logger.debug(f"Final file content: {content}")

        with open(self.path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Changelog update complete.")

    def _compose_new_changelog(self, rendered: str) -> str:
        """
        Compose the initial changelog content.

        Args:
            rendered: The newly rendered changelog entry.

        Returns:
            Combined changelog string.

        """
        parts = [self.header.strip(), rendered.strip(), self.footer.strip()]
        return "\n\n".join(part for part in parts if part)

    def _compose_updated_changelog(self, *, existing: str, rendered: str) -> str:
        """
        Compose the updated changelog content, either truncating or prepending.

        Args:
            existing: The existing changelog content.
            rendered: The newly rendered changelog entry.

        Returns:
            Updated changelog content as a string.

        """
        if self.truncate:
            logger.debug("Truncating the file")
            return self._compose_new_changelog(rendered)

        body = self._strip_header_footer(existing)
        parts = [self.header.strip(), rendered.strip(), body, self.footer.strip()]
        return "\n\n".join(part for part in parts if part)

    def _strip_header_footer(self, content: str) -> str:
        """Remove a known header/footer so recomposition does not duplicate them."""
        text = content.strip()
        header = self.header.strip()
        footer = self.footer.strip()
        if header and text.startswith(header):
            text = text[len(header) :].lstrip("\n")
        if footer and text.endswith(footer):
            text = text[: -len(footer)].rstrip("\n")
        return text.strip()

    def update_version_in_header(self, *, old_version: str, new_version: str) -> bool:
        """
        Update the version string in the changelog header.

        This replaces occurrences of `[old_version]` with `[new_version]`.

        Args:
            old_version: The version string to replace (e.g., '1.3.14-dev').
            new_version: The new version string (e.g., '1.3.14').

        Returns:
            bool: True if the file was modified, False otherwise.
        """
        if not self.path.exists():
            logger.warning(f"Changelog file {self.path} does not exist.")
            return False

        logger.info(f"Updating version header in changelog: {old_version} -> {new_version}")

        with open(self.path, encoding="utf-8") as f:
            content = f.read()

        # Simple string replacement for the header format `[version]`
        old_pattern = f"[{old_version}]"
        new_pattern = f"[{new_version}]"

        if old_pattern not in content:
            logger.warning(f"Version header for '{old_version}' not found in changelog.")
            return False

        new_content = content.replace(old_pattern, new_pattern, 1)

        with open(self.path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return True
