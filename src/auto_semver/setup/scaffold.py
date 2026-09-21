# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Repository scaffolding for Action-Semver-Control onboarding."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from auto_semver.setup.links import load_template

logger = logging.getLogger(__name__)

_GH_REMOTE_RE = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$")


@dataclass(frozen=True, slots=True)
class RepoRef:
    """GitHub repository coordinates."""

    owner: str
    repo: str
    default_branch: str


def parse_github_remote(url: str) -> tuple[str, str]:
    """Extract owner and repo from a git remote URL."""
    match = _GH_REMOTE_RE.search(url.strip())
    if not match:
        msg = f"Could not parse GitHub owner/repo from remote: {url}"
        raise ValueError(msg)
    return match.group("owner"), match.group("repo")


def detect_repo(cwd: Path | None = None) -> RepoRef:
    """Detect GitHub repository from the current git checkout."""
    root = cwd or Path.cwd()
    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    owner, repo = parse_github_remote(remote)
    branch = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    default_branch = "master"
    if branch.returncode == 0:
        default_branch = branch.stdout.strip().rsplit("/", maxsplit=1)[-1]
    ref = RepoRef(owner=owner, repo=repo, default_branch=default_branch)
    logger.info("Detected repo %s/%s (default_branch=%s)", owner, repo, default_branch)
    return ref


def scaffold_files(root: Path, *, dry_run: bool = False) -> list[Path]:
    """Write onboarding config and caller workflows into a consumer repository."""
    written: list[Path] = []
    targets = {
        root / "auto_semver_config.yml": load_template("auto_semver_config.yml"),
        root / ".github/workflows/auto-semver.yml": load_template("auto-semver.caller.yml"),
        root / ".github/workflows/promote.yml": load_template("promote.caller.yml"),
    }
    for path, content in targets.items():
        if path.exists():
            continue
        if dry_run:
            written.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    logger.info(
        "Scaffolded %d files under %s (dry_run=%s)",
        len(written),
        root,
        dry_run,
    )
    return written


def set_repo_secret(*, owner: str, repo: str, name: str, value: str, dry_run: bool) -> None:
    """Set a repository secret using the GitHub CLI."""
    if dry_run:
        logger.info("Dry-run: would set secret %s on %s/%s", name, owner, repo)
        return
    subprocess.run(
        ["gh", "secret", "set", name, "--repo", f"{owner}/{repo}"],
        input=value,
        text=True,
        check=True,
    )
    logger.info("Set secret %s on %s/%s", name, owner, repo)


def set_repo_variable(*, owner: str, repo: str, name: str, value: str, dry_run: bool) -> None:
    """Set a repository Actions variable using the GitHub CLI."""
    if dry_run:
        logger.info("Dry-run: would set variable %s on %s/%s", name, owner, repo)
        return
    subprocess.run(
        ["gh", "variable", "set", name, "--repo", f"{owner}/{repo}", "--body", value],
        check=True,
    )
    logger.info("Set variable %s on %s/%s", name, owner, repo)


def verify_gh_authenticated() -> None:
    """Ensure gh is installed and authenticated."""
    subprocess.run(["gh", "auth", "status"], check=True, capture_output=True, text=True)
