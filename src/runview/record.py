# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MPL-2.0
"""Custom LogRecord factory (installed by ``install``, not at import)."""

from __future__ import annotations

import logging
import sys
import types
from logging import LogRecord
from typing import Any

_old_factory = logging.getLogRecordFactory()


def record_factory(*args: Any, **kwargs: Any) -> LogRecord:
    """Create a log record with ``qualname`` and ``full_name`` attributes.

    ``qualname`` uses the caller frame's ``co_qualname`` (class.method) when
    available so the file logger can show forensic location detail.

    Args:
        *args: Positional args for the original factory.
        **kwargs: Keyword args for the original factory.

    Returns:
        LogRecord with ``qualname`` and ``full_name`` set.
    """
    record = _old_factory(*args, **kwargs)
    qualname = record.funcName
    frame: types.FrameType | None = sys._getframe(1)
    while frame is not None:
        module = frame.f_globals.get("__name__", "")
        if not module.startswith("logging"):
            code = frame.f_code
            qualname = getattr(code, "co_qualname", code.co_name)
            break
        frame = frame.f_back
    record.__dict__["qualname"] = qualname
    record.__dict__["full_name"] = f"[{record.name}.{record.module}][{record.funcName}]"
    return record
