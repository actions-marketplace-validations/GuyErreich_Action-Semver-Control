# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MPL-2.0
"""Independent plain-text forensic file sink."""

from __future__ import annotations

import logging
from logging import FileHandler, LogRecord
from pathlib import Path


class _ForensicFormatter(logging.Formatter):
    """Formatter that tolerates records without ``qualname``."""

    def format(self, record: LogRecord) -> str:
        """Ensure ``qualname`` exists before formatting.

        Args:
            record: Stdlib log record.

        Returns:
            Formatted log line.
        """
        if "qualname" not in record.__dict__:
            record.__dict__["qualname"] = record.funcName
        return super().format(record)


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
            _ForensicFormatter(
                fmt="{asctime} | {levelname:<7} | {filename}:{lineno} {qualname} | {message}",
                datefmt="%Y-%m-%d %H:%M:%S",
                style="{",
            )
        )
