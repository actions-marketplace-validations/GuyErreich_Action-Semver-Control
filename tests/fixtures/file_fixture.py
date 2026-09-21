"""
File fixtures for testing.

This module provides a fixture class for generating various test files for version testing.
"""

from pathlib import Path
from typing import Any

from pyfakefs.fake_filesystem import FakeFilesystem

from auto_semver.core.semver.version import Version


class FileFixture:
    """
    A fixture class for generating test files for version tests.

    This class provides methods to create different types of files with version strings
    for testing version detection, parsing, and updating functionality.
    """

    def __init__(self, tmp_path: Path, fs: FakeFilesystem) -> None:
        """
        Initialize the fixture.

        Args:
            tmp_path: Pytest fixture that provides a temporary directory
            fs: Fake filesystem for testing
        """
        self.tmp_path = tmp_path
        self.fs = fs
        self.file_formats: dict[str, Any] = {
            "python": {
                "extension": ".py",
                "templates": [
                    '# Version: {version}\n__version__ = "{version}"\nVERSION = "{version}"\n',
                    'version = "{version}"\n# Comment line\n',
                    'VERSION = "{version}"  # Used for semantic versioning\n',
                    '"""Package info"""\n__version__ = \'{version}\'\n',
                ],
            },
            "javascript": {
                "extension": ".js",
                "templates": [
                    '// @version {version}\nconst version = "{version}";\n',
                    "export const VERSION = '{version}';\n",
                    'module.exports = {{ version: "{version}" }};\n',
                ],
            },
            "text": {
                "extension": ".txt",
                "templates": ["{version}\n", "Version: {version}\n", "v{version}\n"],
            },
            "json": {
                "extension": ".json",
                "templates": [
                    '{{\n  "version": "{version}"\n}}\n',
                    '{{\n  "name": "test-package",\n  "version": "{version}"\n}}\n',
                ],
            },
            "yaml": {
                "extension": ".yml",
                "templates": ['version: "{version}"\n', "version: {version}\n"],
            },
            "toml": {
                "extension": ".toml",
                "templates": ['[package]\nversion = "{version}"\n', 'version = "{version}"\n'],
            },
            "markdown": {
                "extension": ".md",
                "templates": [
                    (
                        "# Project Name\n\n[![Version]"
                        "(https://img.shields.io/badge/version-{version}-blue.svg)]"
                        "()\n\n## Overview\n"
                    ),
                    "# Changelog\n\n## v{version}\n\n- Feature 1\n- Feature 2\n",
                    "<!-- Version: {version} -->\n# Documentation\n",
                ],
            },
            "css": {
                "extension": ".css",
                "templates": [
                    '/* Version: {version} */\n.version-info:before {{\n  content: "v{version}";\n}}\n',
                    "/*! MyComponent v{version} */\nbody {{\n  margin: 0;\n}}\n",
                ],
            },
            "html": {
                "extension": ".html",
                "templates": [
                    (
                        "<!DOCTYPE html>\n<html>\n<head>\n  "
                        '<meta name="version" content="{version}">\n  '
                        "<title>Test Page</title>\n</head>\n<body>\n  "
                        '<div class="version">v{version}</div>\n</body>\n</html>\n'
                    ),
                    (
                        '<script data-version="{version}">'
                        'console.log("Version: {version}");</script>\n'
                    ),
                ],
            },
            "xml": {
                "extension": ".xml",
                "templates": [
                    (
                        '<?xml version="1.0" encoding="UTF-8"?>\n<project>\n  '
                        "<version>{version}</version>\n</project>\n"
                    ),
                    (
                        "<dependency>\n  <groupId>com.example</groupId>\n  "
                        "<artifactId>library</artifactId>\n  "
                        "<version>{version}</version>\n</dependency>\n"
                    ),
                ],
            },
            "package_json": {
                "extension": ".json",
                "templates": [
                    (
                        '{{\n  "name": "test-package",\n  "version": "{version}",\n  '
                        '"description": "Test package",\n  "main": "index.js",\n  '
                        '"scripts": {{\n    "test": "echo \\"Error: no test specified\\" '
                        '&& exit 1"\\n  }},\\n  "keywords": [],\\n  "author": "",\\n  '
                        '"license": "MIT"\\n}}\\n'
                    )
                ],
            },
            "cargo_toml": {
                "extension": ".toml",
                "templates": [
                    (
                        '[package]\nname = "test_crate"\nversion = "{version}"'
                        '\nedition = "2021"\n\n[dependencies]\n'
                    )
                ],
            },
            "gemspec": {
                "extension": ".gemspec",
                "templates": [
                    (
                        'Gem::Specification.new do |s|\n  s.name        = "test_gem"\n  '
                        's.version     = "{version}"\n  s.summary     = "Test gem"\n  '
                        's.authors     = ["Test Author"]\n  s.files       = ["lib/test.rb"]\n  '
                        's.license     = "MIT"\nend\n'
                    )
                ],
            },
            "go_mod": {
                "extension": ".mod",
                "templates": ["module example.com/test\n\ngo 1.16\n\nversion v{version}\n"],
            },
            "header": {
                "extension": ".h",
                "templates": [
                    (
                        "#ifndef VERSION_H\n#define VERSION_H\n\n"
                        '#define VERSION_STR "{version}"\n#define VERSION_MAJOR {major}\n'
                        "#define VERSION_MINOR {minor}\n#define VERSION_PATCH {patch}\n\n"
                        "#endif // VERSION_H\n"
                    )
                ],
            },
            "properties": {
                "extension": ".properties",
                "templates": ["version={version}\napp.version={version}\n"],
            },
        }

    def create_version_file(
        self,
        file_format: str = "text",
        version: Version | str = "1.0.0",
        template_index: int = 0,
        filename: str = "",
    ) -> Path:
        """
        Create a file with a version string for testing.

        Args:
            file_format: The format of the file to create (python, javascript, text, etc.)
            version: The version string or Version object to include
            template_index: Which template to use for the file format
            filename: Custom filename to use (default: auto-generated)

        Returns:
            Path to the created file

        Raises:
            ValueError: If the file format is not supported
        """
        if file_format not in self.file_formats:
            raise ValueError(f"Unsupported file format: {file_format}")

        # Convert Version object to string if needed
        if isinstance(version, Version):
            version_str = f"{version.major}.{version.minor}.{version.patch}"
            if version.suffix:
                version_str += version.suffix
        else:
            version_str = str(version)

        # Get the template and extension
        templates = self.file_formats[file_format]["templates"]
        extension = self.file_formats[file_format]["extension"]

        if template_index >= len(templates):
            template_index = 0

        template = templates[template_index]

        # Generate content
        content = template.format(version=version_str)

        # Create file
        actual_filename = filename if filename else f"version{extension}"
        if actual_filename and not actual_filename.endswith(extension):
            actual_filename += extension

        # Determine the full path
        file_path = self.tmp_path / actual_filename
        self.fs.create_file(file_path, contents=content)

        return file_path

    def create_python_file(self, version: Version | str = "1.0.0", template_index: int = 0) -> Path:
        """Create a Python file with a version string."""
        return self.create_version_file("python", version, template_index)

    def create_javascript_file(
        self, version: Version | str = "1.0.0", template_index: int = 0
    ) -> Path:
        """Create a JavaScript file with a version string."""
        return self.create_version_file("javascript", version, template_index)

    def create_text_file(self, version: Version | str = "1.0.0", template_index: int = 0) -> Path:
        """Create a plain text file with a version string."""
        return self.create_version_file("text", version, template_index)

    def create_json_file(self, version: Version | str = "1.0.0", template_index: int = 0) -> Path:
        """Create a JSON file with a version string."""
        return self.create_version_file("json", version, template_index)

    def create_yaml_file(self, version: Version | str = "1.0.0", template_index: int = 0) -> Path:
        """Create a YAML file with a version string."""
        return self.create_version_file("yaml", version, template_index)

    def create_toml_file(self, version: Version | str = "1.0.0", template_index: int = 0) -> Path:
        """Create a TOML file with a version string."""
        return self.create_version_file("toml", version, template_index)

    def create_markdown_file(
        self, version: Version | str = "1.0.0", template_index: int = 0
    ) -> Path:
        """Create a Markdown file with a version string or badge."""
        return self.create_version_file("markdown", version, template_index)

    def create_css_file(self, version: Version | str = "1.0.0", template_index: int = 0) -> Path:
        """Create a CSS file with a version string."""
        return self.create_version_file("css", version, template_index)

    def create_html_file(self, version: Version | str = "1.0.0", template_index: int = 0) -> Path:
        """Create an HTML file with a version string."""
        return self.create_version_file("html", version, template_index)

    def create_xml_file(self, version: Version | str = "1.0.0", template_index: int = 0) -> Path:
        """Create an XML file with a version string."""
        return self.create_version_file("xml", version, template_index)

    def create_package_json_file(self, version: Version | str = "1.0.0") -> Path:
        """Create a package.json file with a version string."""
        return self.create_version_file("package_json", version)

    def create_cargo_toml_file(self, version: Version | str = "1.0.0") -> Path:
        """Create a Cargo.toml file with a version string."""
        return self.create_version_file("cargo_toml", version)

    def create_gemspec_file(self, version: Version | str = "1.0.0") -> Path:
        """Create a Ruby gemspec file with a version string."""
        return self.create_version_file("gemspec", version)

    def create_go_mod_file(self, version: Version | str = "1.0.0") -> Path:
        """Create a Go mod file with a version string."""
        return self.create_version_file("go_mod", version)

    def create_header_file(self, version: Version | str = "1.0.0") -> Path:
        """Create a C/C++ header file with version defines."""
        # Convert Version object to string and parse components if needed
        if isinstance(version, Version):
            version_str = str(version)
            major = version.major
            minor = version.minor
            patch = version.patch
        else:
            version_str = str(version)
            # Parse version string
            parts = version_str.split(".")
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2].split("-")[0]) if len(parts) > 2 else 0

        # Create template parameters dict
        params = {"version": version_str, "major": major, "minor": minor, "patch": patch}

        # Special case for header files to include major, minor, patch
        template = self.file_formats["header"]["templates"][0]
        extension = self.file_formats["header"]["extension"]

        # Generate content with all parameters
        content = template.format(**params)

        # Create file
        file_path = self.tmp_path / f"version{extension}"
        self.fs.create_file(file_path, contents=content)

        return file_path

    def create_properties_file(self, version: Version | str = "1.0.0") -> Path:
        """Create a Java properties file with a version string."""
        return self.create_version_file("properties", version)

    def create_multi_version_file(self, version: Version | str = "1.0.0") -> Path:
        """Create a file with multiple version strings in different formats."""
        if isinstance(version, Version):
            version_str = f"{version.major}.{version.minor}.{version.patch}"
            if version.suffix:
                version_str += version.suffix
        else:
            version_str = str(version)

        content = (
            f"# Version: {version_str}\n"
            f"__version__ = '{version_str}'\n"
            f'VERSION = "{version_str}"\n'
            f"version = {version_str}\n"
            f"# Another comment with v{version_str}\n"
        )

        file_path = self.tmp_path / "multi_version.py"
        self.fs.create_file(file_path, contents=content)

        return file_path
