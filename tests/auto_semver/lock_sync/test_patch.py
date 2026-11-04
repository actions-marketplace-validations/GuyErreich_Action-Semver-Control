# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Version-only lock patches stay byte-identical aside from that field."""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_semver.lock_sync.patch import patch_npm_lock_text, patch_uv_lock_text, patch_uv_lockfile

_UV_LOCK = """\
version = 1
revision = 3
requires-python = ">=3.12"

[[package]]
name = "auto-semver"
version = "1.7.6.dev0"
source = { editable = "." }
dependencies = [
    { name = "other", version = "1.0.0" },
]

[[package]]
name = "other"
version = "1.0.0"
"""


@pytest.mark.unit
def test_uv_patch_updates_normalized_version_only() -> None:
    """The matching package version changes; every other byte stays put."""
    updated = patch_uv_lock_text(_UV_LOCK, project_name="auto_semver", version="1.8.5-dev")
    expected = _UV_LOCK.replace('version = "1.7.6.dev0"', 'version = "1.8.5.dev0"', 1)
    assert updated == expected
    assert 'name = "other"\nversion = "1.0.0"' in updated
    assert '{ name = "other", version = "1.0.0" }' in updated
    assert "revision = 3" in updated


@pytest.mark.unit
def test_uv_patch_leaves_file_when_version_field_is_missing() -> None:
    """A package block with no version field is not given one."""
    original = '[[package]]\nname = "auto-semver"\nsource = { editable = "." }\n'
    assert patch_uv_lock_text(original, project_name="auto-semver", version="1.8.5-dev") == original


@pytest.mark.unit
def test_uv_patch_leaves_file_when_project_version_is_dynamic(tmp_path: Path) -> None:
    """Dynamic project versions are not invented inside the lock."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "auto-semver"\ndynamic = ["version"]\n',
        encoding="utf-8",
    )
    lock = tmp_path / "uv.lock"
    lock.write_text(_UV_LOCK, encoding="utf-8")
    assert patch_uv_lockfile(tmp_path) is False
    assert lock.read_text(encoding="utf-8") == _UV_LOCK


_NPM_LOCK = """\
{
  "name": "auto-semver",
  "version": "1.7.6-dev",
  "lockfileVersion": 3,
  "requires": true,
  "packages": {
    "": {
      "name": "auto-semver",
      "version": "1.7.6-dev",
      "dependencies": {
        "left-pad": {
          "version": "1.0.0"
        }
      }
    },
    "node_modules/left-pad": {
      "version": "1.0.0"
    }
  }
}
"""


@pytest.mark.unit
def test_npm_patch_updates_root_versions_only() -> None:
    """Root version fields change; lockfileVersion and the tree do not."""
    updated = patch_npm_lock_text(_NPM_LOCK, version="1.8.5-dev")
    expected = _NPM_LOCK.replace('"version": "1.7.6-dev"', '"version": "1.8.5-dev"')
    assert updated == expected
    assert '"lockfileVersion": 3' in updated
    assert '"node_modules/left-pad": {\n      "version": "1.0.0"' in updated
