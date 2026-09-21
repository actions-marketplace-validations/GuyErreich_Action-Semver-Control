"""
Unit tests for Config class from auto_semver.config.loader.

This module tests the Config class interface without importing internal models,
mimicking how users would interact with the system.
"""

from pathlib import Path

import pytest

from auto_semver.config import ChangelogTemplateVars, Config, PullRequestTemplateVars
from auto_semver.core.changelog.manager import ChangelogManager
from auto_semver.core.commits.grouper import CommitGrouper
from tests.fixtures.config_fixture import ConfigFixture


class TestConfig:
    """Tests for the Config class interface."""

    @pytest.mark.unit
    def test_config_loading_basic(self, config_fixture: ConfigFixture) -> None:
        """Test basic config loading through Config class."""
        config_fixture.create(start_version="1.0.0", suffixes={"main": "", "dev": "-dev"})

        config = Config(config_fixture.config_path)

        # Test that config loaded correctly
        assert config.data.start_version.major == 1
        assert config.data.start_version.minor == 0
        assert config.data.start_version.patch == 0
        assert config.data.suffixes == {"main": "", "dev": "-dev"}

    @pytest.mark.unit
    def test_config_loading_with_custom_path(self, tmp_path: Path) -> None:
        """Test Config initialization with a custom path."""
        # Create a custom config file
        config_file = tmp_path / "custom_config.yml"
        config_file.write_text("""
start_version: "2.0.0"
suffixes:
  main: ""
  dev: "-dev"
version_files:
  - "version.txt"
commit_groups: []
promotions: []
pull_request:
  title: "Release {{version}}"
  body: "Auto-created PR"
  labels: ["release"]
changelog:
  file: "CHANGELOG.md"
  truncate: false
  template: "## {{version}}"
        """)

        config = Config(path=config_file)

        # Verify the config was loaded correctly from the custom path
        assert config.data.start_version.major == 2

    @pytest.mark.unit
    def test_config_missing_file_error(self) -> None:
        """Test initialization handles missing config file gracefully."""
        non_existent_path = "/path/to/non/existent/config.yml"

        with pytest.raises(FileNotFoundError, match=r"Configuration file .* not found"):
            Config(path=Path(non_existent_path))

    @pytest.mark.unit
    def test_config_invalid_yaml_error(self, tmp_path: Path) -> None:
        """Test initialization handles invalid YAML format."""
        invalid_yaml_file = tmp_path / "invalid_config.yml"
        invalid_yaml_file.write_text("invalid_key: true\nno_required_fields: true")

        with pytest.raises(ValueError):
            Config(path=invalid_yaml_file)

    @pytest.mark.unit
    def test_config_incomplete_data_error(self, tmp_path: Path) -> None:
        """Test initialization handles incomplete config data."""
        incomplete_yaml_file = tmp_path / "incomplete_config.yml"
        incomplete_yaml_file.write_text("""
        # Missing required fields like suffixes and promotions
        start_version: "0.1.0"
        """)

        with pytest.raises(ValueError, match="validation error"):
            Config(path=incomplete_yaml_file)

    @pytest.mark.unit
    def test_config_pull_request_interface(self, config_fixture: ConfigFixture) -> None:
        """Test PR config interface through Config class."""
        config_fixture.create(
            pull_request={
                "title": "Release {{version}}",
                "body": "Auto-created PR by auto-semver",
                "labels": ["release", "automated"],
            }
        )

        config = Config(config_fixture.config_path)
        pr_config = config.data.pull_request

        # Test the interface without checking types
        assert pr_config.title == "Release {{version}}"
        assert pr_config.body == "Auto-created PR by auto-semver"
        assert pr_config.labels == ["release", "automated"]

        # Test render methods work
        vars = PullRequestTemplateVars(version="1.2.3", date="2025-09-25", messages=[])
        rendered_title = pr_config.render_title(vars)
        assert rendered_title == "Release 1.2.3"

    @pytest.mark.unit
    def test_config_changelog_interface(self, config_fixture: ConfigFixture) -> None:
        """Test changelog config interface through Config class."""
        config_fixture.create(
            changelog={
                "file": "CHANGELOG.md",
                "truncate": False,
                "template": "## [{{version}}] - {{date}}\n",
            }
        )

        config = Config(config_fixture.config_path)
        changelog_config = config.data.changelog

        # Test the interface
        assert str(changelog_config.file) == "CHANGELOG.md"
        assert changelog_config.truncate is False
        assert changelog_config.template == "## [{{version}}] - {{date}}\n"

    @pytest.mark.unit
    def test_changelog_legacy_grouped_messages_alias(self, config_fixture: ConfigFixture) -> None:
        """Ensure templates using legacy 'grouped_messages' still render with commit_groups."""
        config_fixture.create(
            commit_groups=[{"title": "Features", "patterns": ["^feat:"], "priority": 1}],
            changelog={
                "file": "CHANGELOG.md",
                "truncate": True,
                # Intentionally use legacy grouped_messages variable
                "template": (
                    "## [{{version}}] - {{date}}\n\n"
                    "{% for group in grouped_messages -%}\n"
                    "### {{ group.title }}\n\n"
                    "{% for commit in group.commits -%}\n"
                    "- {{ commit.title if commit.title else commit.message if commit.message else commit }}\n"
                    "{% endfor -%}\n"
                    "{% endfor -%}\n"
                ),
            },
        )
        config = Config(config_fixture.config_path)
        messages = ["feat: add feature"]
        grouped = CommitGrouper.group_messages(messages, config.data.commit_groups)
        vars = ChangelogTemplateVars(
            version="1.0.0",
            date="2025-10-03",
            messages=messages,
            commit_groups=grouped,
        )
        # Use manager for rendering, not config model
        manager = ChangelogManager.from_config(config)
        rendered = manager.render_template(vars.__dict__)
        assert "Features" in rendered
        assert "add feature" in rendered

    @pytest.mark.unit
    def test_config_promotions_interface(self, config_fixture: ConfigFixture) -> None:
        """Test promotions interface through Config class."""
        config_fixture.create(
            suffixes={"dev": "-dev", "staging": "-rc", "main": ""},
            promotions=[
                {"from_branch": "dev", "to_branch": "staging"},
                {"from_branch": "staging", "to_branch": "main"},
            ],
        )

        config = Config(config_fixture.config_path)
        promotions = config.data.promotions

        # Test the interface
        assert len(promotions) == 2
        assert promotions[0].from_branch == "dev"
        assert promotions[0].to_branch == "staging"
        assert promotions[1].from_branch == "staging"
        assert promotions[1].to_branch == "main"
