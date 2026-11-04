# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Python / uv lock sync strategy."""

from __future__ import annotations

from pathlib import Path

from auto_semver.lock_sync.strategy import LockStrategy


class UvLockStrategy(LockStrategy):
    """Refresh ``uv.lock`` with the runner's ``uv lock``, or patch the version."""

    @property
    def name(self) -> str:
        """Ecosystem id."""
        return "uv"

    @property
    def lockfile(self) -> str:
        """Lockfile path relative to the repo root."""
        return "uv.lock"

    def command(self) -> list[str]:
        """Return ``uv lock`` for the runner's uv, never the image uv."""
        return ["uv", "lock"]

    def patch(self, repo_root: Path) -> bool:
        """Replace only the project version in ``uv.lock``.

        Args:
            repo_root: Repository root.

        Returns:
            True when the lockfile bytes changed.
        """
        from auto_semver.lock_sync.patch import patch_uv_lockfile  # noqa: PLC0415

        return patch_uv_lockfile(repo_root)
