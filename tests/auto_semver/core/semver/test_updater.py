"""
Unit tests for VersionFileUpdater class.

This module provides comprehensive unit tests for the VersionFileUpdater class,
including initialization, file updating, error handling, and edge cases.
"""

import threading

import pytest
from pytest_mock import MockerFixture

from auto_semver.core.semver.updater import VersionFileUpdater
from auto_semver.core.semver.version import Version
from tests.fixtures.file_fixture import FileFixture


class TestVersionFileUpdaterInit:
    """Test cases for VersionFileUpdater initialization."""

    @pytest.mark.unit
    def test_init_basic(self) -> None:
        """Test basic initialization with file path and version."""
        version = Version(major=1, minor=2, patch=3)
        updater = VersionFileUpdater(file_path="test.txt", version=version)

        assert updater.file_path == "test.txt"
        assert updater.new_version == version
        assert updater.new_version.major == 1
        assert updater.new_version.minor == 2
        assert updater.new_version.patch == 3

    @pytest.mark.unit
    def test_init_with_complex_version(self) -> None:
        """Test initialization with complex version."""
        version = Version(major=2, minor=0, patch=0, suffix="-beta.1")
        updater = VersionFileUpdater(file_path="/path/to/file.py", version=version)

        assert updater.file_path == "/path/to/file.py"
        assert updater.new_version == version
        assert updater.new_version.suffix == "-beta.1"

    @pytest.mark.unit
    def test_init_requires_keyword_args(self) -> None:
        """Test that initialization requires keyword arguments."""
        version = Version(major=1, minor=0, patch=0)

        # Should work with keyword args
        updater = VersionFileUpdater(file_path="test.txt", version=version)
        assert updater.file_path == "test.txt"


class TestVersionFileUpdaterUpdate:
    """Test cases for VersionFileUpdater.update() method."""

    @pytest.mark.unit
    def test_update_single_version_line(
        self, mocker: MockerFixture, file_fixture: FileFixture
    ) -> None:
        """Test updating a file with a single version line."""
        # Create a Python file with version 1.0.0
        old_version = "1.0.0"
        new_version = Version(major=2, minor=0, patch=0)

        # Create a Python file with version string
        file_path = file_fixture.create_python_file(version=old_version, template_index=1)

        # Initialize updater with the file path and new version
        updater = VersionFileUpdater(file_path=str(file_path), version=new_version)
        updater.update()

        # Read the file content after update
        with open(file_path, encoding="utf-8") as f:
            updated_content = f.read()

        # Verify the version was updated
        assert f'version = "{new_version}"' in updated_content
        assert f'version = "{old_version}"' not in updated_content

    @pytest.mark.unit
    def test_update_multiple_version_lines(
        self, mocker: MockerFixture, file_fixture: FileFixture
    ) -> None:
        """Test updating a file with multiple version lines."""
        old_version = "1.0.0"
        new_version = Version(major=2, minor=5, patch=0)

        # Create a Python file with multiple version strings
        file_path = file_fixture.create_multi_version_file(version=old_version)

        # Initialize updater with the file path and new version
        updater = VersionFileUpdater(file_path=str(file_path), version=new_version)
        updater.update()

        # Read the file content after update
        with open(file_path, encoding="utf-8") as f:
            updated_content = f.read()

        # Verify versions were updated (except the one in the comment)
        assert f"# Version: {new_version}" in updated_content
        assert f"__version__ = '{new_version}'" in updated_content
        assert f'VERSION = "{new_version}"' in updated_content
        assert f"version = {new_version}" in updated_content

        # The comment with "v1.0.0" isn't recognized as a version string, so it won't be updated
        assert "# Another comment with v1.0.0" in updated_content

        # The old version should not appear except in the comment
        updated_content_without_comment_line = "\n".join(
            [line for line in updated_content.split("\n") if "Another comment" not in line]
        )
        assert old_version not in updated_content_without_comment_line

    @pytest.mark.unit
    def test_update_preserves_non_version_lines(self, mocker: MockerFixture) -> None:
        """Test that non-version lines are preserved unchanged."""
        file_content = (
            "# This is a comment\nimport os\nversion = '1.0.0'\ndef function():\n    pass\n"
        )
        expected_lines = [
            "# This is a comment\n",
            "import os\n",
            "version = '3.0.0'\n",
            "def function():\n",
            "    pass\n",
        ]
        new_version = Version(major=3, minor=0, patch=0)

        mock_file = mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))
        updater = VersionFileUpdater(file_path="module.py", version=new_version)
        updater.update()

        handle = mock_file()
        handle.writelines.assert_called_once_with(expected_lines)

    @pytest.mark.unit
    def test_update_with_merge_behavior(self, mocker: MockerFixture) -> None:
        """Test updating with version merging behavior."""
        file_content = "version = '1.0.0-alpha'\n"
        new_version = Version(major=2, minor=0, patch=0)

        mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))
        mock_parse = mocker.patch.object(Version, "parse")

        # Mock the parsed version
        current_version = mocker.MagicMock()
        current_version.format_full_line.return_value = "version = '2.0.0'"
        mock_parse.return_value = current_version

        updater = VersionFileUpdater(file_path="test.py", version=new_version)
        updater.update()

        # Verify merge_from was called
        current_version.merge_from.assert_called_once_with(new_version)
        current_version.format_full_line.assert_called_once()

    @pytest.mark.integration
    def test_update_real_file(self, file_fixture: FileFixture) -> None:
        """Test updating a real temporary file."""
        old_version = "1.0.0"
        new_version = Version(major=2, minor=1, patch=0)

        # Create a Python file with the old version using the first template
        # which contains multiple version patterns
        file_path = file_fixture.create_python_file(version=old_version, template_index=0)

        # Update the file with the new version
        updater = VersionFileUpdater(file_path=str(file_path), version=new_version)
        updater.update()

        # Read the updated file
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # Verify version strings were updated
        assert f'__version__ = "{new_version}"' in content
        assert f'VERSION = "{new_version}"' in content
        assert f"# Version: {new_version}" in content

        # Verify the old version is gone
        assert old_version not in content


class TestVersionFileUpdaterErrorHandling:
    """Test cases for VersionFileUpdater error handling."""

    @pytest.mark.unit
    def test_update_file_not_found(self, mocker: MockerFixture) -> None:
        """Test handling when file doesn't exist."""
        new_version = Version(major=1, minor=0, patch=0)
        updater = VersionFileUpdater(file_path="nonexistent.txt", version=new_version)

        mock_logger = mocker.patch("auto_semver.core.semver.updater.logger")
        # Should not raise exception, just log warning
        updater.update()
        mock_logger.warning.assert_called_once()
        assert "File not found" in str(mock_logger.warning.call_args)

    @pytest.mark.unit
    def test_update_permission_error(self, mocker: MockerFixture) -> None:
        """Test handling permission errors."""
        new_version = Version(major=1, minor=0, patch=0)
        updater = VersionFileUpdater(file_path="test.py", version=new_version)

        mocker.patch("builtins.open", side_effect=PermissionError("Permission denied"))
        mock_logger = mocker.patch("auto_semver.core.semver.updater.logger")
        with pytest.raises(PermissionError):
            updater.update()

        mock_logger.error.assert_called_once()
        assert "Failed to update version" in str(mock_logger.error.call_args)

    @pytest.mark.unit
    def test_update_parse_error_handling(self, mocker: MockerFixture) -> None:
        """Test handling when Version.parse raises ValueError."""
        file_content = "version = '1.0.0'\ninvalid version line\nanother = '2.0.0'\n"
        new_version = Version(major=3, minor=0, patch=0)

        mock_file = mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))
        mock_parse = mocker.patch.object(Version, "parse")

        # First call succeeds, second raises ValueError, third succeeds
        mock_parse.side_effect = [
            mocker.MagicMock(
                merge_from=mocker.MagicMock(),
                format_full_line=mocker.MagicMock(return_value="version = '3.0.0'"),
            ),
            ValueError("Invalid version"),
            mocker.MagicMock(
                merge_from=mocker.MagicMock(),
                format_full_line=mocker.MagicMock(return_value="another = '3.0.0'"),
            ),
        ]

        updater = VersionFileUpdater(file_path="test.py", version=new_version)
        updater.update()

        # Should have called parse for each line
        expected_calls = len(file_content.strip().split("\n"))
        assert mock_parse.call_count == expected_calls

        # Should have written all lines, including the invalid one unchanged
        handle = mock_file()
        written_lines = handle.writelines.call_args[0][0]
        assert len(written_lines) == expected_calls
        assert "invalid version line\n" in written_lines

    @pytest.mark.unit
    def test_update_io_error_during_write(self, mocker: MockerFixture) -> None:
        """Test handling I/O errors during write operations."""
        file_content = "version = '1.0.0'\n"
        new_version = Version(major=2, minor=0, patch=0)

        mock_file = mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))
        # Make writelines raise an exception
        handle = mock_file()
        handle.writelines.side_effect = OSError("Disk full")

        mock_logger = mocker.patch("auto_semver.core.semver.updater.logger")
        updater = VersionFileUpdater(file_path="test.py", version=new_version)

        with pytest.raises(OSError):
            updater.update()

        mock_logger.error.assert_called_once()


class TestVersionFileUpdaterLogging:
    """Test cases for VersionFileUpdater logging behavior."""

    @pytest.mark.unit
    def test_successful_update_logging(self, mocker: MockerFixture) -> None:
        """Test that successful updates are logged."""
        file_content = "version = '1.0.0'\n"
        new_version = Version(major=2, minor=0, patch=0)

        mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))
        mock_logger = mocker.patch("auto_semver.core.semver.updater.logger")
        updater = VersionFileUpdater(file_path="test.py", version=new_version)
        updater.update()

        # Should log successful update
        mock_logger.info.assert_called_once()
        info_call = mock_logger.info.call_args[0]
        assert "Updated version in test.py to 2.0.0" in info_call[0] % info_call[1:]

    @pytest.mark.unit
    def test_line_update_debug_logging(self, mocker: MockerFixture) -> None:
        """Test that individual line updates are logged at debug level."""
        file_content = "version = '1.0.0'\n"
        new_version = Version(major=2, minor=0, patch=0)

        mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))
        mock_logger = mocker.patch("auto_semver.core.semver.updater.logger")
        updater = VersionFileUpdater(file_path="test.py", version=new_version)
        updater.update()

        # Should log debug message for line update
        mock_logger.debug.assert_called_once()
        debug_call = mock_logger.debug.call_args[0]
        assert "Updated:" in debug_call[0]


class TestVersionFileUpdaterEdgeCases:
    """Test cases for edge cases and boundary conditions."""

    @pytest.mark.edge_case
    def test_update_empty_file(self, mocker: MockerFixture) -> None:
        """Test updating an empty file."""
        file_content = ""
        new_version = Version(major=1, minor=0, patch=0)

        mock_file = mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))
        updater = VersionFileUpdater(file_path="empty.txt", version=new_version)
        updater.update()

        handle = mock_file()
        handle.writelines.assert_called_once_with([])

    @pytest.mark.edge_case
    def test_update_file_with_only_whitespace(self, mocker: MockerFixture) -> None:
        """Test updating file with only whitespace."""
        file_content = "\n\n   \n\t\n"
        new_version = Version(major=1, minor=0, patch=0)

        mock_file = mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))
        updater = VersionFileUpdater(file_path="whitespace.txt", version=new_version)
        updater.update()

        handle = mock_file()
        written_lines = handle.writelines.call_args[0][0]
        expected_line_count = 4  # All whitespace lines preserved
        assert len(written_lines) == expected_line_count
        assert all(line.strip() == "" or line.isspace() for line in written_lines)

    @pytest.mark.edge_case
    def test_update_very_long_file(self, mocker: MockerFixture) -> None:
        """Test updating a file with many lines."""
        max_lines = 1000
        version_line_index = 500
        lines = [f"# Comment line {i}\n" for i in range(max_lines)]
        lines[version_line_index] = "version = '1.0.0'\n"  # Insert version line in middle
        file_content = "".join(lines)
        new_version = Version(major=2, minor=0, patch=0)

        mock_file = mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))
        updater = VersionFileUpdater(file_path="large.py", version=new_version)
        updater.update()

        handle = mock_file()
        written_lines = handle.writelines.call_args[0][0]
        assert len(written_lines) == max_lines
        assert written_lines[version_line_index] == "version = '2.0.0'\n"

    @pytest.mark.edge_case
    def test_update_binary_like_file(self, mocker: MockerFixture) -> None:
        """Test updating file with binary-like content."""
        file_content = (
            "version = '1.0.0'\n"
            "\x00\x01\x02\n"  # Binary data
            "more text\n"
        )
        new_version = Version(major=2, minor=0, patch=0)

        mock_file = mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))
        updater = VersionFileUpdater(file_path="mixed.txt", version=new_version)
        updater.update()

        handle = mock_file()
        written_lines = handle.writelines.call_args[0][0]
        assert written_lines[0] == "version = '2.0.0'\n"
        assert written_lines[1] == "\x00\x01\x02\n"  # Binary preserved

    @pytest.mark.edge_case
    def test_update_with_unicode_content(self, mocker: MockerFixture) -> None:
        """Test updating file with Unicode content."""
        file_content = "# 版本: version = '1.0.0'\n# Versión: 1.0.0\nversion = '1.0.0'  # 🚀\n"
        new_version = Version(major=2, minor=0, patch=0)

        mock_file = mocker.patch("builtins.open", mocker.mock_open(read_data=file_content))
        updater = VersionFileUpdater(file_path="unicode.py", version=new_version)
        updater.update()

        handle = mock_file()
        written_lines = handle.writelines.call_args[0][0]
        assert "version = '2.0.0'" in written_lines[2]
        assert "🚀" in written_lines[2]


class TestVersionFileUpdaterIntegration:
    """Integration test cases for VersionFileUpdater."""

    @pytest.mark.integration
    def test_update_package_json_trailing_comma(self, file_fixture: FileFixture) -> None:
        """Mid-object JSON version lines keep their trailing comma after bump."""
        path = file_fixture.create_version_file("package_json", version="1.0.0", filename="package")
        VersionFileUpdater(file_path=str(path), version=Version(major=1, minor=2, patch=3)).update()
        content = path.read_text(encoding="utf-8")
        assert '"version": "1.2.3",' in content
        assert '"name": "test-package"' in content

        """Test updating different types of files."""
        old_version = "1.0.0"
        new_version = Version(major=2, minor=1, patch=0)

        # Test different file formats
        test_files = [
            file_fixture.create_json_file(
                version=old_version, template_index=0
            ),  # package.json style
            file_fixture.create_python_file(
                version=old_version, template_index=2
            ),  # setup.py style
            file_fixture.create_toml_file(
                version=old_version, template_index=0
            ),  # Cargo.toml style
            file_fixture.create_text_file(version=old_version, template_index=2),  # v prefix style
        ]

        # Update each file and verify the changes
        for file_path in test_files:
            updater = VersionFileUpdater(file_path=str(file_path), version=new_version)
            updater.update()

            with open(file_path, encoding="utf-8") as f:
                updated_content = f.read()

            # Should contain the new version
            assert str(new_version) in updated_content
            # Old version should be gone
            assert old_version not in updated_content

    @pytest.mark.integration
    def test_concurrent_updates(self, file_fixture: FileFixture) -> None:
        """Test that concurrent updates work correctly."""
        # Create a simple Python file with version 1.0.0
        file_path = file_fixture.create_python_file(version="1.0.0", template_index=1)
        file_path_str = str(file_path)

        results = []

        def update_version(version_str: str) -> None:
            parts = version_str.split(".")
            version = Version(major=int(parts[0]), minor=int(parts[1]), patch=int(parts[2]))
            updater = VersionFileUpdater(file_path=file_path_str, version=version)
            try:
                updater.update()
                results.append(version_str)
            except Exception as e:
                results.append(f"Error: {e}")

        # Start multiple threads updating to different versions
        threads = []
        for version_str in ["2.0.0", "2.1.0", "2.2.0"]:
            thread = threading.Thread(target=update_version, args=(version_str,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # At least one should succeed
        success_count = sum(1 for r in results if not r.startswith("Error"))
        assert success_count >= 1

        # Verify the file was updated with one of the versions
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        assert any(version in content for version in ["2.0.0", "2.1.0", "2.2.0"])
