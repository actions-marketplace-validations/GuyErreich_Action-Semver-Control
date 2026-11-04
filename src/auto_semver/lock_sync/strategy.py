# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Abstract lock-sync strategy (Strategy pattern)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class LockStrategy(ABC):
    """
    One package-manager ecosystem's lockfile sync behavior.

    To add a new ecosystem:
    1. Subclass ``LockStrategy`` with ``name``, ``lockfile``, and ``command()``.
    2. Register an instance on the default registry (see ``strategies`` package).
    3. Config ``ecosystems`` allow-list accepts the new ``name`` automatically.

    ``command()`` is the runner's official CLI. The action image must not
    execute it. When that binary is absent, ``patch()`` updates only the
    project version.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable ecosystem id used in config (e.g. ``uv``, ``npm``)."""

    @property
    @abstractmethod
    def lockfile(self) -> str:
        """Repo-root relative lockfile path that must already exist."""

    @property
    def tool(self) -> str:
        """Executable name looked up on the runner PATH (defaults to ``name``)."""
        return self.name

    @abstractmethod
    def command(self) -> list[str]:
        """Bounded argv for the runner's lock CLI (never shell-interpolated)."""

    def patch(self, repo_root: Path) -> bool:
        """Update only the project version when the runner has no lock CLI.

        Args:
            repo_root: Repository root containing the lockfile.

        Returns:
            True when the lockfile bytes changed. The default leaves the file.
        """
        del repo_root
        return False

    def detect(self, repo_root: Path) -> bool:
        """Return True when this ecosystem's lockfile exists at the repo root."""
        return (repo_root / self.lockfile).is_file()
