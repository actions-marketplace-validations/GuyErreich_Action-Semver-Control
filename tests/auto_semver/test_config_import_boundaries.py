# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Guard Config entry-point import boundaries (see AGENT.md)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from auto_semver import config as config_pkg

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "auto_semver"
_TESTS_ROOT = _REPO_ROOT / "tests"

_MODELS_PREFIX = "auto_semver.config._models"

_REQUIRED_EXPORTS = frozenset(
    {
        "Config",
        "ConfigData",
        "Commit",
        "CommitGroup",
        "CommitGroupConfig",
        "CommitGroups",
        "CommitGroupsConfig",
        "BumpConfig",
        "ChangelogConfig",
        "ChangelogTemplateVars",
        "PromotionRule",
        "PullRequestConfig",
        "PullRequestTemplateVars",
        "ReleaseConfig",
        "BranchName",
        "RegexPattern",
    }
)


def _is_under_config_package(path: Path) -> bool:
    try:
        path.relative_to(_SRC_ROOT / "config")
        return True
    except ValueError:
        return False


def _models_imports(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(
            _MODELS_PREFIX
        ):
            found.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(_MODELS_PREFIX):
                    found.append(alias.name)
    return found


def _iter_py_outside_config() -> list[Path]:
    paths: list[Path] = []
    for root in (_SRC_ROOT, _TESTS_ROOT):
        for path in root.rglob("*.py"):
            if _is_under_config_package(path):
                continue
            paths.append(path)
    return sorted(paths)


@pytest.mark.unit
def test_config_package_exports_schema_types() -> None:
    """``config.__init__`` must expose Config and schema types at the top level."""
    exported = set(config_pkg.__all__)
    missing = sorted(_REQUIRED_EXPORTS - exported)
    assert missing == [], f"Missing config package exports: {missing}"
    for name in _REQUIRED_EXPORTS:
        assert hasattr(config_pkg, name), f"config package missing attribute {name}"


@pytest.mark.unit
def test_nobody_imports_config_models_outside_config_package() -> None:
    """No src/ or tests/ file outside ``config/`` may import ``config._models``."""
    violations: list[str] = []

    for path in _iter_py_outside_config():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = _models_imports(tree)
        if found:
            rel = path.relative_to(_REPO_ROOT).as_posix()
            violations.append(f"{rel}: {sorted(set(found))}")

    assert violations == [], (
        "Import schema types from auto_semver.config — never config._models:\n"
        + "\n".join(violations)
    )
