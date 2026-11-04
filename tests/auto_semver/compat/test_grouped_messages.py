"""Tests for the grouped_messages template alias."""

import logging
from pathlib import Path

import pytest

from auto_semver.compat.grouped_messages import apply_grouped_messages_alias
from auto_semver.config import (
    Commit,
    CommitGroup,
    CommitGroupConfig,
    PullRequestConfig,
    PullRequestTemplateVars,
)
from auto_semver.core.changelog.manager import ChangelogManager

_NOTICE = "auto_semver.compat._notice"


def _groups() -> list[CommitGroup]:
    return [CommitGroup(title="Features", commits=[Commit(title="add")], priority=1)]


@pytest.mark.unit
def test_old_template_name_is_copied_and_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    """A template that names grouped_messages gets the alias and one warning."""
    template = "{% for group in grouped_messages %}{{ group.title }}{% endfor %}"
    variables: dict[str, object] = {"commit_groups": _groups()}
    with caplog.at_level(logging.WARNING, logger=_NOTICE):
        first = apply_grouped_messages_alias(template, variables)
        second = apply_grouped_messages_alias(template, variables)

    assert first["grouped_messages"] == _groups()
    assert second["grouped_messages"] == _groups()
    assert "grouped_messages" not in variables
    warnings = [
        record for record in caplog.records if "grouped_messages is deprecated" in record.message
    ]
    assert len(warnings) == 1
    assert "Removed in 2.0" in warnings[0].message


@pytest.mark.unit
def test_old_name_without_commit_groups_warns_and_keeps_mapping(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Naming grouped_messages without commit_groups warns and does not invent the alias."""
    template = "{{ grouped_messages }}"
    variables: dict[str, object] = {"version": "1.0.0"}
    with caplog.at_level(logging.WARNING, logger=_NOTICE):
        result = apply_grouped_messages_alias(template, variables)

    assert result is variables
    assert any("grouped_messages is deprecated" in record.message for record in caplog.records)


@pytest.mark.unit
def test_current_template_name_is_silent(caplog: pytest.LogCaptureFixture) -> None:
    """A template that uses commit_groups is not aliased and does not warn."""
    template = "{% for group in commit_groups %}{{ group.title }}{% endfor %}"
    variables: dict[str, object] = {"commit_groups": _groups()}
    with caplog.at_level(logging.WARNING, logger=_NOTICE):
        result = apply_grouped_messages_alias(template, variables)

    assert result is variables
    assert "grouped_messages" not in result
    assert caplog.records == []


@pytest.mark.unit
def test_pull_request_body_renders_old_name(caplog: pytest.LogCaptureFixture) -> None:
    """Release PR bodies that still loop over grouped_messages keep rendering."""
    config = PullRequestConfig(
        body="{% for group in grouped_messages %}{{ group.title }}{% endfor %}",
    )
    with caplog.at_level(logging.WARNING, logger=_NOTICE):
        rendered = config.render_body(
            PullRequestTemplateVars(
                version="1.0.0",
                date="01-01-2026",
                messages=["feat: add"],
                commit_groups=_groups(),
            )
        )

    assert "Features" in rendered
    assert any("grouped_messages is deprecated" in record.message for record in caplog.records)


@pytest.mark.unit
def test_pull_request_body_current_name_is_silent(caplog: pytest.LogCaptureFixture) -> None:
    """Release PR bodies that use commit_groups do not warn."""
    config = PullRequestConfig(
        body="{% for group in commit_groups %}{{ group.title }}{% endfor %}",
    )
    with caplog.at_level(logging.WARNING, logger=_NOTICE):
        rendered = config.render_body(
            PullRequestTemplateVars(
                version="1.0.0",
                date="01-01-2026",
                messages=["feat: add"],
                commit_groups=_groups(),
            )
        )

    assert "Features" in rendered
    assert caplog.records == []


@pytest.mark.unit
def test_changelog_update_warns_once(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Changelog updates still render the old name and warn once per process."""
    path = tmp_path / "CHANGELOG.md"
    manager = ChangelogManager(
        path=path,
        truncate=False,
        template="{% for group in grouped_messages %}{{ group.title }}{% endfor %}",
        header="",
        footer="",
    )
    groups = [CommitGroupConfig(title="Features", patterns=["^feat"], priority=1)]
    with caplog.at_level(logging.WARNING, logger=_NOTICE):
        manager.update(version="1.2.3", messages=["feat: add"], commit_groups=groups)
        manager.update(version="1.2.4", messages=["feat: more"], commit_groups=groups)

    assert path.read_text(encoding="utf-8").count("Features") == 2
    warnings = [
        record for record in caplog.records if "grouped_messages is deprecated" in record.message
    ]
    assert len(warnings) == 1
