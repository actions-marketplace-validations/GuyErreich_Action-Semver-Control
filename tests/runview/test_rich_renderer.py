# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Unit tests for RichRenderer dashboard behavior."""

from __future__ import annotations

import logging
import re

import pytest
from pytest_mock import MockerFixture
from rich.console import Console

from runview import log_group, status
from runview.config import Config
from runview.renderers.rich_live import RichRenderer
from runview.reporter import Reporter, _ReporterState
from runview.summary import RunSummary


@pytest.fixture
def rich_config() -> Config:
    """Minimal config for RichRenderer tests."""
    return Config(app_name="auto-semver", command="bump", max_events=50)


class TestRichRenderer:
    """Tests for dashboard width, qualname, and persistence."""

    @pytest.mark.unit
    @pytest.mark.parametrize("width", [40, 80, 120])
    def test_render_lines_share_width(self, width: int, rich_config: Config) -> None:
        """Every ANSI-stripped line has the same cell width at common sizes."""
        console = Console(force_terminal=True, force_interactive=False, width=width, height=30)
        summary = RunSummary(app_name="auto-semver")
        summary.set("version", "1.0.0 -> 1.1.0")
        summary.set("branches", "feature/x -> main")
        summary.set("pr", "pending")
        view = RichRenderer(rich_config, console=console, summary=summary)
        view.begin_group("Resolve version")
        view.set_status("Fetching baseline...")
        view.message(logging.INFO, "ok", created=1.0)
        view.message(
            logging.ERROR,
            "Target branch foo is not in suffixes",
            created=2.0,
        )

        with console.capture() as capture:
            console.print(view.render())
        plain = re.sub(r"\x1b\[[0-9;]*m", "", capture.get())
        lines = [line for line in plain.splitlines() if line.strip()]
        assert lines
        lengths = {len(line) for line in lines}
        assert len(lengths) == 1, f"Uneven widths {lengths} at console width {width}"
        assert view.command == "bump"
        assert "Resolve" not in f"auto-semver  {view.command}"

    @pytest.mark.unit
    def test_log_card_includes_qualname(self, rich_config: Config) -> None:
        """Live log card renders Class.method before the message."""
        console = Console(force_terminal=True, force_interactive=False, width=80, height=30)
        view = RichRenderer(rich_config, console=console)
        view.message(
            logging.INFO,
            "Adding files",
            qualname="GitOps.commit",
            created=1.0,
        )
        with console.capture() as capture:
            console.print(view.render())
        plain = re.sub(r"\x1b\[[0-9;]*m", "", capture.get())
        assert "GitOps.commit" in plain
        assert "Adding files" in plain

    @pytest.mark.unit
    def test_event_buffer_drops_oldest(self, rich_config: Config) -> None:
        """Bounded event buffer drops oldest entries when over max."""
        console = Console(force_terminal=False, width=80, height=24)
        cfg = Config(app_name="auto-semver", max_events=3)
        view = RichRenderer(cfg, console=console)
        for i in range(5):
            view.message(logging.INFO, f"m{i}", created=float(i))
        assert len(view._events) == 3
        assert view._events[0].message == "m2"

    @pytest.mark.unit
    def test_status_context_toggles_spinner(
        self, rich_config: Config, mocker: MockerFixture
    ) -> None:
        """status() context manager toggles the spinning flag."""
        console = Console(force_terminal=False, width=80, height=24)
        view = RichRenderer(rich_config, console=console)
        # Force live so status does not also emit via logger.
        fake_live = mocker.MagicMock()
        view._live = fake_live
        reporter = Reporter(rich_config, view, RunSummary(app_name="auto-semver"))
        _ReporterState.current = reporter
        was_spinning = view._spinning
        with status("Working..."):
            during_spinning = view._spinning
            during_status = view._status
        assert was_spinning is False
        assert during_spinning is True
        assert during_status == "Working..."
        assert view._spinning is False
        _ReporterState.current = None

    @pytest.mark.unit
    def test_stop_persists_full_dashboard(self, rich_config: Config, mocker: MockerFixture) -> None:
        """close() reprints the full dashboard so logs remain after Live exits."""
        console = Console(force_terminal=True, force_interactive=False, width=80, height=30)
        view = RichRenderer(rich_config, console=console)
        view.begin_group("Finalize")
        view.set_status("Would push branch...")
        view.message(
            logging.INFO,
            "Dry-run complete",
            qualname="main",
            created=1.0,
        )
        fake_live = mocker.MagicMock()
        view._live = fake_live
        printed: list[object] = []
        mocker.patch.object(console, "print", side_effect=lambda r: printed.append(r))

        view.close()

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
        self, rich_config: Config, mocker: MockerFixture
    ) -> None:
        """flush_summary does not replace the dashboard with a summary-only panel."""
        console = Console(force_terminal=False, width=80, height=24)
        view = RichRenderer(rich_config, console=console)
        view._persisted_dashboard = True
        print_mock = mocker.patch.object(console, "print")
        view.flush_summary(RunSummary(app_name="auto-semver"))
        print_mock.assert_not_called()

    @pytest.mark.unit
    def test_flush_summary_prints_when_live_never_started(
        self, rich_config: Config, mocker: MockerFixture
    ) -> None:
        """Non-TTY runs still get the summary panel."""
        console = Console(force_terminal=False, width=80, height=24)
        view = RichRenderer(rich_config, console=console)
        print_mock = mocker.patch.object(console, "print")
        view.flush_summary(RunSummary(app_name="auto-semver"))
        print_mock.assert_called_once()

    @pytest.mark.unit
    def test_log_group_sets_phase(self, rich_config: Config) -> None:
        """log_group updates the phase via the process reporter."""
        console = Console(force_terminal=False, width=80, height=24)
        view = RichRenderer(rich_config, console=console)
        reporter = Reporter(rich_config, view, RunSummary(app_name="auto-semver"))
        _ReporterState.current = reporter
        with log_group("Resolve version"):
            assert view._phase == "Resolve version"
        _ReporterState.current = None
