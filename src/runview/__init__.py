# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MPL-2.0
"""Public runview API — structured run presentation independent of auto_semver."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from runview.config import Config, Theme
from runview.reporter import get_reporter as _get_reporter
from runview.reporter import install
from runview.summary import RunSummary


def get_summary() -> RunSummary:
    """Return the process-wide RunSummary.

    Returns:
        Shared RunSummary (empty if install has not run yet).
    """
    reporter = _get_reporter()
    if reporter is None:
        return RunSummary()
    return reporter.summary


def set_command(command: str) -> None:
    """Update the command label on the active renderer.

    Args:
        command: Short command name.
    """
    reporter = _get_reporter()
    if reporter is not None:
        reporter.set_command(command)


def table(
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> None:
    """Present a structured table via the active renderer.

    Args:
        title: Table title.
        headers: Column headers.
        rows: Cell values.
    """
    reporter = _get_reporter()
    if reporter is not None:
        reporter.table(title, headers, rows)


@contextmanager
def log_group(title: str) -> Iterator[None]:
    """Mark a UX phase on the active renderer.

    Args:
        title: Phase title.

    Yields:
        None
    """
    reporter = _get_reporter()
    if reporter is None:
        yield
        return
    with reporter.log_group(title):
        yield


@contextmanager
def status(message: str) -> Iterator[None]:
    """Show an in-progress status on the active renderer.

    Args:
        message: Status text.

    Yields:
        None
    """
    reporter = _get_reporter()
    if reporter is None:
        yield
        return
    with reporter.status(message):
        yield


def close() -> None:
    """Stop the active renderer and flush the summary."""
    reporter = _get_reporter()
    if reporter is not None:
        reporter.close()


__all__ = [
    "Config",
    "RunSummary",
    "Theme",
    "close",
    "get_summary",
    "install",
    "log_group",
    "set_command",
    "status",
    "table",
]
