# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registry of lock-sync strategies (open for extension)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from auto_semver.lock_sync.strategy import LockStrategy


class LockStrategyRegistry:
    """
    Named registry of ``LockStrategy`` instances.

    Adding an ecosystem is register-only: subclass ``LockStrategy``, then
    ``registry.register(MyStrategy())``. Orchestration and config validation
    read from the registry and do not hard-code ecosystem lists.
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._by_name: dict[str, LockStrategy] = {}

    def register(self, strategy: LockStrategy) -> None:
        """Register or replace a strategy under ``strategy.name``."""
        self._by_name[strategy.name] = strategy

    def get(self, name: str) -> LockStrategy | None:
        """Return the strategy for ``name``, or None if unregistered."""
        return self._by_name.get(name)

    def names(self) -> frozenset[str]:
        """Return the set of registered ecosystem names."""
        return frozenset(self._by_name)

    def all(self) -> list[LockStrategy]:
        """Return strategies in registration order."""
        return list(self._by_name.values())

    def resolve(self, ecosystems: Iterable[str] | None = None) -> list[LockStrategy]:
        """
        Resolve strategies to run.

        Args:
            ecosystems: Allow-list of names. ``None`` means every registered strategy.

        Returns:
            Strategies in registration order, filtered by the allow-list when set.
        """
        if ecosystems is None:
            return self.all()
        allow = set(ecosystems)
        return [s for s in self.all() if s.name in allow]

    def __iter__(self) -> Iterator[LockStrategy]:
        """Iterate registered strategies in registration order."""
        return iter(self._by_name.values())

    def __len__(self) -> int:
        """Return the number of registered strategies."""
        return len(self._by_name)


# Process-wide default; builtins register via ``ensure_builtins_registered``.
default_registry = LockStrategyRegistry()


def ensure_builtins_registered() -> None:
    """
    Lazily register built-in strategies on the default registry.

    Safe to call repeatedly (import is cached). Config validation uses this so
    ``Config()`` does not import strategy modules until ecosystems are checked
    or lock sync is actually used.
    """
    import auto_semver.lock_sync.strategies as _lock_sync_strategies  # noqa: F401, PLC0415
