"""
Unit tests for config data loading through the Config class.

This module contains tests for configuration loading, validation, and usage
through the Config class interface, mimicking how users interact with the system.
"""

import pytest
from pydantic import ValidationError

from auto_semver.config import Config, PullRequestTemplateVars
from auto_semver.config.constants import PR_HIDDEN_MARKER
from tests.fixtures.config_fixture import ConfigFixture


class TestPullRequestConfig:
    """Test cases for PullRequestConfig functionality through Config class."""

    @pytest.mark.unit
    def test_pr_config_basic_functionality(self, config_fixture: ConfigFixture) -> None:
        """Test basic PR config loading and functionality."""
        config_fixture.create(
            pull_request={
                "title": "Release {{version}}",
                "body": "- Version: {{version}}\n- Date: {{date}}",
                "labels": ["semver-bump", "automated"],
            }
        )

        config = Config(path=config_fixture.config_path)
        pr_config = config.data.pull_request

        assert pr_config.title == "Release {{version}}"
        assert pr_config.body == "- Version: {{version}}\n- Date: {{date}}"
        assert pr_config.labels == ["semver-bump", "automated"]

    @pytest.mark.unit
    def test_pr_render_title(self, config_fixture: ConfigFixture) -> None:
        """Test rendering the PR title with a version."""
        config_fixture.create(
            pull_request={
                "title": "Release {{version}}",
                "body": "",
                "labels": ["test-label"],
            }
        )

        config = Config(path=config_fixture.config_path)
        pr_config = config.data.pull_request

        vars = PullRequestTemplateVars(version="1.2.3", date="2025-01-01", messages=[])
        rendered = pr_config.render_title(vars)
        assert rendered == "Release 1.2.3"

    @pytest.mark.unit
    def test_pr_render_body(self, config_fixture: ConfigFixture) -> None:
        """Test rendering the PR body with version, date, and messages."""
        config_fixture.create(
            pull_request={
                "title": "",
                "body": (
                    "- Version: {{version}}\n- Date: {{date}}\n"
                    "{% for msg in messages %}- {{ msg }}\n{% endfor %}"
                ),
                "labels": ["test-label"],
            }
        )

        config = Config(path=config_fixture.config_path)
        pr_config = config.data.pull_request

        vars = PullRequestTemplateVars(
            version="1.2.3",
            date="01-01-2025",
            messages=["Fix bug", "Add feature"],
        )
        rendered = pr_config.render_body(vars)

        # Account for the hidden marker comment added by render_body
        expected = (
            f"{PR_HIDDEN_MARKER}\n- Version: 1.2.3\n- Date: 01-01-2025\n- Fix bug\n- Add feature\n"
        )
        assert rendered == expected

    @pytest.mark.unit
    def test_invalid_pr_template_syntax_in_title(self, config_fixture: ConfigFixture) -> None:
        """Test validation catches invalid Jinja2 syntax in title."""
        with pytest.raises(ValidationError, match="Invalid Jinja2 template"):
            config_fixture.create(
                pull_request={
                    "title": "Release {{ version",  # Missing closing brace
                    "body": "",
                    "labels": ["test-label"],
                }
            )
            Config(path=config_fixture.config_path)  # Should fail during validation

    @pytest.mark.unit
    def test_invalid_pr_template_syntax_in_body(self, config_fixture: ConfigFixture) -> None:
        """Test validation catches invalid Jinja2 syntax in body."""
        with pytest.raises(ValidationError, match="Invalid Jinja2 template"):
            config_fixture.create(
                pull_request={
                    "title": "",
                    "body": "{% for msg in messages %}- {{ msg }}",  # Missing endfor
                    "labels": ["test-label"],
                }
            )
            Config(path=config_fixture.config_path)  # Should fail during validation


class TestChangelogConfig:
    """Test cases for ChangelogConfig functionality through Config class."""

    @pytest.mark.unit
    def test_changelog_basic_functionality(self, config_fixture: ConfigFixture) -> None:
        """Test basic changelog config loading and functionality."""
        config_fixture.create(
            changelog={
                "file": "CHANGELOG.md",
                "truncate": False,
                "template": "## [{{version}}] - {{date}}\n",
                "header": "# Changelog",
                "footer": "## License",
            }
        )

        config = Config(path=config_fixture.config_path)
        changelog_config = config.data.changelog

        assert str(changelog_config.file) == "CHANGELOG.md"
        assert changelog_config.truncate is False
        assert changelog_config.template == "## [{{version}}] - {{date}}\n"
        assert changelog_config.header == "# Changelog"
        assert changelog_config.footer == "## License"

    @pytest.mark.unit
    def test_changelog_optional_fields(self, config_fixture: ConfigFixture) -> None:
        """Test changelog config with default values for optional fields."""
        config_fixture.create(
            changelog={
                "file": "CHANGELOG.md",
                "truncate": True,
                "template": "## [{{version}}] - {{date}}\n",
                "header": None,
                "footer": None,
            }
        )

        config = Config(path=config_fixture.config_path)
        changelog_config = config.data.changelog

        assert changelog_config.header is None
        assert changelog_config.footer is None

    @pytest.mark.unit
    def test_invalid_changelog_template_syntax(self, config_fixture: ConfigFixture) -> None:
        """Test validation catches invalid Jinja2 syntax in changelog template."""
        with pytest.raises(ValidationError, match="Invalid Jinja2 template"):
            config_fixture.create(
                changelog={
                    "file": "CHANGELOG.md",
                    "truncate": False,
                    "template": "## [{{version] - {{date}}\n",  # Missing closing brace
                }
            )
            Config(path=config_fixture.config_path)  # Should fail during validation


class TestPromotionRules:
    """Test cases for PromotionRule functionality through Config class."""

    @pytest.mark.unit
    def test_promotion_rule_basic_functionality(self, config_fixture: ConfigFixture) -> None:
        """Test basic promotion rule loading and functionality."""
        config_fixture.create(promotions=[{"from_branch": "dev", "to_branch": "main"}])

        config = Config(path=config_fixture.config_path)
        rules = config.data.promotions

        assert len(rules) == 1
        rule = rules[0]
        assert rule.from_branch == "dev"
        assert rule.to_branch == "main"


class TestConfigData:
    """Test cases for overall ConfigData functionality through Config class."""

    @pytest.mark.unit
    def test_config_basic_initialization(self, config_fixture: ConfigFixture) -> None:
        """Test basic config loading with all components."""
        config_fixture.create(
            start_version="0.1.0",
            suffixes={"dev": "-dev", "staging": "-rc", "main": ""},
            version_files=["version.txt", "pyproject.toml"],
            promotions=[
                {"from_branch": "dev", "to_branch": "staging"},
                {"from_branch": "staging", "to_branch": "main"},
            ],
            pull_request={
                "title": "Release {{version}}",
                "body": "Version: {{version}}",
                "labels": ["semver-bump"],
            },
            changelog={
                "file": "CHANGELOG.md",
                "truncate": False,
                "template": "## [{{version}}] - {{date}}\n",
            },
        )

        config = Config(path=config_fixture.config_path)
        data = config.data

        assert data.start_version.major == 0
        assert data.start_version.minor == 1
        assert data.start_version.patch == 0
        assert data.suffixes == {"dev": "-dev", "staging": "-rc", "main": ""}
        assert data.version_files == ["version.txt", "pyproject.toml"]
        assert len(data.promotions) == 2

    @pytest.mark.unit
    def test_config_with_promotions(self, config_fixture: ConfigFixture) -> None:
        """Test config loading with promotion rules."""
        config_fixture.create(
            start_version="0.1.0",
            suffixes={"dev": "-dev", "staging": "-rc", "main": ""},
            version_files=["version.txt"],
            promotions=[
                {"from_branch": "dev", "to_branch": "staging"},
                {"from_branch": "staging", "to_branch": "main"},
            ],
        )

        config = Config(path=config_fixture.config_path)
        data = config.data

        assert len(data.promotions) == 2
        assert data.promotions[0].from_branch == "dev"
        assert data.promotions[0].to_branch == "staging"
        assert data.promotions[1].from_branch == "staging"
        assert data.promotions[1].to_branch == "main"

    @pytest.mark.unit
    def test_missing_suffix_for_branch(self, config_fixture: ConfigFixture) -> None:
        """Test validation catches branch without defined suffix."""
        with pytest.raises(ValueError, match="missing suffix definitions"):
            config_fixture.create(
                start_version="0.1.0",
                suffixes={"dev": "-dev", "staging": "-rc"},  # Missing "main"
                version_files=["version.txt"],
                promotions=[
                    {"from_branch": "dev", "to_branch": "staging"},
                    {"from_branch": "staging", "to_branch": "main"},  # "main" not in suffixes
                ],
            )
            Config(path=config_fixture.config_path)  # Should fail during validation

    @pytest.mark.unit
    def test_circular_promotion_loop_prevention(self, config_fixture: ConfigFixture) -> None:
        """Test validation prevents circular promotion loops."""
        with pytest.raises(ValueError, match="reverse rule found"):
            config_fixture.create(
                start_version="0.1.0",
                suffixes={"dev": "-dev", "staging": "-rc"},
                version_files=["version.txt"],
                promotions=[
                    {"from_branch": "dev", "to_branch": "staging"},
                    {"from_branch": "staging", "to_branch": "dev"},  # Creates a loop!
                ],
            )
            Config(path=config_fixture.config_path)  # Should fail during validation
