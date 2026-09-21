# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MPL-2.0
"""Renderer protocol — structured data only, no pre-rendered strings from callers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from runview.summary import RunSummary


class Renderer(Protocol):
    """Active presentation sink for messages and run structure."""

    def open(self) -> None:
        """Start the renderer (e.g. Live dashboard)."""

    def close(self) -> None:
        """Stop the renderer and persist any final frame."""

    def message(
        self,
        level: int,
        text: str,
        *,
        qualname: str = "",
        created: float = 0.0,
    ) -> None:
        """Present a log message.

        Args:
            level: Stdlib logging level number.
            text: Raw message text (not pre-styled / width-padded).
            qualname: Optional caller qualname for forensic display.
            created: Log record timestamp.
        """

    def set_command(self, command: str) -> None:
        """Update the command label shown in chrome."""

    def begin_group(self, title: str) -> None:
        """Open a named phase / group."""

    def end_group(self) -> None:
        """Close the current phase / group."""

    def set_status(self, message: str, *, spinning: bool = False) -> None:
        """Update the status line.

        Args:
            message: Status text.
            spinning: Whether an in-progress indicator should show.
        """

    def table(
        self,
        title: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> None:
        """Present a tabular dataset.

        Args:
            title: Table title.
            headers: Column headers.
            rows: Cell values (plain strings).
        """

    def flush_summary(self, summary: RunSummary) -> None:
        """Emit the end-of-run summary."""

    @property
    def is_live(self) -> bool:
        """Whether an interactive live surface owns the console."""
