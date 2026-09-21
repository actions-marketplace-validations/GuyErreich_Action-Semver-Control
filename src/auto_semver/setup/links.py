# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Onboarding URL builders and template helpers for Action-Semver-Control."""

from __future__ import annotations

import importlib.resources
import urllib.parse

ACTION_REPO = "GuyErreich/Action-Semver-Control"
SETUP_DOC_URL = f"https://github.com/{ACTION_REPO}/blob/dev/docs/SETUP.md"
MARKETPLACE_URL = "https://github.com/marketplace/actions/auto-semver-bumper"


def app_registration_url(*, app_name: str = "Auto Semver Bot") -> str:
    """Build a prefilled GitHub App registration URL.

    Args:
        app_name: Display name for the new GitHub App.

    Returns:
        URL that opens GitHub's new-app form with permissions pre-selected.
    """
    params = {
        "name": app_name,
        "description": "Signed commits and PRs for Action-Semver-Control",
        "url": f"https://github.com/{ACTION_REPO}",
        "public": "true",
        "webhook_active": "false",
        "contents": "write",
        "pull_requests": "write",
    }
    query = urllib.parse.urlencode(params)
    return f"https://github.com/settings/apps/new?{query}"


def org_app_registration_url(*, org: str, app_name: str = "Auto Semver Bot") -> str:
    """Build a prefilled GitHub App registration URL for an organization."""
    params = {
        "name": app_name,
        "description": "Signed commits and PRs for Action-Semver-Control",
        "url": f"https://github.com/{ACTION_REPO}",
        "public": "true",
        "webhook_active": "false",
        "contents": "write",
        "pull_requests": "write",
    }
    query = urllib.parse.urlencode(params)
    return f"https://github.com/organizations/{org}/settings/apps/new?{query}"


def new_file_pr_url(
    *,
    owner: str,
    repo: str,
    branch: str,
    filename: str,
    content: str,
    message: str,
    pr_branch: str | None = None,
) -> str:
    """Build a GitHub web URL that prefills a new file and opens a PR.

    Args:
        owner: Repository owner.
        repo: Repository name.
        branch: Base branch for the PR.
        filename: Path of the file to create (e.g. .github/workflows/auto-semver.yml).
        content: Raw file contents.
        message: Commit message.
        pr_branch: Optional head branch name for the PR.

    Returns:
        URL-encoded deep link to GitHub's new-file editor.
    """
    params: dict[str, str] = {
        "filename": filename,
        "value": content,
        "message": message,
        "quick_pull": branch,
    }
    if pr_branch:
        params["target_branch"] = pr_branch
    query = urllib.parse.urlencode(params)
    return f"https://github.com/{owner}/{repo}/new/{branch}?{query}"


def load_template(name: str) -> str:
    """Load a static onboarding template bundled with the package."""
    path = importlib.resources.files("auto_semver.setup.scaffolds").joinpath(name)
    return path.read_text(encoding="utf-8")


def workflow_bump_deep_link(*, owner: str, repo: str, branch: str) -> str:
    """Deep link to add the auto-semver caller workflow via the GitHub UI."""
    content = load_template("auto-semver.caller.yml")
    return new_file_pr_url(
        owner=owner,
        repo=repo,
        branch=branch,
        filename=".github/workflows/auto-semver.yml",
        content=content,
        message="Add Action-Semver-Control bump workflow",
        pr_branch="add-auto-semver",
    )


def workflow_promote_deep_link(*, owner: str, repo: str, branch: str) -> str:
    """Deep link to add the manual promotion caller workflow via the GitHub UI."""
    content = load_template("promote.caller.yml")
    return new_file_pr_url(
        owner=owner,
        repo=repo,
        branch=branch,
        filename=".github/workflows/promote.yml",
        content=content,
        message="Add Action-Semver-Control promotion workflow",
        pr_branch="add-semver-promote",
    )
