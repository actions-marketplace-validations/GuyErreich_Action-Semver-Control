# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Built-in lock-sync strategy implementations."""

from __future__ import annotations

from auto_semver.lock_sync.registry import default_registry
from auto_semver.lock_sync.strategies.npm import NpmLockStrategy
from auto_semver.lock_sync.strategies.uv import UvLockStrategy

# Side-effect registration: importing this package wires built-ins into the
# default registry. Add new ecosystems here the same way.
default_registry.register(UvLockStrategy())
default_registry.register(NpmLockStrategy())

__all__ = ["NpmLockStrategy", "UvLockStrategy"]
