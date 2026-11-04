# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Subprocess runner for official package-manager lock commands."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a lock sync command."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    missing_tool: bool = False


class LockSyncCommandError(RuntimeError):
    """Raised when a lock sync command exits non-zero."""


class LockCommandRunner:
    """Runs lock CLI argv lists without a shell (injectable for tests)."""

    def __init__(self, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        """Create a runner with a process timeout in seconds."""
        self._timeout = timeout

    def run(self, argv: Sequence[str], *, cwd: Path) -> CommandResult:
        """
        Run a lock sync command without a shell.

        Args:
            argv: Exact command argv (never passed through a shell).
            cwd: Working directory (repo root).

        Returns:
            CommandResult with stdout/stderr and return code.
            ``missing_tool`` is True when the executable is not found.
        """
        argv_list = list(argv)
        logger.info("Running lock sync: %s (cwd=%s)", " ".join(argv_list), cwd)
        env = os.environ.copy()
        # A frozen uv exits 0 without writing. The runner's uv must be allowed to write.
        env.pop("UV_FROZEN", None)
        try:
            completed = subprocess.run(
                argv_list,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
                shell=False,
                env=env,
            )
        except FileNotFoundError:
            logger.warning("Lock sync tool not found: %s", argv_list[0] if argv_list else argv)
            return CommandResult(
                argv=tuple(argv_list),
                returncode=-1,
                stdout="",
                stderr="",
                missing_tool=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise LockSyncCommandError(
                f"lock_sync: {' '.join(argv_list)} timed out after {self._timeout}s"
            ) from exc

        return CommandResult(
            argv=tuple(argv_list),
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            missing_tool=False,
        )


def run_lock_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> CommandResult:
    """Module-level helper that delegates to ``LockCommandRunner``."""
    return LockCommandRunner(timeout=timeout).run(argv, cwd=cwd)
