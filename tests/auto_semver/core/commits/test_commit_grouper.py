"""Test commit grouper functionality."""

import logging

import pytest

from auto_semver.config import CommitGroupConfig, Config
from auto_semver.core.commits.grouper import CommitGrouper
from tests.fixtures.config_fixture import ConfigFixture

# For backward compatibility with old test names
CommitGroupModel = CommitGroupConfig  # TODO: might want to leave it as CommitGroupConfig


@pytest.fixture
def config_with_simple_groups(config_fixture: ConfigFixture) -> Config:
    """Create a config with simple commit groups for testing."""
    config_fixture.create_with_simple_patterns()
    return Config(config_fixture.config_path)


@pytest.fixture
def config_with_regex_groups(config_fixture: ConfigFixture) -> Config:
    """Create a config with explicit regex patterns for testing."""
    config_fixture.create_with_regex_patterns()
    return Config(config_fixture.config_path)


@pytest.fixture
def config_with_complex_groups(config_fixture: ConfigFixture) -> Config:
    """Create a config with complex commit groups for testing."""
    config_fixture.create_with_complex_commit_groups()
    return Config(config_fixture.config_path)


@pytest.fixture
def config_with_no_groups(config_fixture: ConfigFixture) -> Config:
    """Create a config with no commit groups for testing."""
    config_fixture.create_empty_commit_groups()
    return Config(config_fixture.config_path)


@pytest.fixture
def sample_commit_messages() -> list[str]:
    """Sample commit messages for testing."""
    return [
        "feat: add user authentication",
        "feat(api): implement REST endpoints",
        "fix: resolve login issue",
        "docs: update README",
        "chore: update dependencies",
    ]


def test_group_commit_messages_basic(
    config_with_simple_groups: Config,
    sample_commit_messages: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test basic commit grouping functionality."""
    with caplog.at_level(logging.INFO, logger="auto_semver.core.commits.grouper"):
        grouped = CommitGrouper.group_messages(
            sample_commit_messages, config_with_simple_groups.data.commit_groups
        )

    assert len(grouped) == 3  # 2 defined groups + 1 for unmatched

    # Check group titles and priorities
    group_titles = [group.title for group in grouped]
    assert "Features" in group_titles
    assert "Bug Fixes" in group_titles
    assert "Other Changes" in group_titles  # docs and chore go to "Other Changes"

    # Check sorting by priority
    priorities = [group.priority for group in grouped[:-1]]  # Exclude "Other Changes"
    assert priorities == sorted(priorities)
    assert any("Grouped 5 messages into 3 commit groups" in r.message for r in caplog.records)


def test_group_commit_messages_content(
    config_with_simple_groups: Config, sample_commit_messages: list[str]
) -> None:
    """Test that commits are properly grouped by content."""
    grouped = CommitGrouper.group_messages(
        sample_commit_messages, config_with_simple_groups.data.commit_groups
    )

    # Find Features group
    features_group = next(g for g in grouped if g.title == "Features")
    assert len(features_group.commits) == 2
    commit_messages = [c.title for c in features_group.commits]
    assert "add user authentication" in commit_messages
    assert "implement REST endpoints" in commit_messages

    # Find Bug Fixes group
    fixes_group = next(g for g in grouped if g.title == "Bug Fixes")
    assert len(fixes_group.commits) == 1
    assert fixes_group.commits[0].title == "resolve login issue"

    # Find Other Changes group (docs and chore go here with simple patterns)
    other_group = next(g for g in grouped if g.title == "Other Changes")
    assert len(other_group.commits) == 2
    other_messages = [c.title for c in other_group.commits]
    assert "update README" in other_messages
    assert "update dependencies" in other_messages


def test_group_commit_messages_empty_commits(config_with_simple_groups: Config) -> None:
    """Test grouping with no commits."""
    result = CommitGrouper.group_messages([], config_with_simple_groups.data.commit_groups)
    assert len(result) == 0


def test_group_commit_messages_no_groups(config_with_no_groups: Config) -> None:
    """Test grouping with no commit groups defined."""
    messages = ["feat: test commit"]

    result = CommitGrouper.group_messages(messages, config_with_no_groups.data.commit_groups)
    assert len(result) == 1
    assert result[0].title == "📝 Changes"
    assert len(result[0].commits) == 1


def test_group_commit_messages_all_unmatched(config_with_simple_groups: Config) -> None:
    """Test when no commits match any group patterns."""
    messages = ["chore: update", "style: format", "ci: build"]

    result = CommitGrouper.group_messages(messages, config_with_simple_groups.data.commit_groups)

    # Should have just the "Other Changes" group with all commits
    assert len(result) == 1
    assert result[0].title == "Other Changes"
    assert len(result[0].commits) == 3


def test_group_commit_messages_commit_format() -> None:
    """Test that commit dictionaries have the correct format."""
    messages = ["feat: test feature"]
    groups = [CommitGroupConfig(title="Features", patterns=["feat"], priority=1)]
    result = CommitGrouper.group_messages(messages, groups)

    # result is now a list[CommitGroup] (CommitGroups)
    assert len(result) == 1
    assert result[0].title == "Features"
    assert len(result[0].commits) == 1

    commit = result[0].commits[0]
    assert commit.title == "test feature"  # Parsed title without prefix


def test_group_commit_messages_pattern_matching(config_with_regex_groups: Config) -> None:
    """Test various pattern matching scenarios with controlled regex patterns."""
    messages = [
        "feat: new feature",
        "feat(scope): scoped feature",
        "feature: should not match",  # This WILL match simple "feat" pattern but NOT "^feat" pattern
        "feat!: breaking feature",
        "fix: bug fix",
        "bugfix: should not match",  # This WILL match simple "fix" pattern but NOT "^fix" pattern
    ]

    grouped = CommitGrouper.group_messages(messages, config_with_regex_groups.data.commit_groups)

    # With ^feat and ^fix regex patterns, only exact matches at start should work
    # But "feature" still matches "^feat" since feature starts with feat
    # Features should have all 4 commits that start with "feat"
    features_group = next(g for g in grouped if g.title == "Features")
    assert len(features_group.commits) == 4

    # Bug Fixes should have only "fix: bug fix" (1 commit - "bugfix" doesn't match "^fix")
    fixes_group = next(g for g in grouped if g.title == "Bug Fixes")
    assert len(fixes_group.commits) == 1

    # Other Changes should have the unmatched "bugfix" commit
    other_group = next(g for g in grouped if g.title == "Other Changes")
    assert len(other_group.commits) == 1
    assert other_group.commits[0].title == "should not match"


def test_group_commit_messages_exact_patterns(config_with_complex_groups: Config) -> None:
    """Test exact pattern matching with proper regex anchors using complex config."""
    messages = [
        "feat: new feature",
        "feat(scope): scoped feature",
        "feature: should not match",
        "feat!: breaking feature",
        "fix: bug fix",
        "bugfix: should not match",
    ]

    grouped = CommitGrouper.group_messages(messages, config_with_complex_groups.data.commit_groups)

    # Breaking Changes should have feat! (highest priority match)
    breaking_group = next(g for g in grouped if g.title == "Breaking Changes")
    assert len(breaking_group.commits) == 1
    assert breaking_group.commits[0].title == "breaking feature"

    # Features should have only conventional commits starting with feat: (but not feat!)
    features_group = next(g for g in grouped if g.title == "Features")
    assert len(features_group.commits) == 2
    feat_messages = [c.title for c in features_group.commits]
    assert "new feature" in feat_messages
    assert "scoped feature" in feat_messages

    # Bug Fixes should have only conventional commits starting with fix:
    fixes_group = next(g for g in grouped if g.title == "Bug Fixes")
    assert len(fixes_group.commits) == 1
    assert fixes_group.commits[0].title == "bug fix"

    # Other Changes should have the non-conventional commits
    other_group = next(g for g in grouped if g.title == "Other Changes")
    assert len(other_group.commits) == 2
    other_messages = [c.title for c in other_group.commits]
    assert "should not match" in other_messages
    assert "should not match" in other_messages
