"""Test commit bullet point extraction for grouping."""

from auto_semver.config import CommitGroupConfig, CommitGroupsConfig
from auto_semver.core.commits.grouper import CommitGrouper
from auto_semver.core.commits.parser import CommitParser


def test_extract_individual_items_with_bullets() -> None:
    """Test extraction of individual bullet points from commit bodies."""
    commit_with_bullets = """Add comprehensive E2E and integration test suite

Test Infrastructure:
- Add modular fixtures for isolated testing
- Create 17 comprehensive E2E/integration tests
- Implement test_e2e_workflows.py with 6 workflow scenarios

Template System Improvements:
- Extract shared template utilities to templates/utils.py
- Add comprehensive template function registry
- Implement custom Jinja2 filters for PR/changelog generation"""

    parser = CommitParser()
    parsed = parser.parse(commit_with_bullets)

    # New structure: flattened list for verification
    items = []
    items.extend(parsed.bullet_points)
    for section_items in parsed.sectioned_changes.values():
        items.extend(section_items)

    # Should extract 6 bullet points
    assert len(items) == 6
    assert "Add modular fixtures for isolated testing" in items
    assert "Create 17 comprehensive E2E/integration tests" in items
    assert "Implement test_e2e_workflows.py with 6 workflow scenarios" in items
    assert "Extract shared template utilities to templates/utils.py" in items
    assert "Add comprehensive template function registry" in items
    assert "Implement custom Jinja2 filters for PR/changelog generation" in items


def test_extract_individual_items_without_bullets() -> None:
    """Test that commits without bullets are kept as-is."""
    simple_commit = "feat: add user authentication system"

    parser = CommitParser()
    parsed = parser.parse(simple_commit)

    # Simple commit has no items, just header/body
    assert not parsed.bullet_points
    assert not parsed.sectioned_changes
    assert parsed.header == simple_commit


def test_extract_individual_items_mixed() -> None:
    """Test extraction with mix of simple and multi-line commits."""
    # This was testing an implementation detail of flattening a list of messages.
    # The new parser processes one message at a time.
    # We will test that we can parse each message correctly.

    msg1 = "fix: resolve login bug"
    msg2 = """Refactor configuration system

Core Changes:
- Split monolithic config/data.py into focused modules
- Create centralized Jinja2 template engine
- Add typed template variable dataclasses"""
    msg3 = "docs: update README"

    parser = CommitParser()

    # Msg 1
    p1 = parser.parse(msg1)
    assert not p1.bullet_points
    assert not p1.sectioned_changes
    assert p1.header == msg1

    # Msg 2
    p2 = parser.parse(msg2)
    # Check sections
    assert "Core Changes" in p2.sectioned_changes
    descriptions = p2.sectioned_changes["Core Changes"]
    assert len(descriptions) == 3
    assert "Split monolithic config/data.py into focused modules" in descriptions
    assert "Create centralized Jinja2 template engine" in descriptions
    assert "Add typed template variable dataclasses" in descriptions

    # Msg 3
    p3 = parser.parse(msg3)
    assert not p3.bullet_points
    assert not p3.sectioned_changes
    assert p3.header == msg3


def test_group_messages_with_bullet_extraction() -> None:
    """Test that bullet points are categorized into correct groups."""
    messages = [
        """Add comprehensive test suite

Testing Infrastructure:
- Add modular fixtures for isolated testing
- Create 17 comprehensive E2E/integration tests

Features:
- Add console script entry point for Docker
- Enhance changelog template formatting"""
    ]

    commit_groups = [
        CommitGroupConfig(title="✨ Features", patterns=["^Add ", "^Enhance "], priority=1),
        CommitGroupConfig(title="🧪 Testing", patterns=["^Create ", "fixtures"], priority=2),
    ]

    grouped = CommitGrouper.group_messages(
        messages,
        CommitGroupsConfig(summary_mode="expand_body", groups=commit_groups),
    )

    # Should have 2 groups
    assert len(grouped) == 2

    # Check Features group
    features = next(g for g in grouped if g.title == "✨ Features")
    assert len(features.commits) == 3  # "Add modular...", "Add console...", "Enhance..."
    titles = [c.title for c in features.commits]
    assert "Add modular fixtures for isolated testing" in titles
    assert "Add console script entry point for Docker" in titles
    assert "Enhance changelog template formatting" in titles

    # Check Testing group
    testing = next(g for g in grouped if g.title == "🧪 Testing")
    assert len(testing.commits) == 1  # "Create 17..."
    assert "Create 17 comprehensive E2E/integration tests" in testing.commits[0].title


def test_group_messages_simple_commits_without_body() -> None:
    """Test that simple commits without bodies are categorized correctly."""
    messages = [
        "feat: add user authentication",
        "fix: resolve login bug",
        "docs: update README",
        "Add console script entry point",
    ]

    commit_groups = [
        CommitGroupConfig(title="✨ Features", patterns=["^feat:", "^Add "], priority=1),
        CommitGroupConfig(title="🐛 Bug Fixes", patterns=["^fix:"], priority=2),
        CommitGroupConfig(title="📚 Documentation", patterns=["^docs:"], priority=3),
    ]

    grouped = CommitGrouper.group_messages(
        messages,
        CommitGroupsConfig(summary_mode="expand_body", groups=commit_groups),
    )

    # Should have 3 groups
    assert len(grouped) == 3

    # Check Features group - should have 2 items
    features = next(g for g in grouped if g.title == "✨ Features")
    assert len(features.commits) == 2
    titles = [c.title for c in features.commits]
    assert "add user authentication" in titles  # Cleaned from "feat: ..."
    assert "Add console script entry point" in titles

    # Check Bug Fixes group - should have 1 item
    fixes = next(g for g in grouped if g.title == "🐛 Bug Fixes")
    assert len(fixes.commits) == 1
    assert "resolve login bug" in fixes.commits[0].title

    # Check Documentation group - should have 1 item
    docs = next(g for g in grouped if g.title == "📚 Documentation")
    assert len(docs.commits) == 1
    assert "update README" in docs.commits[0].title


def test_group_messages_mixed_simple_and_bulleted() -> None:
    """Test mixed scenario with simple commits and commits with bullet points."""
    messages = [
        "fix: resolve login timeout issue",
        """Refactor configuration system

Core Changes:
- Split monolithic config into focused modules
- Create centralized template engine
- Add typed variable dataclasses

Testing:
- Add comprehensive test suite
- Implement fixture-based testing""",
        "docs: update installation guide",
    ]

    commit_groups = [
        CommitGroupConfig(
            title="♻️ Refactoring", patterns=["^Refactor", "^Split ", "^Create "], priority=1
        ),
        CommitGroupConfig(title="🐛 Bug Fixes", patterns=["^fix:"], priority=2),
        CommitGroupConfig(
            title="🧪 Testing", patterns=["^Add comprehensive", "^Implement "], priority=3
        ),
        CommitGroupConfig(title="📚 Documentation", patterns=["^docs:"], priority=4),
        CommitGroupConfig(title="📝 Other", patterns=["^Add typed"], priority=5),
    ]

    grouped = CommitGrouper.group_messages(
        messages,
        CommitGroupsConfig(summary_mode="expand_body", groups=commit_groups),
    )

    # Check that simple commits are preserved
    fixes = next(g for g in grouped if g.title == "🐛 Bug Fixes")
    assert len(fixes.commits) == 1
    assert "resolve login timeout issue" in fixes.commits[0].title

    docs = next(g for g in grouped if g.title == "📚 Documentation")
    assert len(docs.commits) == 1
    assert "update installation guide" in docs.commits[0].title

    # Check that bullets were extracted and categorized
    refactoring = next(g for g in grouped if g.title == "♻️ Refactoring")
    assert len(refactoring.commits) == 2  # "Split..." and "Create..."

    testing = next(g for g in grouped if g.title == "🧪 Testing")
    assert len(testing.commits) == 2  # "Add comprehensive..." and "Implement..."

    other = next(g for g in grouped if g.title == "📝 Other")
    assert len(other.commits) == 1  # "Add typed..."
