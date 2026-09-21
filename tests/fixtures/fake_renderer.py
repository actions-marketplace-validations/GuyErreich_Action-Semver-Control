# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Fake Renderer that records structured calls for unit tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from runview.summary import RunSummary


@dataclass
class FakeRenderer:
    """Test double that records all Renderer protocol calls."""

    live: bool = False
    opened: bool = False
    closed: bool = False
    commands: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    group_ends: int = 0
    statuses: list[tuple[str, bool]] = field(default_factory=list)
    messages: list[tuple[int, str, str, float]] = field(default_factory=list)
    tables: list[tuple[str, tuple[str, ...], tuple[tuple[str, ...], ...]]] = field(
        default_factory=list
    )
    summaries: list[RunSummary] = field(default_factory=list)

    @property
    def is_live(self) -> bool:
        """Whether this fake reports as a live surface."""
        return self.live

    def open(self) -> None:
        """Record open."""
        self.opened = True

    def close(self) -> None:
        """Record close."""
        self.closed = True
        self.live = False

    def message(
        self,
        level: int,
        text: str,
        *,
        qualname: str = "",
        created: float = 0.0,
    ) -> None:
        """Record a message call."""
        self.messages.append((level, text, qualname, created))

    def set_command(self, command: str) -> None:
        """Record set_command."""
        self.commands.append(command)

    def begin_group(self, title: str) -> None:
        """Record begin_group."""
        self.groups.append(title)

    def end_group(self) -> None:
        """Record end_group."""
        self.group_ends += 1

    def set_status(self, message: str, *, spinning: bool = False) -> None:
        """Record set_status."""
        self.statuses.append((message, spinning))

    def table(
        self,
        title: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> None:
        """Record table."""
        self.tables.append(
            (title, tuple(headers), tuple(tuple(str(c) for c in row) for row in rows))
        )

    def flush_summary(self, summary: RunSummary) -> None:
        """Record flush_summary."""
        self.summaries.append(summary)
