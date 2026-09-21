# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Unit tests for runview.file_sink and install wiring."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from runview.bridge import ReporterHandler
from runview.config import Config
from runview.file_sink import FileLogHandler
from runview.renderers.github import GitHubRenderer
from runview.renderers.plain import PlainRenderer
from runview.renderers.rich_live import RichRenderer
from runview.reporter import install, resolve_log_file


class TestFileLogHandler:
    """Tests for plain-text forensic file logging."""

    @pytest.mark.unit
    def test_file_log_contains_location(self, tmp_path: Path) -> None:
        """FileLogHandler writes filename, lineno, and qualname without ANSI."""
        path = tmp_path / "forensic.log"
        root = logging.getLogger("file_log_test")
        root.handlers.clear()
        root.setLevel(logging.INFO)
        handler = FileLogHandler(path)
        root.addHandler(handler)

        def sample_caller() -> None:
            root.info("forensic line")

        sample_caller()
        handler.close()
        root.removeHandler(handler)

        text = path.read_text(encoding="utf-8")
        assert "\x1b[" not in text
        assert "forensic line" in text
        assert "INFO" in text
        assert "sample_caller" in text or "qualname" in text or ".py:" in text


class TestInstall:
    """Tests for install() handler wiring."""

    @pytest.mark.unit
    def test_install_attaches_exactly_two_handlers(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """Install attaches ReporterHandler and FileLogHandler only."""
        mocker.patch.object(RichRenderer, "open")
        mocker.patch.object(PlainRenderer, "open")
        mocker.patch.object(GitHubRenderer, "open")
        logger = install(
            Config(
                app_name="test",
                default_log_file=str(tmp_path / "test.log"),
                style="plain",
                debug=True,
            )
        )
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        handler_types = {type(h) for h in root.handlers}
        assert handler_types == {ReporterHandler, FileLogHandler}
        assert logger is not None

    @pytest.mark.unit
    def test_install_info_mode(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Non-debug install uses INFO level."""
        mocker.patch.object(PlainRenderer, "open")
        install(
            Config(
                app_name="test",
                default_log_file=str(tmp_path / "info.log"),
                style="plain",
                debug=False,
            )
        )
        assert logging.getLogger().level == logging.INFO

    @pytest.mark.unit
    def test_resolve_log_file_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """log_file_env overrides the default path."""
        target = tmp_path / "custom.log"
        monkeypatch.setenv("AUTO_SEMVER_LOG_FILE", str(target))
        config = Config(
            app_name="test",
            log_file_env="AUTO_SEMVER_LOG_FILE",
            default_log_file="auto-semver.log",
        )
        assert resolve_log_file(config) == target

    @pytest.mark.unit
    def test_auto_selects_github(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """style=auto selects GitHubRenderer when GITHUB_ACTIONS=true."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        mocker.patch.object(GitHubRenderer, "open")
        reporter = install(
            Config(
                app_name="test",
                default_log_file=str(tmp_path / "gha.log"),
                style="auto",
            )
        )
        assert isinstance(reporter.renderer, GitHubRenderer)

    @pytest.mark.unit
    def test_file_stays_debug_when_debug_enabled(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """--debug raises file and reporter handler levels to DEBUG."""
        mocker.patch.object(PlainRenderer, "open")
        install(
            Config(
                app_name="test",
                default_log_file=str(tmp_path / "dbg.log"),
                style="plain",
                debug=True,
            )
        )
        root = logging.getLogger()
        files = [h for h in root.handlers if isinstance(h, FileLogHandler)]
        assert files[0].level == logging.DEBUG
