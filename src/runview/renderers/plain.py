# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MPL-2.0
"""Plain stdout renderer for non-TTY / non-Actions environments."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from runview.config import Config
from runview.summary import RunSummary


class PlainRenderer:
    """Print operator-facing lines to stdout without Rich Live."""

    def __init__(self, config: Config) -> None:
        """Create a plain renderer.

        Args:
            config: Process-wide runview config.
        """
        self.config = config
        self.command = config.command
        self._open = False

    def open(self) -> None:
        """Mark the renderer as active."""
        self._open = True

    def close(self) -> None:
        """Mark the renderer as stopped."""
        self._open = False

    @property
    def is_live(self) -> bool:
        """Plain mode never owns an interactive Live surface."""
        return False

    def message(
        self,
        level: int,
        text: str,
        *,
        qualname: str = "",
        created: float = 0.0,
    ) -> None:
        """Print a message-only line for INFO and above.

        Args:
            level: Stdlib logging level number.
            text: Raw message text.
            qualname: Unused in plain mode (file sink owns forensics).
            created: Unused in plain mode.
        """
        del qualname, created
        if level < logging.INFO:
            return
        sys.stdout.write(f"{text}\n")
        sys.stdout.flush()

    def set_command(self, command: str) -> None:
        """Store the command label (unused for plain output).

        Args:
            command: Short command name.
        """
        self.command = command

    def begin_group(self, title: str) -> None:
        """No-op for plain mode (title is structural only).

        Args:
            title: Phase title.
        """
        del title

    def end_group(self) -> None:
        """No-op for plain mode."""

    def set_status(self, message: str, *, spinning: bool = False) -> None:
        """No-op — status is mirrored via the logger when not live.

        Args:
            message: Status text.
            spinning: Unused.
        """
        del message, spinning

    def table(
        self,
        title: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> None:
        """Print a simple aligned text table.

        Args:
            title: Table title.
            headers: Column headers.
            rows: Cell values.
        """
        sys.stdout.write(f"{title}\n")
        if headers:
            sys.stdout.write(" | ".join(headers) + "\n")
            sys.stdout.write(" | ".join("---" for _ in headers) + "\n")
        for row in rows:
            sys.stdout.write(" | ".join(str(cell) for cell in row) + "\n")
        sys.stdout.flush()

    def flush_summary(self, summary: RunSummary) -> None:
        """Print the summary as plain text key/value lines.

        Args:
            summary: Collected run summary.
        """
        sys.stdout.write(f"== {summary.app_name} ==\n")
        for key, value in summary.items():
            sys.stdout.write(f"{key}: {value}\n")
        sys.stdout.flush()
