"""
Unit tests for the ChangelogManager class in auto_semver.core.changelog.manager module.

This module contains comprehensive tests for all methods and functionality
of the ChangelogManager class, including initialization, content generation, and
file operations.
"""

import datetime
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from auto_semver.config import Config
from auto_semver.core.changelog.manager import _DEFAULT_COMMIT_PLACEHOLDER, ChangelogManager
from tests.fixtures.changelog_fixture import ChangelogFixture


class TestChangelogManagerInit:
    """Test cases for ChangelogManager.__init__() method."""

    @pytest.mark.unit
    def test_basic_initialization(self) -> None:
        """Test basic changelog manager initialization with required parameters."""
        manager = ChangelogManager(
            path=Path("CHANGELOG.md"),
            truncate=False,
            template="## [{{version}}]",
            header="# Changelog",
            footer="",
        )

        assert manager.path == Path("CHANGELOG.md")
        assert manager.truncate is False
        assert manager.template == "## [{{version}}]"
        assert manager.header == "# Changelog"
        assert manager.footer == ""


class TestChangelogManagerFromConfig:
    """Test cases for ChangelogManager.from_config() method."""

    @pytest.mark.unit
    def test_from_config(self, mocker: MockerFixture) -> None:
        """Test creation of changelog manager from config object."""
        # Create mock Config object
        mock_config = mocker.Mock(spec=Config)

        # Create and attach a mock data object with changelog attributes
        mock_data = mocker.Mock()
        mock_changelog = mocker.Mock()

        # Define changelog properties
        mock_changelog.file = "test_changelog.md"
        mock_changelog.truncate = True
        mock_changelog.template = "## [{{version}}] - {{date}}"
        mock_changelog.header = "# Test Changelog"
        mock_changelog.footer = "## License"

        # Set up the object hierarchy
        mock_data.changelog = mock_changelog
        mock_config.data = mock_data

        # Create manager from config
        manager = ChangelogManager.from_config(mock_config)

        # Validate properties
        assert manager.path == Path("test_changelog.md")
        assert manager.truncate is True
        assert manager.template == "## [{{version}}] - {{date}}"
        assert manager.header == "# Test Changelog"
        assert manager.footer == "## License"

    @pytest.mark.unit
    def test_from_config_with_none_values(self, mocker: MockerFixture) -> None:
        """Test creation of changelog manager from config with None values for optional fields."""
        # Create mock Config object with None values for header and footer
        mock_config = mocker.Mock(spec=Config)

        # Create and attach a mock data object with changelog attributes
        mock_data = mocker.Mock()
        mock_changelog = mocker.Mock()

        # Define changelog properties with None values for header and footer
        mock_changelog.file = "CHANGELOG.md"
        mock_changelog.truncate = False
        mock_changelog.template = "## [{{version}}]"
        mock_changelog.header = None
        mock_changelog.footer = None

        # Set up the object hierarchy
        mock_data.changelog = mock_changelog
        mock_config.data = mock_data

        # Create manager from config
        manager = ChangelogManager.from_config(mock_config)

        # Validate properties - header and footer should be empty strings
        assert manager.header == ""
        assert manager.footer == ""


class TestChangelogManagerUpdate:
    """Test cases for ChangelogManager.update() method."""

    @pytest.fixture
    def mock_today(self, mocker: MockerFixture) -> None:
        """Mock date.today() in the changelog manager module to return a fixed date."""

        class FakeDate(datetime.date):
            @classmethod
            def today(cls) -> "FakeDate":
                return cls(2025, 6, 18)

        mocker.patch("auto_semver.core.changelog.manager.date", FakeDate)

    @pytest.mark.unit
    def test_update_new_file(
        self, empty_changelog_path: Path, mock_today: None, mocker: MockerFixture
    ) -> None:
        """Test updating a changelog that doesn't exist yet."""

        # Create manager
        manager = ChangelogManager(
            path=empty_changelog_path,
            truncate=False,
            template="## [{{version}}] - {{date}}\n{% for msg in messages %}\n- {{ msg }}\n{% endfor %}",
            header="# Changelog",
            footer="## License",
        )

        # Update changelog
        manager.update(version="1.0.0", messages=["Feature A", "Bugfix B"])

        # Verify file was created
        assert empty_changelog_path.exists()
        # We're only checking that it exists with some basic content, not the exact format
        # since the date formatting is mocked differently
        content = empty_changelog_path.read_text()
        assert "# Changelog" in content
        assert "## [1.0.0]" in content
        assert "Feature A" in content
        assert "Bugfix B" in content
        assert "## License" in content

    @pytest.mark.unit
    def test_update_existing_file_append(
        self, changelog_fixture: ChangelogFixture, mock_today: None
    ) -> None:
        """Test appending to an existing changelog."""
        # Create changelog with existing content
        existing_content = "# Changelog\n\n## [0.9.0] - 15-06-2025\n\n- Old feature\n"
        changelog_path = changelog_fixture.write(existing_content)

        # Create manager that appends (truncate=False)
        manager = ChangelogManager(
            path=changelog_path,
            truncate=False,
            template="## [{{version}}] - {{date}}\n{% for msg in messages %}\n- {{ msg }}\n{% endfor %}",
            header="# Changelog",
            footer="",
        )

        # Update changelog
        manager.update(version="1.0.0", messages=["New feature"])

        # Verify file was updated with the right content
        content = changelog_path.read_text()
        # Check for the presence of key elements rather than exact format
        assert "# Changelog" in content
        assert "## [1.0.0]" in content
        assert "New feature" in content
        assert "## [0.9.0]" in content
        assert "Old feature" in content

    @pytest.mark.unit
    def test_update_existing_file_truncate(
        self, changelog_fixture: ChangelogFixture, mock_today: None
    ) -> None:
        """Test truncating an existing changelog."""
        # Create changelog with existing content
        existing_content = "# Changelog\n\n## [0.9.0] - 15-06-2025\n\n- Old feature\n"
        changelog_path = changelog_fixture.write(existing_content)

        # Create manager that truncates (truncate=True)
        manager = ChangelogManager(
            path=changelog_path,
            truncate=True,
            template="## [{{version}}] - {{date}}\n{% for msg in messages %}\n- {{ msg }}\n{% endfor %}",
            header="# Changelog",
            footer="",
        )

        # Update changelog
        manager.update(version="1.0.0", messages=["New feature"])

        # Verify file was truncated and updated
        content = changelog_path.read_text()
        # Check for the presence of key elements rather than exact format
        assert "# Changelog" in content
        assert "## [1.0.0]" in content
        assert "New feature" in content
        assert "## [0.9.0]" not in content  # Should be gone due to truncation

    @pytest.mark.unit
    def test_update_empty_messages(
        self, empty_changelog_path: Path, mock_today: None, mocker: MockerFixture
    ) -> None:
        """Test updating with empty messages list uses default placeholder."""

        # Mock logger
        mock_logger = mocker.patch("auto_semver.core.changelog.manager.logger")

        # Create manager
        manager = ChangelogManager(
            path=empty_changelog_path,
            truncate=False,
            template="## [{{version}}] - {{date}}\n{% for msg in messages %}\n- {{ msg }}\n{% endfor %}",
            header="# Changelog",
            footer="",
        )

        # Update changelog with empty messages
        manager.update(version="1.0.0", messages=[])

        # Check for both warnings - order doesn't matter
        mock_logger.warning.assert_any_call("No commit messages provided. Adding default message.")

        # Verify default message was used
        content = empty_changelog_path.read_text()
        assert _DEFAULT_COMMIT_PLACEHOLDER in content

    @pytest.mark.unit
    def test_update_io_error(
        self, empty_changelog_path: Path, mock_today: None, mocker: MockerFixture
    ) -> None:
        """Test handling of IO errors when updating the changelog."""

        # Create manager
        manager = ChangelogManager(
            path=empty_changelog_path,
            truncate=False,
            template="## [{{version}}] - {{date}}\n{% for msg in messages %}\n- {{ msg }}\n{% endfor %}",
            header="# Changelog",
            footer="",
        )

        # Mock open to raise OSError
        mocker.patch("builtins.open", side_effect=OSError("Permission denied"))

        # Update should raise the OSError
        with pytest.raises(OSError, match="Permission denied"):
            manager.update(version="1.0.0", messages=["Feature"])


class TestChangelogManagerComposeNewChangelog:
    """Test cases for ChangelogManager._compose_new_changelog() method."""

    @pytest.mark.unit
    def test_compose_new_changelog_with_all_parts(self, empty_changelog_path: Path) -> None:
        """Test composition of a new changelog with header, content, and footer."""
        manager = ChangelogManager(
            path=empty_changelog_path,
            truncate=False,
            template="",
            header="# Changelog",
            footer="## License",
        )

        result = manager._compose_new_changelog("## [1.0.0]")
        expected = "# Changelog\n\n## [1.0.0]\n\n## License"
        assert result == expected

    @pytest.mark.unit
    def test_compose_new_changelog_without_footer(self, empty_changelog_path: Path) -> None:
        """Test composition of a new changelog without footer."""
        manager = ChangelogManager(
            path=empty_changelog_path,
            truncate=False,
            template="",
            header="# Changelog",
            footer="",
        )

        result = manager._compose_new_changelog("## [1.0.0]")
        expected = "# Changelog\n\n## [1.0.0]"
        assert result == expected

    @pytest.mark.unit
    def test_compose_new_changelog_without_header(self, empty_changelog_path: Path) -> None:
        """Test composition of a new changelog without header."""
        manager = ChangelogManager(
            path=empty_changelog_path,
            truncate=False,
            template="",
            header="",
            footer="## License",
        )

        result = manager._compose_new_changelog("## [1.0.0]")
        expected = "## [1.0.0]\n\n## License"
        assert result == expected


class TestChangelogManagerComposeUpdatedChangelog:
    """Test cases for ChangelogManager._compose_updated_changelog() method."""

    @pytest.mark.unit
    def test_compose_updated_changelog_truncate(self, empty_changelog_path: Path) -> None:
        """Test composition when truncate is True."""
        manager = ChangelogManager(
            path=empty_changelog_path,
            truncate=True,
            template="",
            header="# Changelog",
            footer="## License",
        )

        # When truncate is True, the existing content should be ignored
        result = manager._compose_updated_changelog(existing="## [0.9.0]", rendered="## [1.0.0]")
        expected = "# Changelog\n\n## [1.0.0]\n\n## License"
        assert result == expected

    @pytest.mark.unit
    def test_compose_updated_changelog_append(self, empty_changelog_path: Path) -> None:
        """Test composition when truncate is False (append mode)."""
        manager = ChangelogManager(
            path=empty_changelog_path,
            truncate=False,
            template="",
            header="# Changelog",
            footer="## License",
        )

        # When truncate is False, the existing content should be included after the new content
        result = manager._compose_updated_changelog(existing="## [0.9.0]", rendered="## [1.0.0]")
        expected = "# Changelog\n\n## [1.0.0]\n\n## [0.9.0]\n\n## License"
        assert result == expected

    @pytest.mark.unit
    def test_compose_updated_changelog_strips_existing_header_footer(
        self, empty_changelog_path: Path
    ) -> None:
        """Existing content that already has header/footer must not re-wrap them."""
        manager = ChangelogManager(
            path=empty_changelog_path,
            truncate=False,
            template="",
            header="# Changelog",
            footer="## License",
        )

        existing = "# Changelog\n\n## [0.9.0]\n\n## License"
        result = manager._compose_updated_changelog(existing=existing, rendered="## [1.0.0]")
        assert result.count("# Changelog") == 1
        assert result.count("## License") == 1
        assert "## [1.0.0]" in result
        assert "## [0.9.0]" in result

    @pytest.mark.unit
    def test_update_three_releases_no_header_footer_duplication(
        self, empty_changelog_path: Path
    ) -> None:
        """Three consecutive updates with truncate=False keep a single header and footer."""
        manager = ChangelogManager(
            path=empty_changelog_path,
            truncate=False,
            template="## [{{ version }}]",
            header="# Changelog",
            footer="## License",
        )

        for version in ("1.0.0", "1.1.0", "1.2.0"):
            manager.update(version=version, messages=[f"msg-{version}"])

        content = empty_changelog_path.read_text(encoding="utf-8")
        assert content.count("# Changelog") == 1
        assert content.count("## License") == 1
        assert "## [1.2.0]" in content
        assert "## [1.1.0]" in content
        assert "## [1.0.0]" in content
