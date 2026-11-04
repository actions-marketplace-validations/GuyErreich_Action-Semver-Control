# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for package lock sync."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from auto_semver.config import LockSyncConfig
from auto_semver.lock_sync.registry import LockStrategyRegistry
from auto_semver.lock_sync.runner import (
    CommandResult,
    LockSyncCommandError,
    run_lock_command,
)
from auto_semver.lock_sync.strategies import NpmLockStrategy, UvLockStrategy
from auto_semver.lock_sync.strategy import LockStrategy
from auto_semver.lock_sync.sync import LockSyncOrchestrator, host_binary, sync_package_locks


@pytest.mark.unit
def test_lock_sync_config_defaults() -> None:
    """Omitted lock_sync uses safe defaults."""
    config = LockSyncConfig()
    assert config.enabled is True
    assert config.ecosystems is None
    assert not hasattr(config, "on_missing")


@pytest.mark.unit
def test_lock_sync_config_rejects_unknown_ecosystem() -> None:
    """Unknown ecosystem names fail validation."""
    with pytest.raises(ValidationError, match="Unknown lock_sync ecosystems"):
        LockSyncConfig.model_validate({"ecosystems": ["cargo"]})


@pytest.mark.unit
def test_lock_sync_config_rejects_non_list_ecosystems() -> None:
    """Ecosystems must be a list when provided."""
    with pytest.raises(ValidationError, match="must be a list"):
        LockSyncConfig.model_validate({"ecosystems": "uv"})


@pytest.mark.unit
def test_sync_disabled_returns_empty(tmp_path: Path) -> None:
    """enabled=false never runs commands."""
    (tmp_path / "uv.lock").write_text("x", encoding="utf-8")
    calls: list[list[str]] = []

    def runner(argv: Sequence[str], cwd: Path) -> CommandResult:
        calls.append(list(argv))
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")

    synced = sync_package_locks(
        repo_root=tmp_path,
        config=LockSyncConfig(enabled=False),
        run_command=runner,
    )
    assert synced == []
    assert calls == []


@pytest.mark.unit
def test_sync_detects_uv_and_npm(tmp_path: Path) -> None:
    """Auto-detect runs for each lockfile present."""
    (tmp_path / "uv.lock").write_text("x", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []

    def runner(argv: Sequence[str], cwd: Path) -> CommandResult:
        calls.append(list(argv))
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")

    synced = sync_package_locks(
        repo_root=tmp_path,
        config=LockSyncConfig(),
        run_command=runner,
    )
    assert synced == ["uv.lock", "package-lock.json"]
    assert calls == [
        ["uv", "lock"],
        ["npm", "install", "--package-lock-only"],
    ]


@pytest.mark.unit
def test_sync_skips_absent_lockfile(tmp_path: Path) -> None:
    """Never invents a lockfile that is not already present."""
    calls: list[list[str]] = []

    def runner(argv: Sequence[str], cwd: Path) -> CommandResult:
        calls.append(list(argv))
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")

    synced = sync_package_locks(
        repo_root=tmp_path,
        config=LockSyncConfig(),
        run_command=runner,
    )
    assert synced == []
    assert calls == []


@pytest.mark.unit
def test_sync_allow_list_filters_ecosystems(tmp_path: Path) -> None:
    """Allow-list runs only the named strategies."""
    (tmp_path / "uv.lock").write_text("x", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []

    def runner(argv: Sequence[str], cwd: Path) -> CommandResult:
        calls.append(list(argv))
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")

    synced = sync_package_locks(
        repo_root=tmp_path,
        config=LockSyncConfig(ecosystems=["uv"]),
        run_command=runner,
    )
    assert synced == ["uv.lock"]
    assert calls == [["uv", "lock"]]


@pytest.mark.unit
def test_sync_missing_tool_patches_instead_of_skipping(tmp_path: Path) -> None:
    """A missing host CLI patches the project version instead of skipping."""
    (tmp_path / "uv.lock").write_text("x", encoding="utf-8")

    def runner(argv: Sequence[str], cwd: Path) -> CommandResult:
        return CommandResult(
            argv=tuple(argv),
            returncode=-1,
            stdout="",
            stderr="",
            missing_tool=True,
        )

    synced = sync_package_locks(
        repo_root=tmp_path,
        config=LockSyncConfig(),
        run_command=runner,
    )
    assert synced == ["uv.lock"]
    assert (tmp_path / "uv.lock").read_text(encoding="utf-8") == "x"


@pytest.mark.unit
def test_legacy_on_missing_key_is_ignored() -> None:
    """Older configs that still set on_missing keep loading."""
    config = LockSyncConfig.model_validate({"on_missing": "fail", "ecosystems": ["uv"]})
    assert config.ecosystems == ["uv"]
    assert not hasattr(config, "on_missing")


@pytest.mark.unit
def test_sync_nonzero_exit_raises(tmp_path: Path) -> None:
    """Non-zero lock command exit fails the bump (stale lock is the bug)."""
    (tmp_path / "uv.lock").write_text("x", encoding="utf-8")

    def runner(argv: Sequence[str], cwd: Path) -> CommandResult:
        return CommandResult(
            argv=tuple(argv),
            returncode=1,
            stdout="",
            stderr="lock failed",
        )

    with pytest.raises(LockSyncCommandError, match="failed with exit 1"):
        sync_package_locks(
            repo_root=tmp_path,
            config=LockSyncConfig(),
            run_command=runner,
        )


@pytest.mark.unit
def test_strategies_commands() -> None:
    """Strategies expose the runner CLI argv (no shell, no image verify step)."""
    assert UvLockStrategy().command() == ["uv", "lock"]
    assert NpmLockStrategy().command() == ["npm", "install", "--package-lock-only"]


@pytest.mark.unit
def test_registry_extension_point(tmp_path: Path) -> None:
    """A new ecosystem plugs in via subclass + register without orchestrator changes."""

    class CargoLockStrategy(LockStrategy):
        @property
        def name(self) -> str:
            return "cargo"

        @property
        def lockfile(self) -> str:
            return "Cargo.lock"

        def command(self) -> list[str]:
            return ["cargo", "generate-lockfile"]

    (tmp_path / "Cargo.lock").write_text("x", encoding="utf-8")
    registry = LockStrategyRegistry()
    registry.register(CargoLockStrategy())
    calls: list[list[str]] = []

    def runner(argv: Sequence[str], cwd: Path) -> CommandResult:
        calls.append(list(argv))
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")

    synced = LockSyncOrchestrator(registry=registry, run_command=runner).sync(
        repo_root=tmp_path,
        config=LockSyncConfig(),
    )
    assert synced == ["Cargo.lock"]
    assert calls == [["cargo", "generate-lockfile"]]
    # Config validation uses the default (builtin) registry — cargo is unknown there.
    with pytest.raises(ValidationError, match="Unknown lock_sync ecosystems"):
        LockSyncConfig.model_validate({"ecosystems": ["cargo"]})


@pytest.mark.unit
def test_run_lock_command_never_uses_shell(mocker: MockerFixture, tmp_path: Path) -> None:
    """Runner passes shell=False always."""
    completed = mocker.Mock(returncode=0, stdout="", stderr="")
    run = mocker.patch("auto_semver.lock_sync.runner.subprocess.run", return_value=completed)

    result = run_lock_command(["uv", "lock"], cwd=tmp_path)

    assert result.returncode == 0
    assert result.missing_tool is False
    run.assert_called_once()
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.args[0] == ["uv", "lock"]
    assert "UV_FROZEN" not in run.call_args.kwargs["env"]


@pytest.mark.unit
def test_run_lock_command_missing_binary(mocker: MockerFixture, tmp_path: Path) -> None:
    """FileNotFoundError is reported as missing_tool."""
    mocker.patch(
        "auto_semver.lock_sync.runner.subprocess.run",
        side_effect=FileNotFoundError("uv"),
    )
    result = run_lock_command(["uv", "lock"], cwd=tmp_path)
    assert result.missing_tool is True


@pytest.mark.unit
def test_run_lock_command_timeout_raises(mocker: MockerFixture, tmp_path: Path) -> None:
    """TimeoutExpired maps to LockSyncCommandError for structured failure handling."""
    mocker.patch(
        "auto_semver.lock_sync.runner.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["uv", "lock"], timeout=120),
    )
    with pytest.raises(LockSyncCommandError, match="timed out after 120s"):
        run_lock_command(["uv", "lock"], cwd=tmp_path)


def _write_project(tmp_path: Path, version: str = "1.8.5-dev") -> None:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "auto_semver"\nversion = "{version}"\n',
        encoding="utf-8",
    )


_UV_LOCK = """\
version = 1
revision = 2

[[package]]
name = "auto-semver"
version = "1.7.6.dev0"
source = { editable = "." }

[[package]]
name = "other"
version = "1.0.0"
"""


@pytest.mark.unit
def test_host_uv_runs_lock_and_does_not_patch(tmp_path: Path) -> None:
    """Uv on PATH runs uv lock and leaves the patcher unused."""
    _write_project(tmp_path)
    (tmp_path / "uv.lock").write_text(_UV_LOCK, encoding="utf-8")
    calls: list[list[str]] = []

    def runner(argv: Sequence[str], cwd: Path) -> CommandResult:
        calls.append(list(argv))
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")

    synced = sync_package_locks(
        repo_root=tmp_path,
        config=LockSyncConfig(ecosystems=["uv"]),
        run_command=runner,
        which=lambda tool: "/usr/bin/uv" if tool == "uv" else None,
    )
    assert synced == ["uv.lock"]
    assert calls == [["uv", "lock"]]
    assert (tmp_path / "uv.lock").read_text(encoding="utf-8") == _UV_LOCK


@pytest.mark.unit
def test_absent_uv_patches_without_spawning(tmp_path: Path) -> None:
    """Absent uv patches the project version and does not spawn uv."""
    _write_project(tmp_path)
    (tmp_path / "uv.lock").write_text(_UV_LOCK, encoding="utf-8")
    calls: list[list[str]] = []

    def runner(argv: Sequence[str], cwd: Path) -> CommandResult:
        calls.append(list(argv))
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")

    sync_package_locks(
        repo_root=tmp_path,
        config=LockSyncConfig(ecosystems=["uv"]),
        run_command=runner,
        which=lambda _tool: None,
    )
    assert calls == []
    text = (tmp_path / "uv.lock").read_text(encoding="utf-8")
    assert 'version = "1.8.5.dev0"' in text
    assert 'name = "other"' in text
    assert 'version = "1.0.0"' in text
    assert "revision = 2" in text


@pytest.mark.unit
def test_host_npm_runs_lock_and_absent_npm_does_not_spawn(tmp_path: Path) -> None:
    """Npm on PATH runs the lock install; a missing npm does not spawn npm."""
    package_lock = '{ "version": "1.7.6-dev", "lockfileVersion": 3 }\n'
    (tmp_path / "package.json").write_text('{"version": "1.8.5-dev"}\n', encoding="utf-8")
    (tmp_path / "package-lock.json").write_text(package_lock, encoding="utf-8")
    calls: list[list[str]] = []

    def runner(argv: Sequence[str], cwd: Path) -> CommandResult:
        calls.append(list(argv))
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")

    sync_package_locks(
        repo_root=tmp_path,
        config=LockSyncConfig(ecosystems=["npm"]),
        run_command=runner,
        which=lambda tool: "/usr/bin/npm" if tool == "npm" else None,
    )
    assert calls == [["npm", "install", "--package-lock-only"]]
    assert (tmp_path / "package-lock.json").read_text(encoding="utf-8") == package_lock

    calls.clear()
    sync_package_locks(
        repo_root=tmp_path,
        config=LockSyncConfig(ecosystems=["npm"]),
        run_command=runner,
        which=lambda _tool: None,
    )
    assert calls == []
    assert '"1.8.5-dev"' in (tmp_path / "package-lock.json").read_text(encoding="utf-8")


@pytest.mark.unit
def test_host_binary_uses_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lock sync uses the uv or npm already on PATH."""
    monkeypatch.setattr("auto_semver.lock_sync.sync.shutil.which", lambda tool: f"/usr/bin/{tool}")
    assert host_binary("uv") == "/usr/bin/uv"
