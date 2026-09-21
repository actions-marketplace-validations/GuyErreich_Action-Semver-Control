"""Tests for CommitGroupsConfig parsing."""

import pytest

from auto_semver.config import CommitGroupConfig, CommitGroupsConfig


@pytest.mark.unit
def test_from_yaml_list_legacy_format() -> None:
    """Legacy list YAML becomes groups with default header_only settings."""
    groups = [CommitGroupConfig(title="Features", patterns=["^feat"], priority=1)]
    config = CommitGroupsConfig.from_yaml(groups)

    assert config.summary_mode == "header_only"
    assert len(config.groups) == 1


@pytest.mark.unit
def test_from_yaml_structured_format() -> None:
    """Structured dict YAML preserves settings and groups."""
    config = CommitGroupsConfig.from_yaml(
        {
            "summary_mode": "expand_body",
            "groups": [{"title": "Fixes", "patterns": ["^fix"], "priority": 1}],
        }
    )

    assert config.summary_mode == "expand_body"
    assert config.groups[0].title == "Fixes"


@pytest.mark.unit
def test_from_yaml_rejects_invalid_type() -> None:
    """Invalid commit_groups type raises TypeError."""
    with pytest.raises(TypeError):
        CommitGroupsConfig.from_yaml("invalid")
