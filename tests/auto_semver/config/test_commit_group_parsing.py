"""Tests for the CommitGroupConfig integration with CommitParser."""

from auto_semver.config import CommitGroupConfig, CommitGroupsConfig
from auto_semver.core.commits.grouper import CommitGrouper


class TestCommitGroupConfigParsing:
    """Test suite for CommitGroupConfig using the new parser."""

    def test_group_messages_type_1_simple(self) -> None:
        """Test Type 1: Simple header commit matching via regex."""
        messages = ["feat: add feature A", "fix: fix bug B"]
        groups_config = [
            CommitGroupConfig(title="Features", patterns=["^feat"], priority=1, match_groups=[]),
            CommitGroupConfig(title="Fixes", patterns=["^fix"], priority=2, match_groups=[]),
        ]

        result = CommitGrouper.group_messages(
            messages,
            CommitGroupsConfig(summary_mode="expand_body", groups=groups_config),
        )

        assert len(result) == 2
        assert result[0].title == "Features"
        assert len(result[0].commits) == 1
        assert result[0].commits[0].title == "add feature A"

        assert result[1].title == "Fixes"
        assert len(result[1].commits) == 1
        assert result[1].commits[0].title == "fix bug B"

    def test_group_messages_type_3_items(self) -> None:
        """Test Type 3: Commit with list items (bullets)."""
        messages = [
            """Update deps

- Upgrade libA
- Upgrade libB"""
        ]

        groups_config = [
            CommitGroupConfig(
                title="Deps", patterns=["^Update deps", "^Upgrade"], priority=1, match_groups=[]
            ),
        ]

        # Note: The parser will split the commit into items "Upgrade libA" and "Upgrade libB"
        # Since they don't have explicit groups, we check regex. "Upgrade.*" matches "Upgrade libA".

        result = CommitGrouper.group_messages(
            messages,
            CommitGroupsConfig(summary_mode="expand_body", groups=groups_config),
        )

        assert len(result) == 1
        assert result[0].title == "Deps"
        assert len(result[0].commits) == 2
        assert result[0].commits[0].title == "Upgrade libA"
        assert result[0].commits[1].title == "Upgrade libB"

    def test_group_messages_type_4_grouped(self) -> None:
        """Test Type 4: Commit with explicitly grouped items."""
        message = """Release v1

Features:
- Add dark mode

Bugs:
- Fix crash"""

        messages = [message]

        groups_config = [
            CommitGroupConfig(
                title="Enhancements", patterns=[], match_groups=["Features"], priority=1
            ),
            CommitGroupConfig(title="Bug Fixes", patterns=[], match_groups=["Bugs"], priority=2),
        ]

        result = CommitGrouper.group_messages(
            messages,
            CommitGroupsConfig(summary_mode="expand_body", groups=groups_config),
        )

        assert len(result) == 2

        # Features -> Enhancements
        group1 = next((g for g in result if g.title == "Enhancements"), None)
        assert group1 is not None
        assert len(group1.commits) == 1
        assert group1.commits[0].title == "Add dark mode"

        # Bugs -> Bug Fixes
        group2 = next((g for g in result if g.title == "Bug Fixes"), None)
        assert group2 is not None
        assert len(group2.commits) == 1
        assert group2.commits[0].title == "Fix crash"

    def test_harden_title_classifies_as_features_header_only(self) -> None:
        """Imperative Harden PR/commit titles should land in Features under header_only."""
        messages = ["Harden merge-based auto-promote with dev/rc metadata wins"]
        groups_config = CommitGroupsConfig(
            summary_mode="header_only",
            groups=[
                CommitGroupConfig(
                    title="✨ Features & Enhancements",
                    patterns=["^Harden ", "^Hardened ", "^feat(\\([^)]*\\))?:", "^Improve "],
                    priority=2,
                ),
                CommitGroupConfig(title="📝 Other Changes", patterns=[".*"], priority=99),
            ],
        )

        result = CommitGrouper.group_messages(messages, groups_config)

        assert len(result) == 1
        assert result[0].title == "✨ Features & Enhancements"
        assert len(result[0].commits) == 1
        assert "Harden merge-based" in result[0].commits[0].title

    def test_migrate_title_classifies_as_features_header_only(self) -> None:
        """Imperative Migrate titles should land in Features under header_only."""
        messages = ["Migrate App auth to client-id and pin checkout to v7"]
        groups_config = CommitGroupsConfig(
            summary_mode="header_only",
            groups=[
                CommitGroupConfig(
                    title="✨ Features & Enhancements",
                    patterns=["^Migrate ", "^Migrated "],
                    priority=2,
                ),
                CommitGroupConfig(title="📝 Other Changes", patterns=[".*"], priority=99),
            ],
        )

        result = CommitGrouper.group_messages(messages, groups_config)

        assert len(result) == 1
        assert result[0].title == "✨ Features & Enhancements"
