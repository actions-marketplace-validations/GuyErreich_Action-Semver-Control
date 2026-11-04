"""Tests for CommitGroupsConfig parsing."""

import logging

import pytest

from auto_semver.config import CommitGroupConfig, CommitGroupsConfig


@pytest.mark.unit
def test_from_yaml_list_legacy_format(caplog: pytest.LogCaptureFixture) -> None:
    """Legacy list YAML becomes groups and warns once."""
    groups = [CommitGroupConfig(title="Features", patterns=["^feat"], priority=1)]
    with caplog.at_level(logging.WARNING, logger="auto_semver.compat._notice"):
        config = CommitGroupsConfig.from_yaml(groups)
        CommitGroupsConfig.from_yaml(groups)

    assert config.summary_mode == "header_only"
    assert len(config.groups) == 1
    warnings = [record for record in caplog.records if "YAML list is deprecated" in record.message]
    assert len(warnings) == 1


@pytest.mark.unit
def test_from_yaml_structured_format(caplog: pytest.LogCaptureFixture) -> None:
    """Structured dict YAML preserves settings and groups without a warning."""
    with caplog.at_level(logging.WARNING, logger="auto_semver.compat._notice"):
        config = CommitGroupsConfig.from_yaml(
            {
                "summary_mode": "expand_body",
                "groups": [{"title": "Fixes", "patterns": ["^fix"], "priority": 1}],
            }
        )

    assert config.summary_mode == "expand_body"
    assert config.groups[0].title == "Fixes"
    assert caplog.records == []


@pytest.mark.unit
def test_from_yaml_rejects_invalid_type() -> None:
    """Invalid commit_groups type raises TypeError."""
    with pytest.raises(TypeError):
        CommitGroupsConfig.from_yaml("invalid")
