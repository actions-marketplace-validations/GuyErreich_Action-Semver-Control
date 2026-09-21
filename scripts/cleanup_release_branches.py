#!/usr/bin/env python3
# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Clean up stale auto-semver-owned release branches on the remote."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from auto_semver.adapters.git.ops import GitOps
from auto_semver.config import Config

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete merged/closed auto-semver release branches (ownership-guarded)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print actions without deleting (default: true)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete branches (disables dry-run)",
    )
    parser.add_argument(
        "--github-token",
        default=None,
        help="GitHub token (defaults to GH_TOKEN or GITHUB_TOKEN env)",
    )
    parser.add_argument(
        "--remote-prefix",
        default="origin/",
        help="Remote prefix when listing branches",
    )
    return parser.parse_args()


def main() -> int:
    """Run release branch cleanup with dry-run default unless --apply is set."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    dry_run = args.dry_run and not args.apply

    token = args.github_token or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        logger.error("GitHub token required (--github-token or GH_TOKEN/GITHUB_TOKEN)")
        return 1

    config = Config()
    release_cfg = config.data.release
    branch_prefix = release_cfg.branch_prefix.rstrip("/") + "/"
    labels = config.data.pull_request.labels

    gitops = GitOps(ensure_safe=True, github_token=token)
    gitops.fetch()

    remote = gitops.repo.remote()
    remote_refs = [ref.name for ref in remote.refs]

    candidates: list[str] = []
    for ref_name in remote_refs:
        branch_name = ref_name.split("/", maxsplit=1)[-1] if "/" in ref_name else ref_name
        if branch_name.startswith(branch_prefix.rstrip("/")):
            candidates.append(branch_name)
        elif branch_name.startswith("release/") and branch_name != "release":
            candidates.append(branch_name)

    if not candidates:
        logger.info("No candidate release branches found")
        return 0

    deleted = 0
    skipped = 0

    for branch_name in sorted(set(candidates)):
        owned, reason = gitops.is_auto_semver_release_branch(
            branch_name=branch_name,
            github_token=token,
            branch_prefix=release_cfg.branch_prefix,
            labels=labels,
            require_closed_pr=True,
        )
        if not owned:
            logger.info("SKIP %s: %s", branch_name, reason)
            skipped += 1
            continue

        pr = gitops._find_release_pr(github_token=token, branch_name=branch_name)
        if pr and pr.state == "open":
            logger.info("SKIP %s: pull request still open (#%s)", branch_name, pr.number)
            skipped += 1
            continue

        if dry_run:
            logger.info("DRY-RUN delete %s", branch_name)
        else:
            gitops.delete_branch(branch_name=branch_name)
            logger.info("DELETED %s", branch_name)
        deleted += 1

    logger.info(
        "Done: %s candidate(s), %s skipped, %s %s",
        len(candidates),
        skipped,
        deleted,
        "would delete" if dry_run else "deleted",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
