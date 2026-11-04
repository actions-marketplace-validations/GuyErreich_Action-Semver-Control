# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Node / npm lock sync strategy."""

from __future__ import annotations

from pathlib import Path

from auto_semver.lock_sync.strategy import LockStrategy


class NpmLockStrategy(LockStrategy):
    """Refresh ``package-lock.json`` with the runner's npm, or patch the version."""

    @property
    def name(self) -> str:
        """Ecosystem id."""
        return "npm"

    @property
    def lockfile(self) -> str:
        """Lockfile path relative to the repo root."""
        return "package-lock.json"

    def command(self) -> list[str]:
        """Return ``npm install --package-lock-only`` for the runner's npm."""
        return ["npm", "install", "--package-lock-only"]

    def patch(self, repo_root: Path) -> bool:
        """Replace only the root version fields in ``package-lock.json``.

        Args:
            repo_root: Repository root.

        Returns:
            True when the lockfile bytes changed.
        """
        from auto_semver.lock_sync.patch import patch_npm_lockfile  # noqa: PLC0415

        return patch_npm_lockfile(repo_root)
