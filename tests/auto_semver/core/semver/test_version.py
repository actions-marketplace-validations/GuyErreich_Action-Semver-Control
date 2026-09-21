"""
Unit tests for the Version class in auto_semver.core.semver.version module.

This module contains comprehensive tests for all methods and functionality
of the Version class, including parsing, bumping, comparison operations,
and string formatting.
"""

import operator
from typing import Any

import pytest

from auto_semver.core.semver.version import Version


class TestVersionInit:
    """Test cases for Version.__init__() method."""

    @pytest.mark.unit
    def test_basic_initialization(self) -> None:
        """Test basic version initialization with required parameters."""
        version = Version(major=1, minor=2, patch=3)

        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert version.title is None
        assert version.prefix is None
        assert version.suffix is None
        assert version.quote is None

    @pytest.mark.unit
    def test_initialization_with_all_parameters(self) -> None:
        """Test version initialization with all optional parameters."""
        version = Version(
            major=2, minor=5, patch=7, title="Version: ", prefix="v", suffix="-dev", quote='"'
        )

        assert version.major == 2
        assert version.minor == 5
        assert version.patch == 7
        assert version.title == "Version: "
        assert version.prefix == "v"
        assert version.suffix == "-dev"
        assert version.quote == '"'

    @pytest.mark.unit
    def test_initialization_with_zero_versions(self) -> None:
        """Test version initialization with zero values."""
        version = Version(major=0, minor=0, patch=0)

        assert version.major == 0
        assert version.minor == 0
        assert version.patch == 0


class TestVersionParse:
    """Test cases for Version.parse() static method."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "version_string,expected",
        [
            ("1.2.3", {"major": 1, "minor": 2, "patch": 3}),
            ("0.0.1", {"major": 0, "minor": 0, "patch": 1}),
            ("10.20.30", {"major": 10, "minor": 20, "patch": 30}),
        ],
    )
    def test_parse_basic_versions(self, version_string: str, expected: dict[str, int]) -> None:
        """Test parsing basic semantic version strings."""
        version = Version.parse(version_string)

        assert version.major == expected["major"]
        assert version.minor == expected["minor"]
        assert version.patch == expected["patch"]

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "version_string,expected_prefix",
        [
            ("v1.2.3", "v"),
            ("1.2.3", None),
        ],
    )
    def test_parse_with_prefix(self, version_string: str, expected_prefix: str | None) -> None:
        """Test parsing versions with and without 'v' prefix."""
        version = Version.parse(version_string)

        assert version.prefix == expected_prefix
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "version_string,expected_suffix",
        [
            ("1.2.3-dev", "-dev"),
            ("1.2.3-rc1", "-rc1"),
            ("1.2.3", None),
        ],
    )
    def test_parse_with_suffix(self, version_string: str, expected_suffix: str | None) -> None:
        """Test parsing versions with and without suffixes."""
        version = Version.parse(version_string)

        assert version.suffix == expected_suffix
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "version_string,expected_quote",
        [
            ('"1.2.3"', '"'),
            ("'1.2.3'", "'"),
            ("1.2.3", None),
        ],
    )
    def test_parse_with_quotes(self, version_string: str, expected_quote: str | None) -> None:
        """Test parsing versions with and without quotes."""
        version = Version.parse(version_string)

        assert version.quote == expected_quote
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "version_string,expected_title",
        [
            ("Version: 1.2.3", "Version: "),
            ("Release-Version: 1.2.3", "Release-Version: "),
            ("1.2.3", None),
        ],
    )
    def test_parse_with_title(self, version_string: str, expected_title: str | None) -> None:
        """Test parsing versions with and without titles."""
        version = Version.parse(version_string)

        assert version.title == expected_title
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3

    @pytest.mark.unit
    def test_parse_complex_version_string(self) -> None:
        """Test parsing a complex version string with all components."""
        version_string = 'Version: "v2.5.7-rc1"'
        version = Version.parse(version_string)

        assert version.title == "Version: "
        assert version.quote == '"'
        assert version.prefix == "v"
        assert version.major == 2
        assert version.minor == 5
        assert version.patch == 7
        assert version.suffix == "-rc1"

    @pytest.mark.unit
    @pytest.mark.edge_case
    @pytest.mark.parametrize(
        "invalid_string",
        [
            "invalid",
            "1.2",
            "1.2.3.4",
            "a.b.c",
            "1.2.x",
            "",
            "   ",
        ],
    )
    def test_parse_invalid_version_strings(self, invalid_string: str) -> None:
        """Test parsing invalid version strings raises ValueError."""
        with pytest.raises(ValueError, match="Invalid version format"):
            Version.parse(invalid_string)


class TestVersionParsePatterns:
    """Test comprehensive pattern matching for the Version class."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "version_string,expected",
        [
            # Basic formats
            (
                "1.2.3",
                {"major": 1, "minor": 2, "patch": 3, "title": None, "prefix": None, "suffix": None},
            ),
            (
                "v1.2.3",
                {"major": 1, "minor": 2, "patch": 3, "title": None, "prefix": "v", "suffix": None},
            ),
            (
                "1.2.3-dev",
                {
                    "major": 1,
                    "minor": 2,
                    "patch": 3,
                    "title": None,
                    "prefix": None,
                    "suffix": "-dev",
                },
            ),
            # With quotes
            (
                "'1.2.3'",
                {"major": 1, "minor": 2, "patch": 3, "title": None, "prefix": None, "quote": "'"},
            ),
            (
                '"1.2.3"',
                {"major": 1, "minor": 2, "patch": 3, "title": None, "prefix": None, "quote": '"'},
            ),
            # With titles - assignment format
            ("version = 1.2.3", {"major": 1, "minor": 2, "patch": 3, "title": "version = "}),
            (
                "version='1.2.3'",
                {"major": 1, "minor": 2, "patch": 3, "title": "version=", "quote": "'"},
            ),
            (
                'VERSION = "1.2.3"',
                {"major": 1, "minor": 2, "patch": 3, "title": "VERSION = ", "quote": '"'},
            ),
            (
                "__version__ = '1.2.3'",
                {"major": 1, "minor": 2, "patch": 3, "title": "__version__ = ", "quote": "'"},
            ),
            # With titles - colon format
            ("Version: 1.2.3", {"major": 1, "minor": 2, "patch": 3, "title": "Version: "}),
            (
                'VERSION: "1.2.3"',
                {"major": 1, "minor": 2, "patch": 3, "title": "VERSION: ", "quote": '"'},
            ),
            # Various combinations
            (
                "version = v1.2.3",
                {"major": 1, "minor": 2, "patch": 3, "title": "version = ", "prefix": "v"},
            ),
            (
                'version = "v1.2.3-rc1"',
                {
                    "major": 1,
                    "minor": 2,
                    "patch": 3,
                    "title": "version = ",
                    "prefix": "v",
                    "suffix": "-rc1",
                    "quote": '"',
                },
            ),
            # Complex real-world examples for various file formats
            (
                '"version": "1.2.3"',
                {"major": 1, "minor": 2, "patch": 3, "title": '"version": ', "quote": '"'},
            ),
            (
                '"version": "1.2.3",',
                {
                    "major": 1,
                    "minor": 2,
                    "patch": 3,
                    "title": '"version": ',
                    "quote": '"',
                    "trailer": ",",
                },
            ),
            (
                '  "version": "1.0.2-dev",',
                {
                    "major": 1,
                    "minor": 0,
                    "patch": 2,
                    "title": '  "version": ',
                    "suffix": "-dev",
                    "quote": '"',
                    "trailer": ",",
                },
            ),
            (
                'version= "1.2.3";',
                {
                    "major": 1,
                    "minor": 2,
                    "patch": 3,
                    "title": "version= ",
                    "quote": '"',
                    "trailer": ";",
                },
            ),
            # Trailer - semicolon + comment
            (
                'version= "1.2.3"; // comment',
                {
                    "major": 1,
                    "minor": 2,
                    "patch": 3,
                    "title": "version= ",
                    "quote": '"',
                    "trailer": "; // comment",
                },
            ),
            (
                "version= '1.2.3';# comment",
                {
                    "major": 1,
                    "minor": 2,
                    "patch": 3,
                    "title": "version= ",
                    "quote": "'",
                    "trailer": ";# comment",
                },
            ),
            # Trailer - comment only, no semicolon
            (
                'version= "1.2.3" // comment',
                {
                    "major": 1,
                    "minor": 2,
                    "patch": 3,
                    "title": "version= ",
                    "quote": '"',
                    "trailer": " // comment",
                },
            ),
            (
                'version= "1.2.3"   # inline',
                {
                    "major": 1,
                    "minor": 2,
                    "patch": 3,
                    "title": "version= ",
                    "quote": '"',
                    "trailer": "   # inline",
                },
            ),
            (
                'version= "1.2.3"\t// tabbed',
                {
                    "major": 1,
                    "minor": 2,
                    "patch": 3,
                    "title": "version= ",
                    "quote": '"',
                    "trailer": "\t// tabbed",
                },
            ),
        ],
    )
    def test_supported_version_patterns(
        self, version_string: str, expected: dict[str, object]
    ) -> None:
        """Test that all supported version patterns are correctly parsed."""
        try:
            version = Version.parse(version_string)

            # Check all expected attributes
            for attr, value in expected.items():
                assert getattr(version, attr) == value, (
                    f"Failed on '{version_string}': {attr} should be {value}, got {getattr(version, attr)}"
                )

            # Check numeric components are always present
            assert isinstance(version.major, int)
            assert isinstance(version.minor, int)
            assert isinstance(version.patch, int)

        except ValueError:
            pytest.fail(f"Failed to parse valid version string: '{version_string}'")

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "invalid_string",
        [
            # Invalid formats that should be rejected
            "invalid text",
            "1.2",  # Missing patch
            "1.2.3.4",  # Too many components
            "a.b.c",  # Non-numeric components
            "1.2.x",  # Invalid patch
            "",  # Empty string
            "   ",  # Whitespace only
            "version = abc",  # Invalid version after title
            "version = 1.2",  # Incomplete version
        ],
    )
    def test_unsupported_version_patterns(self, invalid_string: str) -> None:
        """Test that unsupported patterns are correctly rejected."""
        with pytest.raises(ValueError, match="Invalid version format"):
            Version.parse(invalid_string)


class TestVersionDetectBumpType:
    """Test cases for Version.detect_bump_type() static method."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "branch_name,expected_bump",
        [
            ("breaking/new-api", "major"),
            ("major/redesign", "major"),
            ("feature/user-auth", "minor"),
            ("fix/bug-123", "patch"),
            ("bug/memory-leak", "patch"),
            ("hotfix/security", "patch"),
            ("chore/update-deps", "patch"),
            ("devops/ci-improvement", "patch"),
        ],
    )
    def test_detect_bump_type_known_prefixes(self, branch_name: str, expected_bump: str) -> None:
        """Test bump type detection for known branch name prefixes."""
        bump_type = Version.detect_bump_type(branch_name)
        assert bump_type == expected_bump

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "branch_name",
        [
            "unknown/branch",
            "random-branch-name",
            "main",
            "develop",
            "feature-without-slash",
            "",
        ],
    )
    def test_detect_bump_type_unknown_prefixes_default_to_patch(self, branch_name: str) -> None:
        """Test that unknown branch prefixes default to patch bump."""
        bump_type = Version.detect_bump_type(branch_name)
        assert bump_type == "patch"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_detect_bump_type_case_sensitive(self) -> None:
        """Test that bump type detection is case sensitive."""
        # Uppercase should not match and default to patch
        bump_type = Version.detect_bump_type("FEATURE/new-feature")
        assert bump_type == "patch"


class TestVersionBumping:
    """Test cases for version bumping methods."""

    @pytest.mark.unit
    def test_bump_major(self) -> None:
        """Test major version bumping resets minor and patch."""

        version = Version(major=1, minor=5, patch=7)
        version.bump_major()

        assert version.major == 2
        assert version.minor == 0
        assert version.patch == 0

    @pytest.mark.unit
    def test_bump_minor(self) -> None:
        """Test minor version bumping resets patch but keeps major."""

        version = Version(major=2, minor=3, patch=8)
        version.bump_minor()

        assert version.major == 2
        assert version.minor == 4
        assert version.patch == 0

    @pytest.mark.unit
    def test_bump_patch(self) -> None:
        """Test patch version bumping keeps major and minor."""

        version = Version(major=3, minor=4, patch=5)
        version.bump_patch()

        assert version.major == 3
        assert version.minor == 4
        assert version.patch == 6

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "branch_name,expected_version",
        [
            ("breaking/change", (2, 0, 0)),
            ("major/update", (2, 0, 0)),
            ("feature/new", (1, 3, 0)),
            ("fix/bug", (1, 2, 4)),
            ("unknown/branch", (1, 2, 4)),  # defaults to patch
        ],
    )
    def test_bump_by_branch_name(
        self, branch_name: str, expected_version: tuple[int, int, int]
    ) -> None:
        """Test version bumping based on branch name patterns."""

        version = Version(major=1, minor=2, patch=3)
        version.bump(branch_name=branch_name)

        expected_major, expected_minor, expected_patch = expected_version
        assert version.major == expected_major
        assert version.minor == expected_minor
        assert version.patch == expected_patch

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_bump_from_zero_version(self) -> None:
        """Test bumping from 0.0.0 version."""

        version = Version(major=0, minor=0, patch=0)

        version.bump_patch()
        assert (version.major, version.minor, version.patch) == (0, 0, 1)

        version.bump_minor()
        assert (version.major, version.minor, version.patch) == (0, 1, 0)

        version.bump_major()
        assert (version.major, version.minor, version.patch) == (1, 0, 0)


class TestVersionSuffixManagement:
    """Test cases for suffix management methods."""

    @pytest.mark.unit
    def test_set_suffix(self) -> None:
        """Test setting a suffix on a version."""

        version = Version(major=1, minor=2, patch=3)
        version.set_suffix(suffix="-dev")

        assert version.suffix == "-dev"

    @pytest.mark.unit
    def test_set_suffix_replace_existing(self) -> None:
        """Test replacing an existing suffix."""

        version = Version(major=1, minor=2, patch=3, suffix="-rc1")
        version.set_suffix(suffix="-dev")

        assert version.suffix == "-dev"

    @pytest.mark.unit
    def test_set_suffix_to_none(self) -> None:
        """Test setting suffix to None removes it."""

        version = Version(major=1, minor=2, patch=3, suffix="-dev")
        version.set_suffix(suffix=None)

        assert version.suffix is None

    @pytest.mark.unit
    def test_remove_suffix(self) -> None:
        """Test removing a suffix from a version."""

        version = Version(major=1, minor=2, patch=3, suffix="-dev")
        version.remove_suffix()

        assert version.suffix is None

    @pytest.mark.unit
    def test_remove_suffix_when_none(self) -> None:
        """Test removing suffix when there is no suffix."""

        version = Version(major=1, minor=2, patch=3)
        version.remove_suffix()

        assert version.suffix is None


class TestVersionStringRepresentation:
    """Test cases for string representation methods."""

    @pytest.mark.unit
    def test_str_basic_version(self) -> None:
        """Test string representation of basic version."""

        version = Version(major=1, minor=2, patch=3)
        assert str(version) == "1.2.3"

    @pytest.mark.unit
    def test_str_version_with_suffix(self) -> None:
        """Test string representation with suffix."""

        version = Version(major=1, minor=2, patch=3, suffix="-dev")
        assert str(version) == "1.2.3-dev"

    @pytest.mark.unit
    def test_str_version_without_suffix(self) -> None:
        """Test string representation explicitly without suffix."""

        version = Version(major=1, minor=2, patch=3, suffix=None)
        assert str(version) == "1.2.3"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "version_data,expected",
        [
            ({"major": 1, "minor": 2, "patch": 3}, "1.2.3"),
            ({"major": 1, "minor": 2, "patch": 3, "prefix": "v"}, "v1.2.3"),
            ({"major": 1, "minor": 2, "patch": 3, "suffix": "-dev"}, "1.2.3-dev"),
            ({"major": 1, "minor": 2, "patch": 3, "quote": '"'}, '"1.2.3"'),
            ({"major": 1, "minor": 2, "patch": 3, "title": "Version: "}, "Version: 1.2.3"),
        ],
    )
    def test_format_full_line_components(self, version_data: dict[str, Any], expected: str) -> None:
        """Test full line formatting with various components."""

        version = Version(**version_data)
        assert version.format_full_line() == expected

    @pytest.mark.unit
    def test_format_full_line_complex(self) -> None:
        """Test full line formatting with all components."""

        version = Version(
            major=2, minor=1, patch=0, title="Release: ", prefix="v", suffix="-rc1", quote="'"
        )
        expected = "Release: 'v2.1.0-rc1'"
        assert version.format_full_line() == expected

    @pytest.mark.unit
    def test_format_full_line_no_title(self) -> None:
        """Test full line formatting without title."""

        version = Version(major=1, minor=2, patch=3, prefix="v", quote='"')
        expected = '"v1.2.3"'
        assert version.format_full_line() == expected


class TestVersionMergeFrom:
    """Test cases for merge_from() method."""

    @pytest.mark.unit
    def test_merge_from_basic(self) -> None:
        """Test merging version components from another version."""

        version1 = Version(major=1, minor=2, patch=3, title="Old: ", prefix="v")
        version2 = Version(major=4, minor=5, patch=6, suffix="-new")

        version1.merge_from(version2)

        # Version components should be updated
        assert version1.major == 4
        assert version1.minor == 5
        assert version1.patch == 6
        assert version1.suffix == "-new"

        # Title and prefix should be preserved
        assert version1.title == "Old: "
        assert version1.prefix == "v"

    @pytest.mark.unit
    def test_merge_from_preserves_formatting(self) -> None:
        """Test that merge_from preserves original formatting attributes."""

        version1 = Version(major=1, minor=2, patch=3, title="Version: ", prefix="v", quote='"')
        version2 = Version(major=2, minor=0, patch=0)

        version1.merge_from(version2)

        assert version1.major == 2
        assert version1.minor == 0
        assert version1.patch == 0
        assert version1.title == "Version: "  # preserved
        assert version1.prefix == "v"  # preserved
        assert version1.quote == '"'  # preserved

    @pytest.mark.unit
    def test_merge_from_suffix_overwrite(self) -> None:
        """Test that suffix is overwritten during merge."""

        version1 = Version(major=1, minor=2, patch=3, suffix="-old")
        version2 = Version(major=1, minor=2, patch=4, suffix="-new")

        version1.merge_from(version2)

        assert version1.suffix == "-new"

    @pytest.mark.unit
    def test_merge_from_none_suffix(self) -> None:
        """Test merging when target has None suffix."""

        version1 = Version(major=1, minor=2, patch=3, suffix="-dev")
        version2 = Version(major=1, minor=2, patch=4, suffix=None)

        version1.merge_from(version2)

        assert version1.suffix is None


class TestVersionComparison:
    """Test cases for version comparison methods."""

    @pytest.mark.unit
    def test_equality_same_versions(self) -> None:
        """Test equality of identical versions."""

        version1 = Version(major=1, minor=2, patch=3, suffix="-dev")
        version2 = Version(major=1, minor=2, patch=3, suffix="-dev")

        assert version1 == version2
        assert version2 == version1

    @pytest.mark.unit
    def test_equality_different_versions(self) -> None:
        """Test inequality of different versions."""

        version1 = Version(major=1, minor=2, patch=3)
        version2 = Version(major=1, minor=2, patch=4)

        assert version1 != version2
        assert version2 != version1

    @pytest.mark.unit
    def test_equality_different_suffixes(self) -> None:
        """Test that different suffixes make versions unequal."""

        version1 = Version(major=1, minor=2, patch=3, suffix="-dev")
        version2 = Version(major=1, minor=2, patch=3, suffix="-rc1")

        assert version1 != version2

    @pytest.mark.unit
    def test_equality_formatting_ignored(self) -> None:
        """Test that formatting attributes don't affect equality."""

        version1 = Version(major=1, minor=2, patch=3, title="V: ", prefix="v")
        version2 = Version(major=1, minor=2, patch=3, title="Version: ", prefix="")

        assert version1 == version2  # Only version numbers and suffix matter

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "version1_data,version2_data,expected",
        [
            ((1, 2, 3), (1, 2, 4), True),  # patch difference
            ((1, 2, 3), (1, 3, 0), True),  # minor difference
            ((1, 2, 3), (2, 0, 0), True),  # major difference
            ((2, 0, 0), (1, 9, 9), False),  # version1 is greater
            ((1, 2, 3), (1, 2, 3), False),  # equal versions
        ],
    )
    def test_less_than_comparison(
        self,
        version1_data: tuple[int, int, int],
        version2_data: tuple[int, int, int],
        expected: bool,
    ) -> None:
        """Test less than comparison for versions."""

        version1 = Version(major=version1_data[0], minor=version1_data[1], patch=version1_data[2])
        version2 = Version(major=version2_data[0], minor=version2_data[1], patch=version2_data[2])

        assert (version1 < version2) == expected

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "version1_data,version2_data,expected",
        [
            ((1, 2, 4), (1, 2, 3), True),  # patch difference
            ((1, 3, 0), (1, 2, 3), True),  # minor difference
            ((2, 0, 0), (1, 2, 3), True),  # major difference
            ((1, 9, 9), (2, 0, 0), False),  # version1 is smaller
            ((1, 2, 3), (1, 2, 3), False),  # equal versions
        ],
    )
    def test_greater_than_comparison(
        self,
        version1_data: tuple[int, int, int],
        version2_data: tuple[int, int, int],
        expected: bool,
    ) -> None:
        """Test greater than comparison for versions."""

        version1 = Version(major=version1_data[0], minor=version1_data[1], patch=version1_data[2])
        version2 = Version(major=version2_data[0], minor=version2_data[1], patch=version2_data[2])

        assert (version1 > version2) == expected

    @pytest.mark.unit
    def test_less_than_equal_comparison(self) -> None:
        """Test less than or equal comparison."""

        version1 = Version(major=1, minor=2, patch=3)
        version2 = Version(major=1, minor=2, patch=3)
        version3 = Version(major=1, minor=2, patch=4)

        assert version1 <= version2  # equal
        assert version1 <= version3  # less than

    @pytest.mark.unit
    def test_greater_than_equal_comparison(self) -> None:
        """Test greater than or equal comparison."""

        version1 = Version(major=1, minor=2, patch=3)
        version2 = Version(major=1, minor=2, patch=3)
        version3 = Version(major=1, minor=2, patch=2)

        assert version1 >= version2  # equal
        assert version1 >= version3  # greater than

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_comparison_with_non_version_returns_not_implemented(self) -> None:
        """Test that comparison with non-Version objects returns False."""

        version = Version(major=1, minor=2, patch=3)

        # These should return False when comparing with non-Version objects
        assert (version == "1.2.3") is False

        comparisons = [
            operator.lt,
            operator.gt,
            operator.le,
            operator.ge,
        ]

        for op in comparisons:
            with pytest.raises(TypeError):
                op(version, "1.2.3")

    @pytest.mark.unit
    def test_suffix_respected_in_prerelease_ordering(self) -> None:
        """Same core version: prerelease sorts below release; suffixes compare lexicographically."""
        version1 = Version(major=1, minor=2, patch=3, suffix="-dev")
        version2 = Version(major=1, minor=2, patch=4, suffix="-rc1")

        assert version1 < version2
        assert version2 > version1

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("lower", "higher"),
        [
            ("1.2.3-dev", "1.2.3-rc"),
            ("1.2.3-rc", "1.2.3"),
            ("1.2.3-dev", "1.2.3"),
            ("1.0.0-alpha", "1.0.0-alpha.1"),
            ("1.0.0-alpha.1", "1.0.0-alpha.beta"),
            ("1.0.0-alpha.beta", "1.0.0-beta"),
            ("1.0.0-beta", "1.0.0-beta.2"),
            ("1.0.0-beta.2", "1.0.0-beta.11"),
            ("1.0.0-beta.11", "1.0.0-rc.1"),
            ("1.0.0-rc.1", "1.0.0"),
        ],
    )
    def test_semver_prerelease_precedence_table(self, lower: str, higher: str) -> None:
        """Table-driven coverage of semver §11 prerelease precedence."""
        left = Version.parse(lower)
        right = Version.parse(higher)
        assert left < right
        assert right > left
        assert left <= right
        assert right >= left
        assert left != right

    @pytest.mark.unit
    def test_baseline_prefers_higher_open_release_with_prerelease(self) -> None:
        """bump._resolve_baseline_version uses > ; prerelease must not outrank a release."""
        baseline = Version.parse("1.2.3")
        open_release = Version.parse("1.2.3-rc.1")
        assert not (open_release > baseline)

    @pytest.mark.unit
    def test_promote_rejects_equal_or_lower_including_prerelease(self) -> None:
        """promote._validate_target_version uses <= ; 1.2.3-rc must not beat 1.2.3."""
        source = Version.parse("1.2.3-rc.1")
        target = Version.parse("1.2.3")
        assert source <= target


class TestVersionEdgeCases:
    """Test cases for edge cases and boundary conditions."""

    @pytest.mark.edge_case
    def test_very_large_version_numbers(self) -> None:
        """Test handling of very large version numbers."""

        version = Version(major=999999, minor=888888, patch=777777)

        assert str(version) == "999999.888888.777777"

        version.bump_patch()
        assert str(version) == "999999.888888.777778"

    @pytest.mark.edge_case
    def test_empty_string_components(self) -> None:
        """Test handling of empty string components."""

        version = Version(major=1, minor=2, patch=3, title="", prefix="", suffix="")

        assert version.title == ""
        assert version.prefix == ""
        assert version.suffix == ""
        assert str(version) == "1.2.3"

    @pytest.mark.edge_case
    def test_whitespace_in_parse_input(self) -> None:
        """Test parsing with leading/trailing whitespace."""

        version = Version.parse("  1.2.3  ")

        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3

    @pytest.mark.edge_case
    def test_version_with_special_characters_in_suffix(self) -> None:
        """Test version with special characters in suffix."""

        version = Version(major=1, minor=2, patch=3, suffix="-rc.1")

        assert str(version) == "1.2.3-rc.1"
        assert version.suffix == "-rc.1"
