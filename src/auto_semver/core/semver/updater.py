# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
version_updater.py.

This module provides a class for updating version strings in text files.
It uses the Version object to intelligently detect and replace version lines
while preserving original prefixes, quotes, titles, and formatting structure.

Typical use case:
    updater = VersionFileUpdater(file_path="README.md", version=Version("1.2.3"))
    updater.update()
"""

import logging

from auto_semver.core.semver.version import Version

logger = logging.getLogger(__package__)


class VersionFileUpdater:
    """
    Handle version updates in structured version declaration lines across files.

    This class is designed to parse and update version lines in files,
    preserving the original prefix/title/quote structure of each matched line.
    It uses the Version object to intelligently detect and replace version lines.
    """

    def __init__(self, *, file_path: str, version: "Version") -> None:
        """
        Initialize the VersionFileUpdater with a file path and a new version.

        Args:
            file_path (str): The file to update.
            version (Version): The new Version object to apply.

        """
        self.file_path = file_path
        self.new_version = version

    def update(self) -> None:
        """
        Parse and updates all version lines in the file to the new version.

        Preserves the original prefix/title/quote structure of each matched line.
        """
        try:
            with open(self.file_path, "r+", encoding="utf-8") as f:
                lines = f.readlines()
                updated_lines = []

                for line in lines:
                    try:
                        current = Version.parse(line)
                        current.merge_from(self.new_version)
                        updated_line = current.format_full_line()
                        logger.debug("Updated: %s -> %s", line.strip(), updated_line.strip())
                        updated_lines.append(updated_line + "\n")
                    except ValueError:
                        updated_lines.append(line)

                f.seek(0)
                f.writelines(updated_lines)
                f.truncate()

            logger.info("Updated version in %s to %s", self.file_path, self.new_version)

        except FileNotFoundError:
            logger.warning("File not found: %s. Skipping.", self.file_path)
        except Exception as e:
            logger.error("Failed to update version in %s: %s", self.file_path, e)
            raise
