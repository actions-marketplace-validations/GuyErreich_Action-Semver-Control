"""Tests for ChangelogManager integration with template engine via ChangelogConfig."""

from pathlib import Path

import pytest

from auto_semver.config import ChangelogConfig, ChangelogTemplateVars, CommitGroupConfig
from auto_semver.core.changelog.manager import ChangelogManager
from auto_semver.core.commits.grouper import CommitGrouper
from auto_semver.templates.engine import reset_template_engine


@pytest.mark.unit
def test_manager_uses_engine_functions(tmp_path: Path) -> None:
    """Ensure engine-registered functions (e.g., title_case) are usable in manager rendering."""
    reset_template_engine()
    changelog_cfg = ChangelogConfig(
        file=tmp_path / "CHANGELOG.md",
        truncate=True,
        template=(
            "## [{{version}}] - {{date}}\n\n"
            "{{ title_case('some heading') }}\n"
            "{% for group in commit_groups %}### {{ group.title }} ({{ group.commits|length }})\n{% endfor %}"
        ),
    )

    mgr = ChangelogManager(
        path=Path(changelog_cfg.file),
        truncate=changelog_cfg.truncate,
        template=changelog_cfg.template,
        header=changelog_cfg.header or "",
        footer=changelog_cfg.footer or "",
    )

    msgs = ["feat: add feature", "fix: bug"]
    groups = [CommitGroupConfig(title="Features", patterns=["^feat:"], priority=1)]
    grouped = CommitGrouper.group_messages(msgs, groups)
    vars_obj = ChangelogTemplateVars(
        version="1.2.3",
        date="2025-10-04",
        messages=msgs,
        commit_groups=grouped,
    )

    rendered = mgr.render_template(vars_obj.__dict__)
    assert "Some Heading" in rendered  # title_case applied

    mgr.update(version="1.2.3", messages=msgs, commit_groups=groups)
    content = Path(changelog_cfg.file).read_text(encoding="utf-8")
    assert "Some Heading" in content
    assert "Features" in content
