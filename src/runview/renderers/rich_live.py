# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MPL-2.0
"""Rich Live dashboard renderer for local TTY runs."""

from __future__ import annotations

import logging
import sys
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from runview.config import Config, Theme
from runview.summary import RunSummary


@dataclass(frozen=True)
class LogEvent:
    """A single log line shown in the Live event pane."""

    level: int
    message: str
    created: float
    qualname: str = ""


@dataclass(frozen=True)
class _TableData:
    """Structured table stored for dashboard rendering."""

    title: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


class RichRenderer:
    """In-place rounded dashboard driven by phases, status, and log events."""

    def __init__(
        self,
        config: Config,
        *,
        console: Console | None = None,
        summary: RunSummary | None = None,
    ) -> None:
        """Create a Rich Live renderer.

        Args:
            config: Process-wide runview config.
            console: Shared Rich console (created if omitted).
            summary: Shared RunSummary instance.
        """
        self.config = config
        self.theme: Theme = config.theme
        self.console = console or Console()
        self.summary = summary or RunSummary(app_name=config.app_name)
        self.command = config.command
        self.debug = config.debug
        self._phase = "Starting"
        self._status = "Ready"
        self._persisted_dashboard = False
        self._spinning = False
        self._error_banner: str | None = None
        self._events: deque[LogEvent] = deque(maxlen=config.max_events)
        self._live: Live | None = None
        self._table: _TableData | None = None
        self._spinner = Spinner("dots", style=self.theme.accent)

    @property
    def is_live(self) -> bool:
        """Whether the Live alternate screen is active."""
        return self._live is not None

    def open(self) -> None:
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

    def close(self) -> None:
        """Stop Live and leave the final dashboard on the primary screen.

        ``Live(screen=True)`` uses the alternate buffer, which is discarded on
        exit. Printing the last render afterward keeps status, run, and logs
        visible so the UI does not jump to a summary-only panel.
        """
        if self._live is None:
            return
        self._spinning = False
        if self._status and not self._status.lower().startswith("done"):
            self._status = f"Done — {self._status}" if self._status != "Ready" else "Done"
        final = self.render()
        self._live.update(final)
        self._live.stop()
        self._live = None
        self.console.print(final)
        self._persisted_dashboard = True

    def message(
        self,
        level: int,
        text: str,
        *,
        qualname: str = "",
        created: float = 0.0,
    ) -> None:
        """Append a log event to the bounded event pane.

        Args:
            level: Stdlib logging level number.
            text: Raw message text.
            qualname: Optional caller qualname.
            created: Log record timestamp.
        """
        if level < logging.INFO and not self.debug:
            return
        self._events.append(LogEvent(level=level, message=text, created=created, qualname=qualname))
        if level >= logging.ERROR:
            self._error_banner = text
        self._trim_events_to_height()
        if self.is_live:
            self._refresh()
        elif level >= logging.INFO:
            # Non-TTY explicit rich style: mirror operator lines to stdout.
            sys.stdout.write(f"{text}\n")
            sys.stdout.flush()

    def set_command(self, command: str) -> None:
        """Update the outer panel title command segment.

        Args:
            command: Short command name.
        """
        self.command = command
        self._refresh()

    def begin_group(self, title: str) -> None:
        """Update the current phase (shown inside the status card).

        Args:
            title: Phase name; never placed on the outer border.
        """
        self._phase = title
        self._refresh()

    def end_group(self) -> None:
        """No-op — phase remains until the next begin_group."""

    def set_status(self, message: str, *, spinning: bool = False) -> None:
        """Update the status line text and spinner.

        Args:
            message: Status message shown next to the spinner.
            spinning: Whether the spinner column is active.
        """
        self._status = message
        self._spinning = spinning
        self._refresh()

    def table(
        self,
        title: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> None:
        """Store a structured table for inclusion in the dashboard.

        Args:
            title: Table title.
            headers: Column headers.
            rows: Cell values.
        """
        self._table = _TableData(
            title=title,
            headers=tuple(headers),
            rows=tuple(tuple(str(c) for c in row) for row in rows),
        )
        self._refresh()

    def flush_summary(self, summary: RunSummary) -> None:
        """Print the final summary when Live did not persist a dashboard.

        When the full one-page view was already printed by :meth:`close`, skip
        the summary-only panel so logs stay on screen.

        Args:
            summary: Collected run summary.
        """
        if not self._persisted_dashboard:
            width = self.console.width
            self.console.print(summary.as_panel(width=width))

    def render(self) -> RenderableType:
        """Build the full-width nested rounded dashboard.

        Returns:
            Outer Panel containing status, run, and log cards.
        """
        outer_width = self.console.width
        inner_width = max(20, outer_width - 6)

        status_card = self._render_status_card(inner_width)
        run_card = self.summary.as_panel(title="run", width=inner_width)
        log_card = self._render_log_card(inner_width)

        body: list[RenderableType] = [status_card, Text(""), run_card, Text(""), log_card]
        if self._table is not None:
            body.insert(3, Text(""))
            body.insert(4, self._render_data_table(inner_width))

        if self._error_banner:
            banner = Panel(
                Text(self._error_banner, style="bold red", overflow="fold"),
                title="error",
                title_align="left",
                box=self.theme.box,
                border_style="red",
                expand=True,
                width=inner_width,
                padding=(0, 1),
            )
            body.insert(0, banner)
            body.insert(1, Text(""))

        title = f"{self.config.app_name}  {self.command}"
        return Panel(
            Group(*body),
            title=title,
            title_align="left",
            box=self.theme.box,
            border_style=self.theme.accent,
            expand=True,
            width=outer_width,
            padding=(1, 2),
        )

    def _render_status_card(self, width: int) -> Panel:
        """Build the status card with phase, message, and fixed spinner column."""
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column("text", ratio=1, overflow="fold")
        table.add_column("spin", width=3, justify="right", no_wrap=True)

        phase_line = Text(f"phase: {self._phase}", style=self.theme.muted, overflow="fold")
        status_text = Text(self._status, overflow="fold")
        spin: RenderableType = self._spinner if self._spinning else Text("   ")

        table.add_row(phase_line, Text(""))
        table.add_row(status_text, spin)

        return Panel(
            table,
            title="status",
            title_align="left",
            box=self.theme.box,
            border_style=self.theme.muted,
            expand=True,
            width=width,
            padding=(0, 1),
        )

    def _render_log_card(self, width: int) -> Panel:
        """Build the log card with level chips, function name, and messages."""
        lines: list[Text] = []
        for event in self._events:
            label = self.theme.level_labels.get(event.level, "INFO")
            style = self.theme.level_styles.get(event.level, self.theme.accent)
            chip = Text(f" {label} ", style=f"bold {style} reverse")
            msg_style = "red" if event.level >= logging.ERROR else ""
            message = Text(event.message, style=msg_style, overflow="fold")
            row = Text()
            row.append_text(chip)
            row.append("  ")
            if event.qualname:
                row.append(event.qualname, style=self.theme.muted)
                row.append("  ")
            row.append_text(message)
            lines.append(row)

        content: RenderableType = (
            Group(*lines) if lines else Text("_(no events)_", style=self.theme.muted)
        )
        border = "red" if self._error_banner else self.theme.muted
        return Panel(
            content,
            title="log",
            title_align="left",
            box=self.theme.box,
            border_style=border,
            expand=True,
            width=width,
            padding=(0, 1),
        )

    def _render_data_table(self, width: int) -> Panel:
        """Build a Rich table panel from stored structured table data."""
        assert self._table is not None
        data = self._table
        table = Table(box=self.theme.box, expand=True, show_header=bool(data.headers))
        for header in data.headers:
            table.add_column(header, overflow="fold")
        if not data.headers and data.rows:
            for _ in data.rows[0]:
                table.add_column(overflow="fold")
        for row in data.rows:
            table.add_row(*row)
        return Panel(
            table,
            title=data.title,
            title_align="left",
            box=self.theme.box,
            border_style=self.theme.muted,
            expand=True,
            width=width,
            padding=(0, 1),
        )

    def _trim_events_to_height(self) -> None:
        """Drop oldest events so the log pane fits the console height budget."""
        budget = max(3, self.console.height - self.config.height_reserved)
        while len(self._events) > budget:
            self._events.popleft()

    def _refresh(self) -> None:
        """Push a new renderable to Live when it is running."""
        if self._live is not None:
            self._live.update(self.render())
