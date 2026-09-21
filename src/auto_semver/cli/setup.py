# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI command to onboard a repository onto Action-Semver-Control."""

from __future__ import annotations

import logging
import webbrowser
from pathlib import Path

from auto_semver.setup.links import (
    SETUP_DOC_URL,
    app_registration_url,
    workflow_bump_deep_link,
    workflow_promote_deep_link,
)
from auto_semver.setup.scaffold import (
    RepoRef,
    detect_repo,
    scaffold_files,
    set_repo_secret,
    set_repo_variable,
    verify_gh_authenticated,
)

logger = logging.getLogger(__name__)


def run(
    *,
    owner: str | None = None,
    repo: str | None = None,
    default_branch: str | None = None,
    app_id: str | None = None,
    client_id: str | None = None,
    private_key_path: Path | None = None,
    dry_run: bool = False,
    open_browser: bool = False,
    skip_secrets: bool = False,
    skip_scaffold: bool = False,
) -> None:
    """Guide setup of GitHub App credentials and consumer workflow files.

    Args:
        owner: GitHub repository owner (defaults to origin remote).
        repo: GitHub repository name (defaults to origin remote).
        default_branch: Base branch for deep links and scaffolding context.
        app_id: Deprecated alias for client_id (kept for CLI compatibility).
        client_id: GitHub App Client ID (preferred; from app settings).
        private_key_path: Path to the App private key PEM file.
        dry_run: Print actions without writing secrets or files.
        open_browser: Open the prefilled App registration URL in a browser.
        skip_secrets: Skip writing GH_APP_CLIENT_ID and GH_APP_PRIVATE_KEY.
        skip_scaffold: Skip writing config and workflow files.
    """
    repo_ref = _resolve_repo(owner=owner, repo=repo, default_branch=default_branch)
    reg_url = app_registration_url()

    print("Action-Semver-Control setup")
    print("===========================")
    print()
    print("1. Register a GitHub App (Contents + Pull requests: read/write, webhooks off):")
    print(f"   {reg_url}")
    print()
    install_target = f"{repo_ref.owner}/{repo_ref.repo}"
    print("2. Install the app on this repository:")
    print(f"   https://github.com/settings/apps (Install App → {install_target})")
    print()
    print("3. Generate a private key and note the App **Client ID** (not the numeric App ID).")
    print()

    if open_browser and not dry_run:
        webbrowser.open(reg_url)

    if not skip_secrets:
        verify_gh_authenticated()
        resolved_client_id = (client_id or app_id or _prompt("GitHub App Client ID")).strip()
        key_path = private_key_path or Path(_prompt("Path to private key .pem file"))
        private_key = key_path.read_text(encoding="utf-8")
        set_repo_variable(
            owner=repo_ref.owner,
            repo=repo_ref.repo,
            name="GH_APP_CLIENT_ID",
            value=resolved_client_id,
            dry_run=dry_run,
        )
        set_repo_secret(
            owner=repo_ref.owner,
            repo=repo_ref.repo,
            name="GH_APP_PRIVATE_KEY",
            value=private_key,
            dry_run=dry_run,
        )
        print("Repository variable GH_APP_CLIENT_ID and secret GH_APP_PRIVATE_KEY configured.")
    else:
        print("Skipped credential configuration (--skip-secrets).")

    if not skip_scaffold:
        written = scaffold_files(Path.cwd(), dry_run=dry_run)
        if written:
            print("Scaffolded files:")
            for path in written:
                print(f"  - {path}")
        else:
            print("No new files scaffolded (targets already exist).")
    else:
        print("Skipped file scaffolding (--skip-scaffold).")

    bump_link = workflow_bump_deep_link(
        owner=repo_ref.owner,
        repo=repo_ref.repo,
        branch=repo_ref.default_branch,
    )
    promote_link = workflow_promote_deep_link(
        owner=repo_ref.owner,
        repo=repo_ref.repo,
        branch=repo_ref.default_branch,
    )

    print()
    print("Optional: add workflows via the GitHub UI instead of local scaffold:")
    print(f"  Bump:    {bump_link}")
    print(f"  Promote: {promote_link}")
    print()
    print(f"Full guide: {SETUP_DOC_URL}")
    print()
    print("Next: merge a PR to dev/staging/master to trigger the first semver bump.")


def _resolve_repo(
    *,
    owner: str | None,
    repo: str | None,
    default_branch: str | None,
) -> RepoRef:
    if owner and repo:
        return RepoRef(owner=owner, repo=repo, default_branch=default_branch or "master")
    detected = detect_repo()
    if default_branch:
        return RepoRef(
            owner=detected.owner,
            repo=detected.repo,
            default_branch=default_branch,
        )
    return detected


def _prompt(label: str) -> str:
    value = input(f"{label}: ").strip()
    if not value:
        msg = f"{label} is required"
        raise ValueError(msg)
    return value
