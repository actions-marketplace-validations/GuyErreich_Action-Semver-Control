# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MPL-2.0
"""Bridge stdlib logging into the active Reporter / Renderer."""

from __future__ import annotations

import logging
from logging import LogRecord
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runview.reporter import Reporter


class ReporterHandler(logging.Handler):
    """Forward log records into the Reporter's active renderer."""

    def __init__(self, reporter: Reporter) -> None:
        """Create a handler bound to ``reporter``.

        Args:
            reporter: Process Reporter that owns the renderer.
        """
        super().__init__()
        self.reporter = reporter

    def emit(self, record: LogRecord) -> None:
        """Push structured message fields into the renderer.

        Args:
            record: Stdlib log record.
        """
        try:
            qualname = record.__dict__.get("qualname", record.funcName)
            self.reporter.message(
                record.levelno,
                record.getMessage(),
                qualname=str(qualname) if qualname else "",
                created=record.created,
            )
        except Exception:
            self.handleError(record)
