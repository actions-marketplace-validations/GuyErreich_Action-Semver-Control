"""
Unit tests for the SemverLock class in auto_semver.core.semver.lock module.

This module contains comprehensive tests for all methods and functionality
of the SemverLock class, including file I/O operations, serialization,
and data validation.
"""

import os
import tempfile
from typing import Any

import pytest
import yaml
from pytest_mock import MockerFixture

from auto_semver.core.semver.lock import FILE_NAME, SemverLock
from auto_semver.core.semver.version import Version


class TestSemverLockInit:
    """Test cases for SemverLock initialization."""

    @pytest.mark.unit
    def test_basic_initialization(self) -> None:
        """Test basic SemverLock initialization with required parameters."""
        version = Version(major=1, minor=2, patch=3)
        lock = SemverLock(version=version, source_branch="feature/test", target_branch="main")

        assert lock.version == version
        assert lock.source_branch == "feature/test"
        assert lock.target_branch == "main"
        assert lock.target_base_sha is None
        assert lock.finalized is False
        assert lock.path == FILE_NAME

    @pytest.mark.unit
    def test_initialization_with_all_parameters(self) -> None:
        """Test SemverLock initialization with all parameters."""
        version = Version(major=2, minor=1, patch=0, suffix="-dev")
        lock = SemverLock(
            version=version,
            source_branch="feature/new-feature",
            target_branch="develop",
            target_base_sha="abcd1234",
            finalized=True,
            path="/custom/path/.semver.lock",
        )

        assert lock.version == version
        assert lock.source_branch == "feature/new-feature"
        assert lock.target_branch == "develop"
        assert lock.target_base_sha == "abcd1234"
        assert lock.finalized is True
        assert lock.path == "/custom/path/.semver.lock"

    @pytest.mark.unit
    def test_default_values(self) -> None:
        """Test that default values are properly set."""
        version = Version(major=1, minor=0, patch=0)
        lock = SemverLock(version=version, source_branch="test", target_branch="main")

        assert lock.target_base_sha is None
        assert lock.finalized is False
        assert lock.path == FILE_NAME


class TestSemverLockFromDict:
    """Test cases for SemverLock.from_dict() class method."""

    @pytest.mark.unit
    def test_from_dict_minimal_data(self) -> None:
        """Test creating SemverLock from minimal dictionary data."""
        data = {"version": "1.2.3", "source_branch": "feature/test", "target_branch": "main"}

        lock = SemverLock.from_dict(data)

        assert str(lock.version) == "1.2.3"
        assert lock.source_branch == "feature/test"
        assert lock.target_branch == "main"
        assert lock.target_base_sha is None
        assert lock.finalized is False

    @pytest.mark.unit
    def test_from_dict_complete_data(self) -> None:
        """Test creating SemverLock from complete dictionary data."""
        data = {
            "version": "2.1.0-dev",
            "source_branch": "feature/new-api",
            "target_branch": "develop",
            "target_base_sha": "abcd1234efgh5678",
            "finalized": True,
        }

        lock = SemverLock.from_dict(data)

        assert str(lock.version) == "2.1.0-dev"
        assert lock.source_branch == "feature/new-api"
        assert lock.target_branch == "develop"
        assert lock.target_base_sha == "abcd1234efgh5678"
        assert lock.finalized is True

    @pytest.mark.unit
    def test_from_dict_with_complex_version(self) -> None:
        """Test creating SemverLock with complex version string."""
        data = {"version": "v1.0.0-rc1", "source_branch": "release/1.0.0", "target_branch": "main"}

        lock = SemverLock.from_dict(data)

        assert lock.version.major == 1
        assert lock.version.minor == 0
        assert lock.version.patch == 0
        assert lock.version.prefix == "v"
        assert lock.version.suffix == "-rc1"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_from_dict_missing_optional_fields(self) -> None:
        """Test from_dict with missing optional fields."""
        data = {
            "version": "1.0.0",
            "source_branch": "feature",
            "target_branch": "main",
            # target_base_sha and finalized are missing
        }

        lock = SemverLock.from_dict(data)

        assert lock.target_base_sha is None
        assert lock.finalized is False

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_from_dict_explicit_none_values(self) -> None:
        """Test from_dict with explicit None values."""
        data = {
            "version": "1.0.0",
            "source_branch": "feature",
            "target_branch": "main",
            "target_base_sha": None,
            "finalized": False,
        }

        lock = SemverLock.from_dict(data)

        assert lock.target_base_sha is None
        assert lock.finalized is False


class TestSemverLockToDict:
    """Test cases for SemverLock.to_dict() method."""

    @pytest.mark.unit
    def test_to_dict_basic(self) -> None:
        """Test converting SemverLock to dictionary."""
        version = Version(major=1, minor=2, patch=3)
        lock = SemverLock(version=version, source_branch="feature/test", target_branch="main")

        result = lock.to_dict()

        expected = {
            "version": "1.2.3",
            "source_branch": "feature/test",
            "target_branch": "main",
            "target_base_sha": None,
            "finalized": False,
        }

        assert result == expected

    @pytest.mark.unit
    def test_to_dict_complete(self) -> None:
        """Test converting complete SemverLock to dictionary."""
        version = Version(major=2, minor=1, patch=0, suffix="-dev")
        lock = SemverLock(
            version=version,
            source_branch="feature/new-feature",
            target_branch="develop",
            target_base_sha="abcd1234efgh5678",
            finalized=True,
        )

        result = lock.to_dict()

        expected = {
            "version": "2.1.0-dev",
            "source_branch": "feature/new-feature",
            "target_branch": "develop",
            "target_base_sha": "abcd1234efgh5678",
            "finalized": True,
        }

        assert result == expected

    @pytest.mark.unit
    def test_to_dict_with_complex_version(self) -> None:
        """Test to_dict with complex version formatting."""
        version = Version(major=1, minor=0, patch=0, prefix="v", suffix="-rc1")
        lock = SemverLock(version=version, source_branch="release/1.0.0", target_branch="main")

        result = lock.to_dict()

        # The to_dict method uses str(version) which only includes core version + suffix
        assert result["version"] == "1.0.0-rc1"


class TestSemverLockSaveToFile:
    """Test cases for SemverLock.save_to_file() method."""

    @pytest.mark.unit
    def test_save_to_file_success(self, mocker: MockerFixture) -> None:
        """Test successful saving of lockfile to disk."""
        version = Version(major=1, minor=2, patch=3)
        lock = SemverLock(
            version=version,
            source_branch="feature/test",
            target_branch="main",
            path="test_lock.yml",
        )

        mock_file = mocker.mock_open()
        mocker.patch("builtins.open", mock_file)
        mock_yaml_dump = mocker.patch("yaml.dump")
        lock.save_to_file()

        mock_file.assert_called_once_with("test_lock.yml", "w", encoding="utf-8")
        mock_yaml_dump.assert_called_once()

        # Verify the data passed to yaml.dump
        call_args = mock_yaml_dump.call_args
        data = call_args[0][0]
        assert data["version"] == "1.2.3"
        assert data["source_branch"] == "feature/test"
        assert data["target_branch"] == "main"

    @pytest.mark.unit
    def test_save_to_file_yaml_options(self, mocker: MockerFixture) -> None:
        """Test that YAML dump is called with correct options."""
        version = Version(major=1, minor=2, patch=3)
        lock = SemverLock(version=version, source_branch="feature/test", target_branch="main")

        mocker.patch("builtins.open", mocker.mock_open())
        mock_yaml_dump = mocker.patch("yaml.dump")
        lock.save_to_file()

        # Check that yaml.dump was called with correct options
        call_args = mock_yaml_dump.call_args
        kwargs = call_args[1]
        assert kwargs["default_flow_style"] is False
        assert kwargs["sort_keys"] is False

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_save_to_file_exception_handling(self, mocker: MockerFixture) -> None:
        """Test exception handling during file save."""
        version = Version(major=1, minor=2, patch=3)
        lock = SemverLock(version=version, source_branch="feature/test", target_branch="main")

        # Test file I/O exception
        mocker.patch("builtins.open", side_effect=OSError("Permission denied"))
        with pytest.raises(OSError):
            lock.save_to_file()

        # Test YAML serialization exception
        mocker.patch("builtins.open", mocker.mock_open())
        mocker.patch("yaml.dump", side_effect=yaml.YAMLError("YAML error"))
        with pytest.raises(yaml.YAMLError):
            lock.save_to_file()

    @pytest.mark.integration
    def test_save_to_file_real_file(self) -> None:
        """Integration test: save to real temporary file."""
        version = Version(major=1, minor=2, patch=3, suffix="-test")

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yml") as tmp_file:
            tmp_path = tmp_file.name

        try:
            lock = SemverLock(
                version=version,
                source_branch="feature/integration-test",
                target_branch="main",
                target_base_sha="abc123",
                finalized=False,
                path=tmp_path,
            )

            lock.save_to_file()

            # Verify file was created and contains expected content
            assert os.path.exists(tmp_path)

            with open(tmp_path, encoding="utf-8") as f:
                saved_data = yaml.safe_load(f)

            expected_data = {
                "version": "1.2.3-test",
                "source_branch": "feature/integration-test",
                "target_branch": "main",
                "target_base_sha": "abc123",
                "finalized": False,
            }

            assert saved_data == expected_data

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class TestSemverLockLoadFromFile:
    """Test cases for SemverLock.load_from_file() class method."""

    @pytest.mark.unit
    def test_load_from_file_success(self, mocker: MockerFixture) -> None:
        """Test successful loading of lockfile from disk."""
        mock_data = {
            "version": "1.2.3",
            "source_branch": "feature/test",
            "target_branch": "main",
            "target_base_sha": "abcd1234",
            "finalized": False,
        }

        mock_file = mocker.mock_open(read_data="dummy")
        mocker.patch("builtins.open", mock_file)
        mocker.patch("yaml.safe_load", return_value=mock_data)
        lock = SemverLock.load_from_file()

        assert str(lock.version) == "1.2.3"
        assert lock.source_branch == "feature/test"
        assert lock.target_branch == "main"
        assert lock.target_base_sha == "abcd1234"
        assert lock.finalized is False
        mock_file.assert_called_once_with(FILE_NAME, encoding="utf-8")

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_load_from_file_not_found(self, mocker: MockerFixture) -> None:
        """Test loading when lockfile doesn't exist."""
        mocker.patch("builtins.open", side_effect=FileNotFoundError("File not found"))
        with pytest.raises(FileNotFoundError):
            SemverLock.load_from_file()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_load_from_file_yaml_error(self, mocker: MockerFixture) -> None:
        """Test loading with invalid YAML content."""
        mock_file = mocker.mock_open(read_data="invalid: yaml: content:")
        mocker.patch("builtins.open", mock_file)
        mocker.patch("yaml.safe_load", side_effect=yaml.YAMLError("Invalid YAML"))
        with pytest.raises(yaml.YAMLError):
            SemverLock.load_from_file()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_load_from_file_general_exception(self, mocker: MockerFixture) -> None:
        """Test loading with general exception during processing."""
        mock_file = mocker.mock_open(read_data="dummy")
        mocker.patch("builtins.open", mock_file)
        mocker.patch("yaml.safe_load", side_effect=Exception("General error"))
        with pytest.raises(Exception, match="General error"):
            SemverLock.load_from_file()

    @pytest.mark.integration
    def test_load_from_file_real_file(self, mocker: MockerFixture) -> None:
        """Integration test: load from real temporary file."""
        test_data = {
            "version": "2.1.0-dev",
            "source_branch": "feature/real-test",
            "target_branch": "develop",
            "target_base_sha": "def456",
            "finalized": True,
        }

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yml") as tmp_file:
            yaml.dump(test_data, tmp_file, default_flow_style=False)
            tmp_path = tmp_file.name

        try:
            mocker.patch("auto_semver.core.semver.lock.FILE_NAME", tmp_path)
            lock = SemverLock.load_from_file()

            assert str(lock.version) == "2.1.0-dev"
            assert lock.source_branch == "feature/real-test"
            assert lock.target_branch == "develop"
            assert lock.target_base_sha == "def456"
            assert lock.finalized is True

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class TestSemverLockRoundTrip:
    """Test cases for round-trip serialization/deserialization."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "test_data",
        [
            {
                "version": Version(major=1, minor=2, patch=3),
                "source_branch": "feature/test",
                "target_branch": "main",
            },
            {
                "version": Version(major=2, minor=0, patch=0, suffix="-dev"),
                "source_branch": "feature/complex",
                "target_branch": "develop",
                "target_base_sha": "abcd1234",
                "finalized": True,
            },
            {
                "version": Version(major=0, minor=1, patch=0, prefix="v", suffix="-rc1"),
                "source_branch": "release/0.1.0",
                "target_branch": "main",
                "target_base_sha": None,
                "finalized": False,
            },
        ],
    )
    def test_to_dict_from_dict_round_trip(self, test_data: dict[str, Any]) -> None:
        """Test that to_dict() and from_dict() are inverse operations."""
        # Create original lock
        original_lock = SemverLock(**test_data)

        # Convert to dict and back
        dict_data = original_lock.to_dict()
        restored_lock = SemverLock.from_dict(dict_data)

        # Compare all attributes
        assert str(original_lock.version) == str(restored_lock.version)
        assert original_lock.source_branch == restored_lock.source_branch
        assert original_lock.target_branch == restored_lock.target_branch
        assert original_lock.target_base_sha == restored_lock.target_base_sha
        assert original_lock.finalized == restored_lock.finalized

    @pytest.mark.integration
    def test_save_load_round_trip(self, mocker: MockerFixture) -> None:
        """Integration test: save to file and load back."""
        original_version = Version(major=3, minor=1, patch=4, suffix="-beta")
        original_lock = SemverLock(
            version=original_version,
            source_branch="feature/round-trip",
            target_branch="staging",
            target_base_sha="xyz789",
            finalized=True,
        )

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yml") as tmp_file:
            tmp_path = tmp_file.name

        try:
            # Save with custom path
            original_lock.path = tmp_path
            original_lock.save_to_file()

            # Load back using the same path
            mocker.patch("auto_semver.core.semver.lock.FILE_NAME", tmp_path)
            loaded_lock = SemverLock.load_from_file()

            # Compare all attributes
            assert str(original_lock.version) == str(loaded_lock.version)
            assert original_lock.source_branch == loaded_lock.source_branch
            assert original_lock.target_branch == loaded_lock.target_branch
            assert original_lock.target_base_sha == loaded_lock.target_base_sha
            assert original_lock.finalized == loaded_lock.finalized

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class TestSemverLockEdgeCases:
    """Test cases for edge cases and boundary conditions."""

    @pytest.mark.edge_case
    def test_empty_branch_names(self) -> None:
        """Test SemverLock with empty branch names."""
        version = Version(major=1, minor=0, patch=0)
        lock = SemverLock(version=version, source_branch="", target_branch="")

        assert lock.source_branch == ""
        assert lock.target_branch == ""

        # Should still serialize/deserialize correctly
        dict_data = lock.to_dict()
        restored_lock = SemverLock.from_dict(dict_data)
        assert restored_lock.source_branch == ""
        assert restored_lock.target_branch == ""

    @pytest.mark.edge_case
    def test_long_branch_names(self) -> None:
        """Test SemverLock with very long branch names."""
        long_name = "feature/" + "very-long-branch-name-" * 10
        version = Version(major=1, minor=0, patch=0)
        lock = SemverLock(version=version, source_branch=long_name, target_branch=long_name)

        assert lock.source_branch == long_name
        assert lock.target_branch == long_name

    @pytest.mark.edge_case
    def test_special_characters_in_branches(self) -> None:
        """Test SemverLock with special characters in branch names."""
        special_branch = "feature/fix-issue-#123_with-symbols"
        version = Version(major=1, minor=0, patch=0)
        lock = SemverLock(version=version, source_branch=special_branch, target_branch="main")

        dict_data = lock.to_dict()
        restored_lock = SemverLock.from_dict(dict_data)
        assert restored_lock.source_branch == special_branch

    @pytest.mark.edge_case
    def test_very_long_sha(self) -> None:
        """Test SemverLock with very long SHA string."""
        long_sha = "a" * 64  # 64-character SHA
        version = Version(major=1, minor=0, patch=0)
        lock = SemverLock(
            version=version,
            source_branch="feature/test",
            target_branch="main",
            target_base_sha=long_sha,
        )

        assert lock.target_base_sha == long_sha

        dict_data = lock.to_dict()
        restored_lock = SemverLock.from_dict(dict_data)
        assert restored_lock.target_base_sha == long_sha

    @pytest.mark.edge_case
    def test_custom_file_path(self) -> None:
        """Test SemverLock with custom file path."""
        custom_path = "/custom/directory/.my-semver.lock"
        version = Version(major=1, minor=0, patch=0)
        lock = SemverLock(
            version=version, source_branch="feature/test", target_branch="main", path=custom_path
        )

        assert lock.path == custom_path

        # Path should be preserved but not serialized
        dict_data = lock.to_dict()
        assert "path" not in dict_data
