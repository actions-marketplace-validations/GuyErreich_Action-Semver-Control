# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Guard that every package ``__all__`` name is actually defined."""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

import pytest

import auto_semver


def _iter_package_modules(package: ModuleType) -> list[ModuleType]:
    modules = [package]
    if not hasattr(package, "__path__"):
        return modules
    prefix = package.__name__ + "."
    for module_info in pkgutil.walk_packages(package.__path__, prefix):
        try:
            modules.append(importlib.import_module(module_info.name))
        except Exception as exc:  # pragma: no cover - defensive
            pytest.fail(f"Failed to import {module_info.name}: {exc}")
    return modules


@pytest.mark.unit
def test_all_package_all_exports_exist() -> None:
    """Every name listed in any package ``__all__`` must be getattr-able."""
    missing: list[str] = []
    for module in _iter_package_modules(auto_semver):
        names = getattr(module, "__all__", None)
        if names is None:
            continue
        for name in names:
            if not hasattr(module, name):
                missing.append(f"{module.__name__}.{name}")
    assert missing == [], f"Phantom __all__ exports: {missing}"
