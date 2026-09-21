"""Unit tests for GitHubPRBuilder template functions."""

from auto_semver.config import Commit, CommitGroup
from auto_semver.config.constants import PR_HIDDEN_MARKER
from auto_semver.core.pr.github_builder import GitHubPRBuilder, GitHubPRTemplateVariables


def test_pr_builder_registers_functions() -> None:
    """Test that GitHubPRBuilder registers its own template functions."""
    variables = GitHubPRTemplateVariables(
        version="1.0.0",
        previous_version="1.0.0",
        commit_groups=[],
        breaking_changes=[],
        author="",
        repository="",
        date="",
        branch="",
        base_branch="",
        labels=None,
        groups=None,
    )
    builder = GitHubPRBuilder(
        data=variables,
        title_template="{{ truncate_commit('This is a very long commit message', 20) }}",
        body_template="Type: {{ conventional_type('feat: add feature') }}",
    )
    assert builder.title == "This is a very lo..."
    assert builder.body == f"{PR_HIDDEN_MARKER}\nType: feat"


def test_pr_builder_functions_as_filters() -> None:
    """Test that PR functions work as filters."""
    variables = GitHubPRTemplateVariables(
        version="1.0.0",
        previous_version="1.0.0",
        commit_groups=[],
        breaking_changes=[],
        author="",
        repository="",
        date="",
        branch="",
        base_branch="",
        labels=None,
        groups=None,
    )
    builder = GitHubPRBuilder(
        data=variables,
        title_template="{{ truncate_commit('This is a very long commit message', 20) }}",
        body_template="{{ capitalize_first('hello world') }}",
    )
    assert builder.title == "This is a very lo..."
    assert builder.body == f"{PR_HIDDEN_MARKER}\nHello world"


def test_pr_builder_complex_functions() -> None:
    """Test more complex PR functions."""
    # Test with sample groups data
    groups = [
        CommitGroup(
            title="Features",
            commits=[
                Commit(title="feat: add login", body=""),
                Commit(title="feat: add logout", body=""),
            ],
            priority=1,
        ),
        CommitGroup(
            title="Bug Fixes",
            commits=[Commit(title="fix: resolve crash", body="")],
            priority=2,
        ),
        CommitGroup(
            title="Breaking Changes",
            commits=[Commit(title="feat!: new API", body="")],
            priority=3,
        ),
    ]
    variables = GitHubPRTemplateVariables(
        version="1.0.0",
        previous_version="1.0.0",
        commit_groups=[],
        breaking_changes=[],
        author="",
        repository="",
        date="",
        branch="",
        base_branch="",
        labels=None,
        groups=groups,
    )
    builder = GitHubPRBuilder(
        data=variables,
        title_template="Groups: {{ count_groups(groups) }}, Commits: {{ count_commits(groups) }}",
        body_template="Breaking: {{ has_breaking(groups) }}",
    )
    assert builder.title == "Groups: 3, Commits: 4"  # 2 + 1 + 1 = 4 commits total
    assert builder.body == f"{PR_HIDDEN_MARKER}\nBreaking: True"


def test_pr_builder_date_formatting() -> None:
    """Test date formatting function."""
    variables = GitHubPRTemplateVariables(
        version="1.0.0",
        previous_version="1.0.0",
        commit_groups=[],
        breaking_changes=[],
        author="",
        repository="",
        date="2024-12-25",
        branch="",
        base_branch="",
        labels=None,
        groups=None,
    )
    builder = GitHubPRBuilder(
        data=variables,
        title_template="Released: {{ format_date_custom(date, '%B %d, %Y') }}",
        body_template="Date: {{ format_date_custom(date, '%m/%d/%Y') }}",
    )
    assert builder.title == "Released: December 25, 2024"
    assert builder.body == f"{PR_HIDDEN_MARKER}\nDate: 12/25/2024"
