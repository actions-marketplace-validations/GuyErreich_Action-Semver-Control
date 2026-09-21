# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MPL-2.0
"""GitHub Actions renderer — workflow commands + plain INFO lines."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from runview.config import Config
from runview.renderers.plain import PlainRenderer
from runview.summary import RunSummary


def _escape_workflow_data(value: str) -> str:
    """Escape ``%``, newlines, and carriage returns for workflow commands.

    Args:
        value: Raw message text.

    Returns:
        Escaped string safe for ``::warning::`` / ``::error::`` data.
    """
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _print_command(command: str, message: str = "") -> None:
    """Write an unstyled workflow command line to stdout.

    Args:
        command: Command name (``group``, ``endgroup``, ``warning``, ``error``).
        message: Optional command data / title.
    """
    if message:
        sys.stdout.write(f"::{command}::{_escape_workflow_data(message)}\n")
    else:
        sys.stdout.write(f"::{command}::\n")
    sys.stdout.flush()


class GitHubRenderer(PlainRenderer):
    """Plain INFO sink with GitHub annotations as the sole WARNING/ERROR path."""

    def __init__(self, config: Config) -> None:
        """Create a GitHub Actions renderer.

        Args:
            config: Process-wide runview config.
        """
        super().__init__(config)

    def message(
        self,
        level: int,
        text: str,
        *,
        qualname: str = "",
        created: float = 0.0,
    ) -> None:
        """Emit ``::warning::`` / ``::error::`` or a plain INFO line.

        WARNING and ERROR are annotation-only — no duplicate plain line.

        Args:
            level: Stdlib logging level number.
            text: Raw message text.
            qualname: Unused for Actions annotations.
            created: Unused for Actions annotations.
        """
        if level >= logging.ERROR:
            _print_command("error", text)
            return
        if level >= logging.WARNING:
            _print_command("warning", text)
            return
        super().message(level, text, qualname=qualname, created=created)

    def begin_group(self, title: str) -> None:
        """Emit ``::group::`` for a phase title.

        Args:
            title: Phase title.
        """
        _print_command("group", title)

    def end_group(self) -> None:
        """Emit ``::endgroup::``."""
        sys.stdout.write("::endgroup::\n")
        sys.stdout.flush()

    def table(
        self,
        title: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> None:
        """Print a GitHub-flavored Markdown table.

        Args:
            title: Table title.
            headers: Column headers.
            rows: Cell values.
        """
        sys.stdout.write(f"### {title}\n\n")
        if headers:
            sys.stdout.write("| " + " | ".join(headers) + " |\n")
            sys.stdout.write("| " + " | ".join("---" for _ in headers) + " |\n")
            for row in rows:
                cells = [str(c).replace("|", "\\|") for c in row]
                sys.stdout.write("| " + " | ".join(cells) + " |\n")
        sys.stdout.write("\n")
        sys.stdout.flush()

    def flush_summary(self, summary: RunSummary) -> None:
        """Append markdown summary to ``$GITHUB_STEP_SUMMARY`` when set.

        Args:
            summary: Collected run summary.
        """
        path = os.environ.get("GITHUB_STEP_SUMMARY")
        if not path:
            return
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(summary.as_markdown())
