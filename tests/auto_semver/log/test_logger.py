# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Unit tests for auto_semver.log."""

from __future__ import annotations

import logging
import re
from collections.abc import Generator
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from rich.console import Console

from auto_semver.log.github import GitHubActionsHandler, attach_github_adapter, is_github_actions
from auto_semver.log.handler import FileLogHandler, LogViewHandler
from auto_semver.log.setup import get_summary, record_factory, resolve_log_file, setup_logger
from auto_semver.log.summary import JobSummary
from auto_semver.log.view import LiveView, LogEvent, get_view, log_group, set_view, status


class TestRecordFactory:
    """Tests for the custom log record factory."""

    @pytest.fixture
    def reset_logging_factory(self) -> Generator[None, None, None]:
        """Reset the logging record factory after each test."""
        original_factory = logging.getLogRecordFactory()
        yield
        logging.setLogRecordFactory(original_factory)

    @pytest.mark.unit
    def test_record_factory_adds_qualname(self, reset_logging_factory: None) -> None:
        """record_factory adds qualname and full_name attributes."""
        record_args = [
            "test_logger",
            logging.INFO,
            "file.py",
            10,
            "Test message",
            (),
            None,
        ]
        record = record_factory(*record_args)
        assert hasattr(record, "qualname")
        assert hasattr(record, "full_name")
        assert record.full_name == f"[{record.name}.{record.module}][{record.funcName}]"


class TestSetupLogger:
    """Tests for setup_logger configuration."""

    @pytest.mark.unit
    def test_setup_logger_attaches_view_and_file(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """setup_logger attaches LogViewHandler and FileLogHandler."""
        mocker.patch.object(LiveView, "start")
        log_path = tmp_path / "test.log"
        logger = setup_logger(debug=True, log_file=log_path, start_live=False)

        assert logger.level == logging.DEBUG
        handler_types = {type(h) for h in logger.handlers}
        assert LogViewHandler in handler_types
        assert FileLogHandler in handler_types
        # Live did not start → stdout StreamHandler for Actions / non-TTY.
        assert logging.StreamHandler in handler_types
        assert get_view() is not None

    @pytest.mark.unit
    def test_setup_logger_info_mode(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Non-debug setup uses INFO level."""
        mocker.patch.object(LiveView, "start")
        logger = setup_logger(debug=False, log_file=tmp_path / "info.log", start_live=False)
        assert logger.level == logging.INFO

    @pytest.mark.unit
    def test_setup_logger_skips_stream_when_live_running(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """TTY Live dashboard must not also flood stdout with StreamHandler."""

        def _fake_start(self: LiveView) -> None:
            self._live = mocker.MagicMock()

        mocker.patch.object(LiveView, "start", _fake_start)
        logger = setup_logger(debug=False, log_file=tmp_path / "live.log", start_live=True)
        handler_types = {type(h) for h in logger.handlers}
        assert LogViewHandler in handler_types
        assert FileLogHandler in handler_types
        assert logging.StreamHandler not in handler_types

    @pytest.mark.unit
    def test_resolve_log_file_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """AUTO_SEMVER_LOG_FILE overrides the default path."""
        target = tmp_path / "custom.log"
        monkeypatch.setenv("AUTO_SEMVER_LOG_FILE", str(target))
        assert resolve_log_file() == target

    @pytest.mark.unit
    def test_stream_handler_emits_inside_groups(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Non-TTY setup prints plain INFO lines to stdout between group markers."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        mocker.patch.object(LiveView, "start")
        setup_logger(debug=True, log_file=tmp_path / "gha.log", start_live=False)
        view = get_view()
        assert view is not None
        attach_github_adapter(view)

        with log_group("Tag"):
            logging.getLogger("auto_semver").info("Tagging branch")
            logging.getLogger("auto_semver").debug("hidden from stdout")

        out = capsys.readouterr().out
        assert "::group::Tag" in out
        assert "Tagging branch" in out
        assert "hidden from stdout" not in out
        # Operator stream is message-only (no level/qualname prefix).
        assert " | " not in out.split("Tagging branch")[0].splitlines()[-1]
        assert "::endgroup::" in out
        assert out.index("::group::Tag") < out.index("Tagging branch") < out.index("::endgroup::")

    @pytest.mark.unit
    def test_stream_stays_info_when_debug_enabled(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """--debug raises file level but Actions stdout stays INFO."""
        mocker.patch.object(LiveView, "start")
        logger = setup_logger(debug=True, log_file=tmp_path / "dbg.log", start_live=False)
        streams = [h for h in logger.handlers if type(h) is logging.StreamHandler]
        assert len(streams) == 1
        assert streams[0].level == logging.INFO
        files = [h for h in logger.handlers if isinstance(h, FileLogHandler)]
        assert files[0].level == logging.DEBUG

    @pytest.mark.unit
    def test_warning_emits_annotation_only_once(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """In Actions, a WARNING is one ::warning:: line — not also a plain log."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        mocker.patch.object(LiveView, "start")
        setup_logger(debug=False, log_file=tmp_path / "warn.log", start_live=False)
        view = get_view()
        assert view is not None
        attach_github_adapter(view)

        logging.getLogger("auto_semver").warning("branch already deleted")

        out = capsys.readouterr().out
        matching = [line for line in out.splitlines() if "branch already deleted" in line]
        assert len(matching) == 1
        assert matching[0].startswith("::warning::")


class TestLogViewHandler:
    """Tests for LiveView event routing."""

    @pytest.mark.unit
    def test_emit_adds_event_without_stream(self, mocker: MockerFixture) -> None:
        """LogViewHandler updates LiveView and does not write to a stream."""
        console = Console(force_terminal=False, width=80, height=24)
        view = LiveView(console=console, debug=False)
        handler = LogViewHandler(view)
        handler.setLevel(logging.INFO)

        record = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname="x.py",
            lineno=1,
            msg="hello view",
            args=(),
            exc_info=None,
        )
        record.__dict__["qualname"] = "SampleClass.sample_method"
        handler.emit(record)
        assert any(e.message == "hello view" for e in view._events)
        assert any(e.qualname == "SampleClass.sample_method" for e in view._events)

    @pytest.mark.unit
    def test_emit_falls_back_to_func_name(self) -> None:
        """Without qualname attribute, handler uses record.funcName."""
        console = Console(force_terminal=False, width=80, height=24)
        view = LiveView(console=console, debug=False)
        handler = LogViewHandler(view)
        record = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname="x.py",
            lineno=1,
            msg="fallback",
            args=(),
            exc_info=None,
            func="my_func",
        )
        handler.emit(record)
        assert view._events[0].qualname == "my_func"

    @pytest.mark.unit
    def test_event_buffer_drops_oldest(self) -> None:
        """Bounded event buffer drops oldest entries when over max."""
        console = Console(force_terminal=False, width=80, height=24)
        view = LiveView(console=console, max_events=3)
        for i in range(5):
            view.add_event(LogEvent(level=logging.INFO, message=f"m{i}", created=float(i)))
        assert len(view._events) == 3
        assert view._events[0].message == "m2"


class TestLiveViewRender:
    """Tests for dashboard width and title rules."""

    @pytest.mark.unit
    @pytest.mark.parametrize("width", [40, 80, 120])
    def test_render_lines_share_width(self, width: int) -> None:
        """Every ANSI-stripped line has the same cell width at common sizes."""
        console = Console(force_terminal=True, force_interactive=False, width=width, height=30)
        summary = JobSummary()
        summary.set("version", "1.0.0 -> 1.1.0")
        summary.set("branches", "feature/x -> main")
        summary.set("pr", "pending")
        view = LiveView(console=console, summary=summary, command="bump")
        view.set_phase("Resolve version")
        view.set_status("Fetching baseline...")
        view.add_event(LogEvent(level=logging.INFO, message="ok", created=1.0))
        view.add_event(
            LogEvent(
                level=logging.ERROR,
                message="Target branch foo is not in suffixes",
                created=2.0,
            )
        )

        with console.capture() as capture:
            console.print(view.render())
        plain = capture.get()
        # Strip ANSI
        plain = re.sub(r"\x1b\[[0-9;]*m", "", plain)
        lines = [line for line in plain.splitlines() if line.strip()]
        assert lines
        lengths = {len(line) for line in lines}
        assert len(lengths) == 1, f"Uneven widths {lengths} at console width {width}"
        # Outer title is short product/command only — phase stays inside status card
        assert view.command == "bump"
        assert "Resolve" not in f"auto-semver  {view.command}"

    @pytest.mark.unit
    def test_log_card_includes_qualname(self) -> None:
        """Live log card renders Class.method before the message."""
        console = Console(force_terminal=True, force_interactive=False, width=80, height=30)
        view = LiveView(console=console, command="bump")
        view.add_event(
            LogEvent(
                level=logging.INFO,
                message="Adding files",
                created=1.0,
                qualname="GitOps.commit",
            )
        )
        with console.capture() as capture:
            console.print(view.render())
        plain = re.sub(r"\x1b\[[0-9;]*m", "", capture.get())
        assert "GitOps.commit" in plain
        assert "Adding files" in plain

    @pytest.mark.unit
    def test_status_context_toggles_spinner(self) -> None:
        """status() context manager toggles the spinning flag."""
        console = Console(force_terminal=False, width=80, height=24)
        view = LiveView(console=console)
        set_view(view)
        assert view._spinning is False
        with status("Working..."):
            active = get_view()
            assert active is view
            assert active._spinning is True
            assert active._status == "Working..."
        assert view._spinning is False
        set_view(None)

    @pytest.mark.unit
    def test_stop_persists_full_dashboard(self, mocker: MockerFixture) -> None:
        """stop() reprints the full dashboard so logs remain after Live exits."""
        console = Console(force_terminal=True, force_interactive=False, width=80, height=30)
        view = LiveView(console=console, command="bump")
        view.set_phase("Finalize")
        view.set_status("Would push branch...")
        view.add_event(
            LogEvent(
                level=logging.INFO,
                message="Dry-run complete",
                created=1.0,
                qualname="main",
            )
        )
        fake_live = mocker.MagicMock()
        view._live = fake_live
        printed: list[object] = []
        mocker.patch.object(console, "print", side_effect=lambda r: printed.append(r))

        view.stop()

        fake_live.stop.assert_called_once()
        fake_live.update.assert_called_once()
        assert view._live is None
        assert view._persisted_dashboard is True
        assert view._spinning is False
        assert len(printed) == 1
        assert view._status.startswith("Done")
        assert any(e.message == "Dry-run complete" for e in view._events)

    @pytest.mark.unit
    def test_flush_summary_skips_panel_when_dashboard_persisted(
        self, mocker: MockerFixture
    ) -> None:
        """flush_summary does not replace the dashboard with a summary-only panel."""
        console = Console(force_terminal=False, width=80, height=24)
        view = LiveView(console=console)
        view._persisted_dashboard = True
        print_mock = mocker.patch.object(console, "print")
        view.flush_summary()
        print_mock.assert_not_called()

    @pytest.mark.unit
    def test_flush_summary_prints_when_live_never_started(
        self, mocker: MockerFixture
    ) -> None:
        """Non-TTY runs still get the summary panel."""
        console = Console(force_terminal=False, width=80, height=24)
        view = LiveView(console=console)
        print_mock = mocker.patch.object(console, "print")
        view.flush_summary()
        print_mock.assert_called_once()


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


class TestGitHubActions:
    """Tests for the optional GitHub Actions adapter."""

    @pytest.mark.unit
    def test_handler_emits_warning_and_error(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GitHubActionsHandler emits escaped workflow commands."""
        written: list[str] = []

        class FakeStdout:
            def write(self, data: str) -> int:
                written.append(data)
                return len(data)

            def flush(self) -> None:
                return None

        mocker.patch("auto_semver.log.github.sys.stdout", FakeStdout())
        handler = GitHubActionsHandler()
        handler.emit(logging.LogRecord("t", logging.WARNING, "x.py", 1, "warn\nline", (), None))
        handler.emit(logging.LogRecord("t", logging.ERROR, "x.py", 1, "boom%1", (), None))
        assert any("::warning::" in line and "%0A" in line for line in written)
        assert any("::error::" in line and "%25" in line for line in written)

    @pytest.mark.unit
    def test_is_github_actions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """is_github_actions reflects the GITHUB_ACTIONS env var."""
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert is_github_actions() is False
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert is_github_actions() is True

    @pytest.mark.unit
    def test_attach_writes_step_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Adapter on_summary appends markdown to GITHUB_STEP_SUMMARY."""
        summary_path = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
        mocker.patch.object(LiveView, "start")
        setup_logger(debug=False, log_file=tmp_path / "a.log", start_live=False)
        view = get_view()
        assert view is not None
        attach_github_adapter(view)
        with log_group("Resolve version"):
            pass
        get_summary().set("version", "1.0.0")
        view.flush_summary()
        content = summary_path.read_text(encoding="utf-8")
        assert "auto-semver" in content
        assert "1.0.0" in content


class TestJobSummary:
    """Tests for JobSummary rendering."""

    @pytest.mark.unit
    def test_as_markdown(self) -> None:
        """as_markdown produces a GFM table."""
        summary = JobSummary()
        summary.set("command", "bump")
        md = summary.as_markdown()
        assert "| **command** | bump |" in md
