"""Tests for promotion metadata helpers."""

from pathlib import Path

import pytest

from auto_semver.cli.utils import apply_promotion_metadata
from auto_semver.config import Config
from auto_semver.core.semver import SemverLock

_BASE_CONFIG = """
start_version: "0.1.0"
suffixes:
  dev: "-dev"
  staging: "-rc"
  master: ""
promotions:
  - from_branch: dev
    to_branch: staging
    auto_promote: true
  - from_branch: staging
    to_branch: master
    auto_promote: false
version_files:
  - "version.txt"
changelog:
  file: "CHANGELOG.md"
  truncate: true
  template: "## [{{version}}]\\n"
commit_groups:
  - title: "Changes"
    patterns: ["^feat:"]
    priority: 1
pull_request:
  title: "Release {{version}}"
  body: "Release"
  labels: ["release"]
"""


def _setup_promotion_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.chdir(tmp_path)

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [1.4.6-dev] - 30-08-2026\n\n### Changes\n- Example\n",
        encoding="utf-8",
    )
    version_file = tmp_path / "version.txt"
    version_file.write_text("1.4.6-dev\n", encoding="utf-8")
    (tmp_path / ".semver.lock").write_text(
        "version: 1.4.6-dev\nsource_branch: dev\ntarget_branch: dev\nfinalized: false\n",
        encoding="utf-8",
    )
    (tmp_path / "auto_semver_config.yml").write_text(_BASE_CONFIG, encoding="utf-8")
    return Config()


@pytest.mark.unit
def test_apply_promotion_metadata_updates_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Promotion should rewrite changelog, version files, and lock for the target channel."""
    config = _setup_promotion_fixture(tmp_path, monkeypatch)
    changelog = tmp_path / "CHANGELOG.md"
    version_file = tmp_path / "version.txt"

    apply_promotion_metadata(
        config=config,
        source_branch="dev",
        source_version="1.4.6-dev",
        target_version="1.4.6-rc",
        target_branch="staging",
        merge_sha="abc123",
    )

    assert "[1.4.6-rc]" in changelog.read_text(encoding="utf-8")
    assert version_file.read_text(encoding="utf-8").strip() == "1.4.6-rc"

    lock = SemverLock.load_from_file()
    assert str(lock.version) == "1.4.6-rc"
    assert lock.source_branch == "dev"
    assert lock.target_branch == "staging"
    assert lock.source_branch != lock.target_branch
    assert lock.finalized is True
    assert lock.branch_role is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source_branch", "target_branch", "source_version", "target_version"),
    [
        ("dev", "staging", "1.4.6-dev", "1.4.6-rc"),
        ("staging", "master", "1.4.6-rc", "1.4.6"),
    ],
)
def test_apply_promotion_metadata_lock_matches_config_promotion_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_branch: str,
    target_branch: str,
    source_version: str,
    target_version: str,
) -> None:
    """Lock source/target must mirror promotions[].from_branch and to_branch from config."""
    config = _setup_promotion_fixture(tmp_path, monkeypatch)

    apply_promotion_metadata(
        config=config,
        source_branch=source_branch,
        source_version=source_version,
        target_version=target_version,
        target_branch=target_branch,
        merge_sha="abc123",
    )

    lock = SemverLock.load_from_file()
    assert lock.source_branch == source_branch
    assert lock.target_branch == target_branch
    assert str(lock.version) == target_version
