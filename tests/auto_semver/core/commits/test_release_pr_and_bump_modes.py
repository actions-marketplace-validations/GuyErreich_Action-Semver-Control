"""Tests for release PR noise fixes and cumulative bump mode."""

import pytest

from auto_semver.config import CommitGroupConfig, CommitGroupsConfig
from auto_semver.core.commits.grouper import CommitGrouper
from auto_semver.core.semver.version import Version

PR_222_SQUASH_BODY = """feat: add signed commit support via GitHub API

### Summary
- Add API-backed commits for verified merges

### Testing
- [x] Tests added and passing
- [x] Lint clean

Co-authored-by: Cursor <cursor@cursor.com>
Made with [Cursor]
---------"""


@pytest.mark.unit
def test_header_only_excludes_checkbox_lines_from_groups() -> None:
    """Squash PR bodies must not explode checklist lines into release PR bullets."""
    groups_config = CommitGroupsConfig(
        summary_mode="header_only",
        groups=[
            CommitGroupConfig(title="✨ Features", patterns=["^feat"], priority=1),
            CommitGroupConfig(title="📝 Other Changes", patterns=[".*"], priority=99),
        ],
    )

    grouped = CommitGrouper.group_messages([PR_222_SQUASH_BODY], groups_config)

    all_titles = [commit.title for group in grouped for commit in group.commits]
    assert len(all_titles) == 1
    assert all_titles[0] == "add signed commit support via GitHub API"
    assert not any("[x]" in title for title in all_titles)


@pytest.mark.unit
@pytest.mark.parametrize(
    "start,branches,expected",
    [
        ("1.3.14", ["fix/a", "fix/b"], "1.3.16"),
        ("1.3.14", ["feature/x"], "1.4.14"),
        ("1.3.14", ["fix/a", "fix/b", "feature/x"], "1.4.16"),
        ("1.4.16", ["breaking/change"], "2.0.0"),
    ],
)
def test_cumulative_bump_examples(start: str, branches: list[str], expected: str) -> None:
    """Cumulative mode accumulates patch/minor without resetting patch on minor."""
    version = Version.parse(start)
    version.bump_cumulative(branch_names=branches)
    assert str(version) == expected


@pytest.mark.unit
def test_classic_bump_unchanged_for_feature_branch() -> None:
    """Classic mode still resets patch on minor bump."""
    version = Version.parse("1.3.14")
    version.bump(branch_name="feature/example")
    assert str(version) == "1.4.0"
