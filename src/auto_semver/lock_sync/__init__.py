# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sync language package lockfiles after version bumps."""

from __future__ import annotations

from typing import Any

# Register built-ins on package import for sync callers. Config validation uses
# ``ensure_builtins_registered`` lazily instead of importing strategies at Config load.
from auto_semver.lock_sync.registry import (
    LockStrategyRegistry,
    default_registry,
    ensure_builtins_registered,
)
from auto_semver.lock_sync.strategy import LockStrategy

ensure_builtins_registered()

__all__ = [
    "LockStrategy",
    "LockStrategyRegistry",
    "LockSyncOrchestrator",
    "default_registry",
    "sync_package_locks",
]


def __getattr__(name: str) -> Any:
    """Lazy-load orchestrator exports to avoid import cycles with config."""
    if name == "sync_package_locks":
        from auto_semver.lock_sync.sync import sync_package_locks  # noqa: PLC0415

        return sync_package_locks
    if name == "LockSyncOrchestrator":
        from auto_semver.lock_sync.sync import LockSyncOrchestrator  # noqa: PLC0415

        return LockSyncOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
