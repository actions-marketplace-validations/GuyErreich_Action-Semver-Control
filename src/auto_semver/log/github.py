# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""GitHub Actions adapter: annotations, groups, and job summary."""

from __future__ import annotations

import logging
import os
import sys
from logging import LogRecord
from pathlib import Path
from typing import Protocol

from auto_semver.log.summary import JobSummary
from auto_semver.log.view import LiveView, get_view


class GroupObserver(Protocol):
    """Callbacks for phase groups and end-of-run summary."""

    def on_group_start(self, title: str) -> None:
        """Called when a log_group starts."""

    def on_group_end(self) -> None:
        """Called when a log_group ends."""

    def on_summary(self, summary: JobSummary) -> None:
        """Called when the job summary is flushed."""


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


class GitHubActionsHandler(logging.Handler):
    """Emit GitHub workflow annotations for WARNING and ERROR records."""

    def emit(self, record: LogRecord) -> None:
        """Write ``::warning::`` or ``::error::`` for high-severity records.

        Args:
            record: Stdlib log record.
        """
        try:
            if record.levelno >= logging.ERROR:
                _print_command("error", record.getMessage())
            elif record.levelno >= logging.WARNING:
                _print_command("warning", record.getMessage())
        except Exception:
            self.handleError(record)


class GitHubActionsAdapter:
    """Mirror log groups and write ``GITHUB_STEP_SUMMARY`` markdown."""

    def on_group_start(self, title: str) -> None:
        """Emit ``::group::`` for a phase title.

        Args:
            title: Phase title.
        """
        _print_command("group", title)

    def on_group_end(self) -> None:
        """Emit ``::endgroup::``."""
        sys.stdout.write("::endgroup::\n")
        sys.stdout.flush()

    def on_summary(self, summary: JobSummary) -> None:
        """Append markdown summary to ``$GITHUB_STEP_SUMMARY`` when set.

        Args:
            summary: Collected job summary fields.
        """
        path = os.environ.get("GITHUB_STEP_SUMMARY")
        if not path:
            return
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(summary.as_markdown())


def attach_github_adapter(view: LiveView | None = None) -> GitHubActionsHandler:
    """Attach GitHub Actions logging sinks when running in Actions.

    Args:
        view: LiveView to observe for groups/summary (defaults to module view).

    Returns:
        The installed ``GitHubActionsHandler``.
    """
    target = view if view is not None else get_view()
    adapter = GitHubActionsAdapter()
    if target is not None:
        target.add_observer(adapter)

    handler = GitHubActionsHandler()
    handler.setLevel(logging.WARNING)
    root = logging.getLogger()
    root.addHandler(handler)
    return handler


def is_github_actions() -> bool:
    """Return True when ``GITHUB_ACTIONS`` is set to ``true``."""
    return os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
