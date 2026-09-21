# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MPL-2.0
"""Reporter facade owning the active renderer and structure API."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from rich.console import Console

from runview.bridge import ReporterHandler
from runview.config import Config
from runview.file_sink import FileLogHandler
from runview.record import record_factory
from runview.renderers import select_renderer
from runview.renderers.base import Renderer
from runview.summary import RunSummary


class _ReporterState:
    """Mutable holder so we avoid module-level ``global`` statements."""

    current: Reporter | None = None


class Reporter:
    """Owns the active renderer, summary, and structure helpers."""

    def __init__(self, config: Config, renderer: Renderer, summary: RunSummary) -> None:
        """Create a reporter.

        Args:
            config: Process-wide config.
            renderer: Sole active renderer.
            summary: Shared run summary.
        """
        self.config = config
        self.renderer = renderer
        self.summary = summary

    def message(
        self,
        level: int,
        text: str,
        *,
        qualname: str = "",
        created: float = 0.0,
    ) -> None:
        """Forward a structured message to the active renderer."""
        self.renderer.message(level, text, qualname=qualname, created=created)

    def set_command(self, command: str) -> None:
        """Update the command label on the active renderer."""
        self.renderer.set_command(command)

    def table(
        self,
        title: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> None:
        """Present a structured table via the active renderer."""
        self.renderer.table(title, headers, rows)

    @contextmanager
    def log_group(self, title: str) -> Iterator[None]:
        """Mark a UX phase on the active renderer.

        Args:
            title: Phase title.

        Yields:
            None
        """
        self.renderer.begin_group(title)
        try:
            yield
        finally:
            self.renderer.end_group()

    @contextmanager
    def status(self, message: str) -> Iterator[None]:
        """Show an in-progress status.

        When the renderer is not live, also emit the status via the app logger
        so it appears inside groups on stdout.

        Args:
            message: Status text.

        Yields:
            None
        """
        live = self.renderer.is_live
        self.renderer.set_status(message, spinning=True)
        if not live:
            logging.getLogger(__name__).info("%s", message)
        try:
            yield
        finally:
            self.renderer.set_status(message, spinning=False)

    def close(self) -> None:
        """Stop the renderer and flush the summary."""
        self.renderer.close()
        self.renderer.flush_summary(self.summary)


def get_reporter() -> Reporter | None:
    """Return the process-wide Reporter, if installed."""
    return _ReporterState.current


def resolve_log_file(config: Config) -> Path:
    """Resolve the forensic log file path.

    Precedence: explicit ``config.log_file``, then ``config.log_file_env``,
    then ``config.default_log_file`` in the current working directory.

    Args:
        config: Process-wide config.

    Returns:
        Path to the log file.
    """
    if config.log_file is not None:
        return Path(config.log_file)
    if config.log_file_env:
        env = os.environ.get(config.log_file_env)
        if env:
            return Path(env)
    return Path(config.default_log_file)


def install(config: Config) -> Reporter:
    """Install runview as the process logging / UX facade.

    Sets the log record factory, selects exactly one renderer, attaches
    ``ReporterHandler`` + ``FileLogHandler`` to the root logger, quiets
    third-party loggers, and opens the renderer.

    Args:
        config: Process-wide configuration.

    Returns:
        The installed Reporter.
    """
    logging.setLogRecordFactory(record_factory)

    summary = RunSummary(app_name=config.app_name)
    console = Console()
    renderer = select_renderer(config, console, summary=summary)
    reporter = Reporter(config, renderer, summary)
    _ReporterState.current = reporter

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if config.debug else logging.INFO)

    for name in config.quiet_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)

    view_handler = ReporterHandler(reporter)
    view_handler.setLevel(logging.DEBUG if config.debug else logging.INFO)
    view_handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(view_handler)

    file_handler = FileLogHandler(resolve_log_file(config))
    file_handler.setLevel(logging.DEBUG if config.debug else logging.INFO)
    root.addHandler(file_handler)

    renderer.open()
    return reporter
