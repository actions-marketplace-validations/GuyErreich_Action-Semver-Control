# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Semantic versioning utilities for Auto-Semver pipelines.

This module provides a `Version` class for managing semantic versioning, including
parsing, bumping (major, minor, patch), setting suffixes, and converting to strings.

Typical usage example::

    version = Version.parse("1.2.3")
    version.bump_patch()
    version.set_suffix("-dev")
    print(str(version))  # "1.2.4-dev"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import total_ordering
from typing import Any

logger = logging.getLogger(__package__)

# --- Title matching (before version number) ---
TITLE_PART = r"""
(?P<title>
    [ \t]*                             # indentation support
    (?:-[ ]|\#[ ])?                            # YAML support
    ["']?                              # optional opening quote
    (?:_|__)?                          # Python dunder support
    (?:[Pp]ackage-|[Rr]elease-)?      # optional version title prefixes
    (?:version|Version|VERSION)        # version title
    _{0,2}                              # closing dunder support
    ["']?                              # optional closing quote
    [ \t]*                              # YAML formatting alignment
    [=:]                                # assignment or mapping
    [ ]?                                # optional space
)?
"""

# --- Version (quoted) ---
QUOTED_VERSION_PART = r"""
(?:
    (?P<quote>["'])                    # opening quote
    (?P<prefix>v)?                     # optional 'v'
    (?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)
    (?!\.[\d])                         # forbid 4th segment
    (?P<suffix>-[\w]+(?:\.[\w]+)*)?    # optional suffix
    (?P=quote)                         # matching closing quote
)
"""

# --- Version (unquoted) ---
UNQUOTED_VERSION_PART = r"""
(?:
    (?P<prefix2>v)?
    (?P<major2>\d+)\.(?P<minor2>\d+)\.(?P<patch2>\d+)
    (?!\.[\d])
    (?P<suffix2>-[\w]+(?:\.[\w]+)*)?
)
"""

# --- Trailer (comma, semicolon, or comment) ---
# JSON mid-object lines keep a trailing comma after the version value.
TRAILER_PART = r"""
(?P<trailer>
    ,                                   # JSON trailing comma
  | ;(?:[ \t]*(?:\#|//).*)?             # semicolon + optional comment
  | [ \t]*(?:\#|//).*                   # comment-only
)?
"""

# --- Final Regex ---
_VERSION_PATTERN = re.compile(
    rf"""^
        {TITLE_PART}
        (?:{QUOTED_VERSION_PART}|{UNQUOTED_VERSION_PART})
        {TRAILER_PART}
        $
    """,
    re.VERBOSE | re.MULTILINE,
)

_MAJOR_PREFIXES = ("breaking/", "major/")
_MINOR_PREFIXES = ("feature/",)
_PATCH_PREFIXES = ("fix/", "bug/", "hotfix/", "chore/", "devops/")


@dataclass(frozen=True)
class BumpCounts:
    """Aggregated branch-driven bump counts for cumulative mode."""

    feature_count: int = 0
    fix_count: int = 0
    has_major: bool = False


@total_ordering
class Version:
    """
    Represents a semantic version, optionally with prefix, suffix, or title.

    Attributes:
        title (str | None): Optional title or label before version string.
        prefix (str | None): Optional 'v' prefix.
        major (int): Major version component.
        minor (int): Minor version component.
        patch (int): Patch version component.
        suffix (str | None): Optional suffix like '-dev' or '-rc.1'.
        quote (str | None): Optional surrounding quote (" or ').
        trailer (str | None): Optional trailing text after the version (redundant text like comments).

    """

    def __init__(
        self,
        *,
        major: int,
        minor: int,
        patch: int,
        title: str | None = None,
        prefix: str | None = None,
        suffix: str | None = None,
        quote: str | None = None,
        trailer: str | None = None,
    ) -> None:
        """
        Initialize a Version object.

        Args:
            major (int): Major version number.
            minor (int): Minor version number.
            patch (int): Patch version number.
            title (str | None): Optional title or label before version string.
            prefix (str | None): Optional 'v' prefix.
            suffix (str | None): Optional suffix like '-dev' or '-rc.1'.
            quote (str | None): Optional surrounding quote (" or ').
            trailer (str | None): Optional trailing text after the version (redundant text like comments).

        """

        self.major = major
        self.minor = minor
        self.patch = patch
        self.title = title
        self.prefix = prefix
        self.suffix = suffix
        self.quote = quote
        self.trailer = trailer

    @staticmethod
    def parse(version_line: str) -> Version:
        """
        Parse a version line and returns a Version object.

        Args:
            version_line: The raw version string to parse.

        Returns:
            A Version instance.

        Raises:
            ValueError: If the version format is invalid.

        """

        logger.debug(f"Parsing version line: {version_line}")

        # Match on a stripped body so bare versions like ``  1.2.3  `` still
        # parse, but remember leading indentation for JSON/YAML round-trips.
        raw = version_line.rstrip("\r\n")
        indent_len = len(raw) - len(raw.lstrip(" \t"))
        indent = raw[:indent_len]
        body = raw[indent_len:].rstrip()

        match = _VERSION_PATTERN.match(body)
        if not match:
            raise ValueError("Invalid version format")

        groups = match.groupdict()
        title = groups["title"] if "title" in groups else None
        if indent:
            title = f"{indent}{title or ''}"

        version = Version(
            title=title,
            prefix=groups["prefix"] or groups["prefix2"] or None,
            major=int(groups["major"] or groups["major2"]),
            minor=int(groups["minor"] or groups["minor2"]),
            patch=int(groups["patch"] or groups["patch2"]),
            suffix=groups["suffix"] or groups["suffix2"] or None,
            quote=groups["quote"] or None,
            trailer=groups["trailer"] or None,
        )

        logger.debug(
            f"Parsed version components - "
            f"Title: {version.title}, Prefix: {version.prefix}, "
            f"Major: {version.major}, Minor: {version.minor}, "
            f"Patch: {version.patch}, Suffix: {version.suffix}, "
            f"Quote: {version.quote}, Trailer: {version.trailer}"
        )

        return version

    @staticmethod
    def detect_bump_type(branch_name: str) -> str:
        """
        Determine bump type based on Git branch naming conventions.

        This method analyzes the branch name to determine the type of version bump
        that should be applied. It categorizes the branch names into three types:
        - Major: For branches starting with 'breaking/' or 'major/'.
        - Minor: For branches starting with 'feature/'.
        - Patch: For branches starting with 'fix/', 'bug/', 'hotfix/', 'chore/',
          or 'devops/'.

        Note:
            If the branch name does not match any of these patterns, it defaults to 'patch'.

        Args:
            branch_name (str): The name of the branch to analyze.

        Returns:
            One of 'major', 'minor', or 'patch'.

        """

        bump_type: str = "patch"  # Default bump type

        logger.debug(f"Detecting bump type for branch: {branch_name}")

        if any(branch_name.startswith(prefix) for prefix in _MAJOR_PREFIXES):
            bump_type = "major"
        elif any(branch_name.startswith(prefix) for prefix in _MINOR_PREFIXES):
            bump_type = "minor"
        elif any(branch_name.startswith(prefix) for prefix in _PATCH_PREFIXES):
            bump_type = "patch"

        logger.debug(f"Bump type detected: {bump_type}")

        return bump_type

    @staticmethod
    def count_branch_bumps(branch_names: list[str]) -> BumpCounts:
        """Count feature, fix, and major signals from merged branch names."""
        feature_count = 0
        fix_count = 0
        has_major = False

        for branch_name in branch_names:
            if any(branch_name.startswith(prefix) for prefix in _MAJOR_PREFIXES):
                has_major = True
            elif any(branch_name.startswith(prefix) for prefix in _MINOR_PREFIXES):
                feature_count += 1
            elif any(branch_name.startswith(prefix) for prefix in _PATCH_PREFIXES):
                fix_count += 1
            else:
                fix_count += 1

        return BumpCounts(
            feature_count=feature_count,
            fix_count=fix_count,
            has_major=has_major,
        )

    def bump_cumulative(self, *, branch_names: list[str]) -> BumpCounts:
        """
        Apply cumulative bump rules from merged branch names.

        Major bumps reset minor/patch. Otherwise minor += features and patch += fixes
        without resetting patch on minor increments.
        """
        counts = self.count_branch_bumps(branch_names)

        if counts.has_major:
            self.bump_major()
            return counts

        if counts.feature_count:
            self.minor += counts.feature_count
        if counts.fix_count:
            self.patch += counts.fix_count

        logger.info(
            "Cumulative bump applied: +%s minor, +%s patch from %s branches",
            counts.feature_count,
            counts.fix_count,
            len(branch_names),
        )
        return counts

    def bump_major(self) -> None:
        """Increments the major version and resets minor and patch to 0."""

        logger.info(f"Bumping major version: {self.major} -> {self.major + 1}")

        self.major += 1
        self.minor = 0
        self.patch = 0

    def bump_minor(self) -> None:
        """Increments the minor version and resets patch to 0."""

        logger.info(f"Bumping minor version: {self.minor} -> {self.minor + 1}")

        self.minor += 1
        self.patch = 0

    def bump_patch(self) -> None:
        """Increments the patch version."""

        logger.info(f"Bumping patch version: {self.patch} -> {self.patch + 1}")

        self.patch += 1

    def bump(self, *, branch_name: str) -> None:
        """
        Bumps the version based on the branch name.

        This method determines the type of version bump (major, minor, or patch)
        based on the branch name and applies the appropriate bump method.

        The branch name is analyzed to detect the type of change:
        - Major: For branches starting with 'breaking/' or 'major/'.
        - Minor: For branches starting with 'feature/'.
        - Patch: For branches starting with 'fix/', 'bug/', 'hotfix/', 'chore/',
          or 'devops/'.

        Note:
            If the branch name does not match any of these patterns, it defaults to 'patch'.

        Args:
            branch_name (str): The name of the branch to analyze.

        """

        bump_type: str = self.detect_bump_type(branch_name)

        match bump_type:
            case "major":
                self.bump_major()
            case "minor":
                self.bump_minor()
            case _:
                self.bump_patch()

    def set_suffix(self, *, suffix: str | None) -> None:
        """
        Set a new suffix (e.g. -dev, -rc.1) on the version.

        Args:
            suffix: Suffix string to apply or None to clear it.

        """

        logger.info(f"Setting suffix: {self.suffix} -> {suffix}")

        self.suffix = suffix

    def remove_suffix(self) -> None:
        """Remove the suffix from the version object."""

        logger.info(f"Removing suffix: {self.suffix}")

        self.suffix = None

    def __str__(self) -> str:
        """Return the version string in the format 'major.minor.patch' or 'major.minor.patch-suffix'."""

        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.suffix:
            version += self.suffix

        return f"{version}"

    def format_full_line(self) -> str:
        """Return the full version string, including title, prefix, and quotes if present."""

        title = self.title or ""
        prefix = self.prefix or ""
        suffix = self.suffix or ""
        quote = self.quote or ""
        trailer = self.trailer or ""

        return (
            f"{title}{quote}{prefix}{self.major}.{self.minor}.{self.patch}{suffix}{quote}{trailer}"
        )

    def merge_from(self, other: Version) -> None:
        """
        Merge version components (major, minor, patch, suffix) from another Version instance.

        This method copies the version components from the provided Version instance
        to the current instance. It does not modify the title or prefix of the current instance.
        This is useful for updating the version components based on another Version instance.

        Note:
            This method does not return a new Version instance; it modifies the current instance in place.

        Example:
            version1 = Version(1, 2, 3)
            version2 = Version(4, 5, 6)
            version1.merge_from(version2)
            # version1 is now 4.5.6

        Args:
            other (Version): The Version instance from which to copy the version components.

        """

        self.major = other.major
        self.minor = other.minor
        self.patch = other.patch
        self.suffix = other.suffix

    def __eq__(self, other: object) -> bool:
        """Check if the two given versions are equal."""
        if not isinstance(other, Version):
            return NotImplemented

        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.suffix == other.suffix
        )

    def __hash__(self) -> int:
        """Return hash value for the version object."""
        return hash((self.major, self.minor, self.patch, self.suffix))

    def _prerelease_identifiers(self) -> tuple[tuple[int, int | str], ...] | None:
        """Parse suffix into semver §11 prerelease identifiers, or None if release."""
        if not self.suffix:
            return None
        raw = self.suffix[1:] if self.suffix.startswith("-") else self.suffix
        if not raw:
            return None
        identifiers: list[tuple[int, int | str]] = []
        for part in raw.split("."):
            if part.isdigit():
                # Numeric identifiers sort before non-numeric (tag 0 vs 1)
                identifiers.append((0, int(part)))
            else:
                identifiers.append((1, part))
        return tuple(identifiers)

    def _precedence_key(self) -> tuple[Any, ...]:
        """Build a comparable key per semver §11 (prerelease sorts below release)."""
        pre = self._prerelease_identifiers()
        # is_prerelease=0 sorts before is_prerelease=1 so 1.0.0-rc < 1.0.0
        if pre is None:
            return (self.major, self.minor, self.patch, 1, ())
        return (self.major, self.minor, self.patch, 0, pre)

    def __lt__(self, other: object) -> bool:
        """Check if the current instance of the version is smaller than the given version."""
        if not isinstance(other, Version):
            return NotImplemented

        return self._precedence_key() < other._precedence_key()
