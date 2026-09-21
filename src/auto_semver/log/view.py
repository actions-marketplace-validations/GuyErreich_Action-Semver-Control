# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""One-page Rich Live dashboard for local TTY runs."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from auto_semver.log.summary import JobSummary

if TYPE_CHECKING:
    from auto_semver.log.github import GroupObserver

_LEVEL_STYLES: dict[int, str] = {
    logging.DEBUG: "dim",
    logging.INFO: "cyan",
    logging.WARNING: "yellow",
    logging.ERROR: "red",
    logging.CRITICAL: "bold red",
}

_LEVEL_LABELS: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRIT",
}


@dataclass(frozen=True)
class LogEvent:
    """A single log line shown in the Live event pane."""

    level: int
    message: str
    created: float
    qualname: str = ""


class LiveView:
    """In-place rounded dashboard driven by phases, status, and log events."""

    def __init__(
        self,
        *,
        console: Console | None = None,
        summary: JobSummary | None = None,
        command: str = "bump",
        debug: bool = False,
        max_events: int = 50,
    ) -> None:
        """Create a LiveView.

        Args:
            console: Shared Rich console (created if omitted).
            summary: Shared JobSummary instance.
            command: Short command name for the outer title.
            debug: When True, DEBUG events appear in the log pane.
            max_events: Hard cap on buffered events (also trimmed by height).
        """
        self.console = console or Console()
        self.summary = summary or JobSummary()
        self.command = command
        self.debug = debug
        self._phase = "Starting"
        self._status = "Ready"
        self._persisted_dashboard = False
        self._spinning = False
        self._error_banner: str | None = None
        self._events: deque[LogEvent] = deque(maxlen=max_events)
        self._live: Live | None = None
        self._observers: list[GroupObserver] = []
        self._spinner = Spinner("dots", style="cyan")

    def add_observer(self, observer: GroupObserver) -> None:
        """Register a group/summary observer (e.g. GitHub Actions adapter).

        Args:
            observer: Object implementing group and summary callbacks.
        """
        self._observers.append(observer)

    def set_command(self, command: str) -> None:
        """Update the outer panel title command segment.

        Args:
            command: Short command name (``bump``, ``promote``, ...).
        """
        self.command = command
        self._refresh()

    def set_phase(self, title: str) -> None:
        """Update the current phase (shown inside the status card).

        Args:
            title: Phase name; never placed on the outer border.
        """
        self._phase = title
        self._refresh()

    def set_status(self, message: str) -> None:
        """Update the status line text.

        Args:
            message: Status message shown next to the spinner.
        """
        self._status = message
        self._refresh()

    def add_event(self, event: LogEvent) -> None:
        """Append a log event to the bounded event pane.

        Args:
            event: Log event to display.
        """
        if event.level < logging.INFO and not self.debug:
            return
        self._events.append(event)
        if event.level >= logging.ERROR:
            self._error_banner = event.message
        self._trim_events_to_height()
        self._refresh()

    def clear_error_banner(self) -> None:
        """Clear the sticky error banner after recovery."""
        self._error_banner = None
        self._refresh()

    @property
    def is_running(self) -> bool:
        """Whether the Live alternate screen is active."""
        return self._live is not None

    def start(self) -> None:
        """Start the Live alternate-screen dashboard when stdout is a TTY."""
        if self._live is not None:
            return
        if not self.console.is_terminal:
            return
        self._live = Live(
            self.render(),
            console=self.console,
            refresh_per_second=12,
            screen=True,
            transient=False,
        )
        self._live.start()

    def stop(self) -> None:
        """Stop Live and leave the final dashboard on the primary screen.

        ``Live(screen=True)`` uses the alternate buffer, which is discarded on
        exit. Printing the last render afterward keeps status, run, and logs
        visible so the UI does not jump to a summary-only panel.
        """
        if self._live is None:
            return
        self._spinning = False
        if self._status and not self._status.lower().startswith("done"):
            # Keep phase/logs; mark the spinner-era status as finished.
            self._status = f"Done — {self._status}" if self._status != "Ready" else "Done"
        final = self.render()
        self._live.update(final)
        self._live.stop()
        self._live = None
        self.console.print(final)
        self._persisted_dashboard = True

    def flush_summary(self) -> None:
        """Print the final summary when Live did not persist a dashboard.

        When the full one-page view was already printed by :meth:`stop`, skip
        the summary-only panel so logs stay on screen. Always notify observers
        (e.g. GitHub step summary).
        """
        if not self._persisted_dashboard:
            width = self.console.width
            self.console.print(self.summary.as_panel(width=width))
        for observer in self._observers:
            observer.on_summary(self.summary)

    def render(self) -> RenderableType:
        """Build the full-width nested rounded dashboard.

        Returns:
            Outer Panel containing status, run, and log cards.
        """
        outer_width = self.console.width
        # Outer border (2) + horizontal padding (2+2) = 6
        inner_width = max(20, outer_width - 6)

        status_card = self._render_status_card(inner_width)
        run_card = self.summary.as_panel(title="run", width=inner_width)
        log_card = self._render_log_card(inner_width)

        body: list[RenderableType] = [status_card, Text(""), run_card, Text(""), log_card]
        if self._error_banner:
            banner = Panel(
                Text(self._error_banner, style="bold red", overflow="fold"),
                title="error",
                title_align="left",
                box=box.ROUNDED,
                border_style="red",
                expand=True,
                width=inner_width,
                padding=(0, 1),
            )
            body.insert(0, banner)
            body.insert(1, Text(""))

        title = f"auto-semver  {self.command}"
        return Panel(
            Group(*body),
            title=title,
            title_align="left",
            box=box.ROUNDED,
            border_style="cyan",
            expand=True,
            width=outer_width,
            padding=(1, 2),
        )

    def _render_status_card(self, width: int) -> Panel:
        """Build the status card with phase, message, and fixed spinner column."""
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column("text", ratio=1, overflow="fold")
        table.add_column("spin", width=3, justify="right", no_wrap=True)

        phase_line = Text(f"phase: {self._phase}", style="dim", overflow="fold")
        status_text = Text(self._status, overflow="fold")
        spin: RenderableType = self._spinner if self._spinning else Text("   ")

        table.add_row(phase_line, Text(""))
        table.add_row(status_text, spin)

        return Panel(
            table,
            title="status",
            title_align="left",
            box=box.ROUNDED,
            border_style="dim",
            expand=True,
            width=width,
            padding=(0, 1),
        )

    def _render_log_card(self, width: int) -> Panel:
        """Build the log card with level chips, function name, and messages."""
        lines: list[Text] = []
        for event in self._events:
            label = _LEVEL_LABELS.get(event.level, "INFO")
            style = _LEVEL_STYLES.get(event.level, "cyan")
            chip = Text(f" {label} ", style=f"bold {style} reverse")
            msg_style = "red" if event.level >= logging.ERROR else ""
            message = Text(event.message, style=msg_style, overflow="fold")
            row = Text()
            row.append_text(chip)
            row.append("  ")
            if event.qualname:
                row.append(event.qualname, style="dim")
                row.append("  ")
            row.append_text(message)
            lines.append(row)

        content: RenderableType = Group(*lines) if lines else Text("_(no events)_", style="dim")
        border = "red" if self._error_banner else "dim"
        return Panel(
            content,
            title="log",
            title_align="left",
            box=box.ROUNDED,
            border_style=border,
            expand=True,
            width=width,
            padding=(0, 1),
        )

    def _trim_events_to_height(self) -> None:
        """Drop oldest events so the log pane fits the console height budget."""
        # Reserve ~12 rows for chrome + status + run cards
        budget = max(3, self.console.height - 14)
        while len(self._events) > budget:
            self._events.popleft()

    def _refresh(self) -> None:
        """Push a new renderable to Live when it is running."""
        if self._live is not None:
            self._live.update(self.render())


# Module-level registry used by log_group / status / setup_logger.
class _ViewState:
    """Mutable holder so we avoid module-level ``global`` statements."""

    current: LiveView | None = None


def get_view() -> LiveView | None:
    """Return the active LiveView, if configured."""
    return _ViewState.current


def set_view(view: LiveView | None) -> None:
    """Install or clear the module-level LiveView.

    Args:
        view: LiveView instance or ``None`` to clear.
    """
    _ViewState.current = view


@contextmanager
def log_group(title: str) -> Iterator[None]:
    """Mark a UX phase (updates LiveView; notifies GitHub observers).

    Args:
        title: Phase title shown inside the status card.

    Yields:
        None
    """
    view = get_view()
    if view is not None:
        view.set_phase(title)
        for observer in view._observers:
            observer.on_group_start(title)
    try:
        yield
    finally:
        if view is not None:
            for observer in view._observers:
                observer.on_group_end()


@contextmanager
def status(message: str) -> Iterator[None]:
    """Show an in-progress status (spinner on TTY Live).

    When Live is not running (e.g. GitHub Actions), also emit the status via
    the root logger so it appears inside ``::group::`` sections on stdout.

    Args:
        message: Status text.

    Yields:
        None
    """
    view = get_view()
    live = view is not None and view.is_running
    if view is not None:
        view.set_status(message)
        view._spinning = True
        view._refresh()
    if not live:
        logging.getLogger("auto_semver").info("%s", message)
    try:
        yield
    finally:
        if view is not None:
            view._spinning = False
            view._refresh()
