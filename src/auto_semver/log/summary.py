# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run summary data shared by the Live view and optional GitHub job summary."""

from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.table import Table


class JobSummary:
    """Collect key/value fields for the end-of-run summary panel."""

    def __init__(self) -> None:
        """Initialize an empty field map."""
        self._fields: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        """Set or replace a summary field.

        Args:
            key: Field label shown in the summary.
            value: Field value (plain text).
        """
        self._fields[key] = value

    def get(self, key: str, default: str = "") -> str:
        """Return a field value or ``default``.

        Args:
            key: Field label.
            default: Value when the key is missing.

        Returns:
            Stored value or ``default``.
        """
        return self._fields.get(key, default)

    def as_table(self) -> Table:
        """Build a borderless Rich table of summary fields.

        Returns:
            Table with dim keys and bold values.
        """
        table = Table(box=None, expand=True, show_header=False, padding=(0, 1))
        table.add_column("key", style="dim", no_wrap=True)
        table.add_column("value", style="bold", overflow="fold")
        for key, value in self._fields.items():
            table.add_row(key, value)
        return table

    def as_panel(self, *, title: str = "run", width: int | None = None) -> Panel:
        """Render the summary as a rounded panel.

        Args:
            title: Panel title (short chrome text).
            width: Explicit panel width for alignment.

        Returns:
            Rounded Panel wrapping the summary table.
        """
        return Panel(
            self.as_table(),
            title=title,
            title_align="left",
            box=box.ROUNDED,
            border_style="dim",
            expand=True,
            width=width,
            padding=(0, 1),
        )

    def as_markdown(self) -> str:
        """Render the summary as GitHub-flavored Markdown.

        Returns:
            Markdown table string for ``GITHUB_STEP_SUMMARY``.
        """
        if not self._fields:
            return "## auto-semver\n\n_(no summary fields)_\n"
        lines = ["## auto-semver", "", "| | |", "| --- | --- |"]
        for key, value in self._fields.items():
            safe_key = key.replace("|", "\\|")
            safe_value = value.replace("|", "\\|")
            lines.append(f"| **{safe_key}** | {safe_value} |")
        lines.append("")
        return "\n".join(lines)
