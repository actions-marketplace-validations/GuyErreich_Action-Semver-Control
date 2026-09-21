# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Logging handlers: Live view sink and plain-text file sink."""

from __future__ import annotations

import logging
from logging import FileHandler, LogRecord
from pathlib import Path

from auto_semver.log.view import LiveView, LogEvent


class LogViewHandler(logging.Handler):
    """Forward log records into a LiveView event pane (no stream prints)."""

    def __init__(self, view: LiveView) -> None:
        """Create a handler bound to ``view``.

        Args:
            view: LiveView that receives events.
        """
        super().__init__()
        self.view = view

    def emit(self, record: LogRecord) -> None:
        """Push a LogEvent into the LiveView.

        Args:
            record: Stdlib log record.
        """
        try:
            qualname = record.__dict__.get("qualname", record.funcName)
            self.view.add_event(
                LogEvent(
                    level=record.levelno,
                    message=record.getMessage(),
                    created=record.created,
                    qualname=str(qualname) if qualname else "",
                )
            )
        except Exception:
            self.handleError(record)


class FileLogHandler(FileHandler):
    """Plain-text file handler with file:line and class.function context."""

    def __init__(self, filename: str | Path, *, mode: str = "w", encoding: str = "utf-8") -> None:
        """Open ``filename`` for forensic logging.

        Args:
            filename: Destination log path.
            mode: File open mode (default overwrite per process).
            encoding: Text encoding.
        """
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename=str(path), mode=mode, encoding=encoding)
        self.setFormatter(
            logging.Formatter(
                fmt="{asctime} | {levelname:<7} | {filename}:{lineno} {qualname} | {message}",
                datefmt="%Y-%m-%d %H:%M:%S",
                style="{",
            )
        )
