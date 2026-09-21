# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate consumer repository setup for Action-Semver-Control."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_CONCURRENCY_PATTERN = re.compile(
    r"auto-semver-bump-\$\{\{\s*github\.repository\s*\}\}",
    re.IGNORECASE,
)
_CANCEL_FALSE_PATTERN = re.compile(
    r"cancel-in-progress:\s*false",
    re.IGNORECASE,
)


def check_workflow_concurrency(workflows_dir: Path | None = None) -> list[str]:
    """
    Return actionable errors when caller workflows lack required concurrency.

    Args:
        workflows_dir: Path to `.github/workflows` (defaults to cwd).

    Returns:
        List of error messages (empty when valid).
    """
    root = workflows_dir or Path(".github/workflows")
    errors: list[str] = []

    if not root.exists():
        errors.append(
            f"Missing workflows directory: {root}. "
            "Add .github/workflows/auto-semver.yml with a concurrency block."
        )
        return errors

    workflow_files = list(root.glob("*.yml")) + list(root.glob("*.yaml"))
    bump_files = [
        path for path in workflow_files if "auto-semver" in path.name or "semver" in path.name
    ]

    if not bump_files:
        errors.append(
            "No auto-semver caller workflow found under .github/workflows/. "
            "Expected auto-semver.yml (or similar) calling semver-bump.reusable.yml."
        )
        return errors

    for path in bump_files:
        content = path.read_text(encoding="utf-8")
        if "workflow_call" in content and "semver-bump" in content:
            continue
        if "uses:" in content and "semver-bump.reusable" in content:
            if not _CONCURRENCY_PATTERN.search(content):
                errors.append(
                    f"{path}: missing required concurrency group "
                    "'auto-semver-bump-${{ github.repository }}-...'. "
                    "See docs/SETUP.md#concurrent-merges--bump-queue."
                )
            elif not _CANCEL_FALSE_PATTERN.search(content):
                errors.append(
                    f"{path}: concurrency must set cancel-in-progress: false "
                    "(queue merges; do not cancel in-flight bumps)."
                )

    return errors


def run_check(*, workflows_dir: Path | None = None) -> bool:
    """Print check results; return True when all checks pass."""
    errors = check_workflow_concurrency(workflows_dir=workflows_dir)

    config_path = Path("auto_semver_config.yml")
    if not config_path.exists():
        errors.append("Missing auto_semver_config.yml in repository root.")

    if errors:
        logger.info("Setup check failed with %d issue(s)", len(errors))
        print("Setup check failed:")
        for err in errors:
            print(f"  - {err}")
        return False

    logger.info("Setup check passed")
    print("Setup check passed.")
    return True
