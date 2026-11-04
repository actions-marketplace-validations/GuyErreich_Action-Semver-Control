# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Orchestrate package lock sync after version-file rewrites."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path

from auto_semver.config import LockSyncConfig
from auto_semver.lock_sync.registry import LockStrategyRegistry, default_registry
from auto_semver.lock_sync.runner import (
    CommandResult,
    LockCommandRunner,
    LockSyncCommandError,
)
from auto_semver.lock_sync.strategy import LockStrategy

logger = logging.getLogger(__name__)

RunCommand = Callable[[Sequence[str], Path], CommandResult]
WhichTool = Callable[[str], str | None]

def host_binary(tool: str) -> str | None:
    """Return a lock CLI on PATH.

    The action installs its own uv and does not put that binary on ``PATH``.
    This lookup is the ``uv`` or ``npm`` already installed for the repository.

    Args:
        tool: Executable name (``uv``, ``npm``).

    Returns:
        The PATH hit, or ``None`` when the tool is absent.
    """
    return shutil.which(tool)


class LockSyncOrchestrator:
    """
    Runs registered lock strategies for a repo after version-file rewrites.

    Depends on a ``LockStrategyRegistry`` and a command runner so tests and
    future ecosystems plug in without changing this class.
    """

    def __init__(
        self,
        *,
        registry: LockStrategyRegistry | None = None,
        runner: LockCommandRunner | None = None,
        run_command: RunCommand | None = None,
    ) -> None:
        """
        Create an orchestrator.

        Args:
            registry: Strategy source (defaults to the process default registry).
            runner: Preferred command runner.
            run_command: Legacy injectable callable (tests); overrides ``runner`` when set.
        """
        self._registry = registry if registry is not None else default_registry
        self._runner = runner if runner is not None else LockCommandRunner()
        self._run_command = run_command

    def sync(
        self,
        *,
        repo_root: Path,
        config: LockSyncConfig,
        which: WhichTool | None = None,
    ) -> list[str]:
        """
        Sync known package lockfiles that already exist at the repo root.

        Uses the host CLI when ``which`` (or :func:`host_binary`) finds it.
        Otherwise patches only the project version. Never runs ``uv lock
        --check``. A non-zero CLI exit still fails the bump. A missing CLI
        does not.
        """
        if not config.enabled:
            logger.debug("lock_sync.enabled is false — skipping package lock sync")
            return []

        strategies = self._registry.resolve(config.ecosystems)
        synced: list[str] = []

        for strategy in strategies:
            if not strategy.detect(repo_root):
                logger.debug(
                    "Skipping ecosystem %s — lockfile %s not found",
                    strategy.name,
                    strategy.lockfile,
                )
                continue

            if self._use_cli(strategy, which):
                argv = strategy.command()
                result = self._execute(argv, repo_root)
                if result.missing_tool:
                    logger.info(
                        "Host %s not found; patching the project version in %s",
                        strategy.tool,
                        strategy.lockfile,
                    )
                    strategy.patch(repo_root)
                elif result.returncode != 0:
                    detail = (result.stderr or result.stdout or "").strip()
                    raise LockSyncCommandError(
                        f"lock_sync: {' '.join(argv)} failed with exit {result.returncode}"
                        + (f": {detail}" if detail else "")
                    )
                else:
                    logger.info("Synced %s via host %s", strategy.lockfile, strategy.tool)
            else:
                logger.info(
                    "No host %s; patching the project version in %s",
                    strategy.tool,
                    strategy.lockfile,
                )
                strategy.patch(repo_root)

            synced.append(strategy.lockfile)

        return synced

    def _use_cli(self, strategy: LockStrategy, which: WhichTool | None) -> bool:
        """True when this ecosystem's CLI should run instead of the patcher."""
        if which is not None:
            return which(strategy.tool) is not None
        if self._run_command is not None:
            # An injected runner is the test (or caller) simulating a host CLI.
            return True
        return host_binary(strategy.tool) is not None

    def _execute(self, argv: Sequence[str], repo_root: Path) -> CommandResult:
        if self._run_command is not None:
            return self._run_command(argv, repo_root)
        return self._runner.run(argv, cwd=repo_root)


def _registry_for(
    strategies: Sequence[LockStrategy] | None,
    registry: LockStrategyRegistry | None,
) -> LockStrategyRegistry | None:
    if strategies is None:
        return registry
    temp = LockStrategyRegistry()
    for strategy in strategies:
        temp.register(strategy)
    return temp


def sync_package_locks(
    *,
    repo_root: Path,
    config: LockSyncConfig,
    strategies: Sequence[LockStrategy] | None = None,
    run_command: RunCommand | None = None,
    registry: LockStrategyRegistry | None = None,
    which: WhichTool | None = None,
) -> list[str]:
    """
    Sync package locks using the default orchestrator.

    ``strategies`` remains supported for tests: when provided, a temporary
    registry containing only those strategies is used. ``which`` selects the
    host CLI; when omitted, an injected ``run_command`` is treated as that CLI
    being present.
    """
    return LockSyncOrchestrator(
        registry=_registry_for(strategies, registry),
        run_command=run_command,
    ).sync(repo_root=repo_root, config=config, which=which)
