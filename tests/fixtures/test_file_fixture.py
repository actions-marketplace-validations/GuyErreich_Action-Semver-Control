"""
Tests for the FileFixture class.

This module tests the functionality of the FileFixture class.
"""

import pytest

from auto_semver.core.semver.version import Version
from tests.fixtures.file_fixture import FileFixture


@pytest.mark.unit
def test_file_fixture_python_file(file_fixture: FileFixture) -> None:
    """Test creating a Python file with a version string."""
    file_path = file_fixture.create_python_file(version="2.1.0")
    assert file_path.exists()

    content = file_path.read_text()
    assert "2.1.0" in content
    assert file_path.suffix == ".py"


@pytest.mark.unit
def test_file_fixture_text_file(file_fixture: FileFixture) -> None:
    """Test creating a text file with a version string."""
    file_path = file_fixture.create_text_file(version="1.5.0")
    assert file_path.exists()

    content = file_path.read_text()
    assert "1.5.0" in content
    assert file_path.suffix == ".txt"


@pytest.mark.unit
def test_file_fixture_with_custom_filename(file_fixture: FileFixture) -> None:
    """Test creating a file with a custom filename."""
    file_path = file_fixture.create_version_file(
        file_format="json", version="3.0.0", filename="package"
    )
    assert file_path.exists()
    assert file_path.name == "package.json"

    content = file_path.read_text()
    assert "3.0.0" in content
    assert '"version"' in content


@pytest.mark.unit
def test_file_fixture_with_version_object(file_fixture: FileFixture) -> None:
    """Test creating a file with a Version object."""
    version = Version(major=4, minor=2, patch=1, suffix="-beta")
    file_path = file_fixture.create_yaml_file(version=version)

    assert file_path.exists()
    assert file_path.suffix == ".yml"

    content = file_path.read_text()
    assert "4.2.1-beta" in content


@pytest.mark.unit
def test_file_fixture_multi_version_file(file_fixture: FileFixture) -> None:
    """Test creating a file with multiple version strings."""
    file_path = file_fixture.create_multi_version_file(version="2.0.0")

    assert file_path.exists()
    assert file_path.name == "multi_version.py"

    content = file_path.read_text()
    assert content.count("2.0.0") >= 4  # Should appear multiple times
