# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Version-only lockfile patches used when the runner has no uv or npm."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from auto_semver.lock_sync.pep440 import pep503_name, to_pep440

_UV_NAME = re.compile(r'^name = "([^"]+)"\s*$')
_UV_VERSION = re.compile(r'^version = "([^"]*)"\s*$')
_NPM_VERSION = re.compile(r'("version"\s*:\s*")([^"]*)(")')


def read_static_project(repo_root: Path) -> tuple[str, str] | None:
    """Read a static ``[project]`` name and version.

    Args:
        repo_root: Repository root that may contain ``pyproject.toml``.

    Returns:
        ``(name, version)`` when both are strings. ``None`` when the file,
        the table, or either field is missing (including dynamic versions).
    """
    path = repo_root / "pyproject.toml"
    if not path.is_file():
        return None
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    name = project.get("name")
    version = project.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        return None
    return name, version


def read_package_json_version(repo_root: Path) -> str | None:
    """Read the root ``version`` string from ``package.json``.

    Args:
        repo_root: Repository root that may contain ``package.json``.

    Returns:
        The version string, or ``None`` when the file or field is absent.
    """
    path = repo_root / "package.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    if not isinstance(version, str):
        return None
    return version


def patch_uv_lock_text(text: str, *, project_name: str, version: str) -> str:
    """Replace only the root project's version in a ``uv.lock`` document.

    Other bytes, including ``revision``, hashes, and every other package, stay
    as they were. A package block with no ``version`` field is left alone.

    Args:
        text: Full ``uv.lock`` text.
        project_name: Distribution name from ``pyproject.toml``.
        version: Project version. ``-dev`` / ``-rc`` suffixes are normalized
            to PEP 440.

    Returns:
        Lock text with that one version updated, or the original text.
    """
    pep_version = to_pep440(version)
    wanted = pep503_name(project_name)
    lines = text.splitlines(keepends=True)
    rewritten: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != "[[package]]":
            rewritten.append(lines[index])
            index += 1
            continue

        block = [lines[index]]
        index += 1
        while index < len(lines) and not lines[index].startswith("[["):
            block.append(lines[index])
            index += 1

        name = _package_name(block)
        if name is not None and pep503_name(name) == wanted:
            block = _replace_own_version(block, pep_version)
        rewritten.extend(block)
    return "".join(rewritten)


def patch_npm_lock_text(text: str, *, version: str) -> str:
    """Replace root ``version`` fields in ``package-lock.json``.

    Updates the top-level ``version`` and ``packages[""].version`` when those
    keys exist. ``lockfileVersion``, dependency versions, and every other byte
    stay unchanged. When neither field exists, the text is returned as-is.

    Args:
        text: Full lockfile text.
        version: Version string copied from ``package.json`` (not PEP 440).

    Returns:
        Lock text with the root version fields updated.
    """
    updated = text
    marker = updated.find('"lockfileVersion"')
    if marker < 0:
        marker = updated.find('"packages"')
    if marker > 0:
        updated = _replace_version_in_span(updated, 0, marker, version)

    packages_at = updated.find('"packages"')
    if packages_at < 0:
        return updated
    empty = updated.find('""', packages_at)
    if empty < 0:
        return updated
    node_modules = updated.find('"node_modules/', empty)
    end = node_modules if node_modules > 0 else len(updated)
    return _replace_version_in_span(updated, empty, end, version)


def patch_uv_lockfile(repo_root: Path) -> bool:
    """Patch ``uv.lock`` from the static project version.

    Args:
        repo_root: Repository root.

    Returns:
        True when the lockfile bytes changed.
    """
    identity = read_static_project(repo_root)
    lock_path = repo_root / "uv.lock"
    if identity is None or not lock_path.is_file():
        return False
    name, version = identity
    original = lock_path.read_text(encoding="utf-8")
    updated = patch_uv_lock_text(original, project_name=name, version=version)
    if updated == original:
        return False
    lock_path.write_text(updated, encoding="utf-8")
    return True


def patch_npm_lockfile(repo_root: Path) -> bool:
    """Patch ``package-lock.json`` from ``package.json``.

    Args:
        repo_root: Repository root.

    Returns:
        True when the lockfile bytes changed.
    """
    version = read_package_json_version(repo_root)
    lock_path = repo_root / "package-lock.json"
    if version is None or not lock_path.is_file():
        return False
    original = lock_path.read_text(encoding="utf-8")
    updated = patch_npm_lock_text(original, version=version)
    if updated == original:
        return False
    lock_path.write_text(updated, encoding="utf-8")
    return True


def _package_name(block: list[str]) -> str | None:
    for line in block:
        match = _UV_NAME.match(line.rstrip("\r\n"))
        if match is not None:
            return match.group(1)
    return None


def _replace_own_version(block: list[str], version: str) -> list[str]:
    updated = list(block)
    for index, line in enumerate(updated):
        body = line.rstrip("\r\n")
        if _UV_VERSION.match(body) is None:
            continue
        newline = line[len(body) :]
        updated[index] = f'version = "{version}"{newline}'
        return updated
    return updated


def _replace_version_in_span(text: str, start: int, end: int, version: str) -> str:
    segment = text[start:end]
    match = _NPM_VERSION.search(segment)
    if match is None:
        return text
    value_start = start + match.start(2)
    value_end = start + match.end(2)
    return text[:value_start] + version + text[value_end:]
