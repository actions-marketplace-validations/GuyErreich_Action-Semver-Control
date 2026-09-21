# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Logger configuration: record factory and setup_logger."""

from __future__ import annotations

import logging
import os
import sys
import types
from logging import LogRecord
from pathlib import Path
from typing import Any

from rich.console import Console

from auto_semver.log.github import is_github_actions
from auto_semver.log.handler import FileLogHandler, LogViewHandler
from auto_semver.log.summary import JobSummary
from auto_semver.log.view import LiveView, set_view

old_factory = logging.getLogRecordFactory()

DEFAULT_LOG_FILE = "auto-semver.log"
_ENV_LOG_FILE = "AUTO_SEMVER_LOG_FILE"

# Third-party loggers that drown Actions job logs when root is DEBUG.
_NOISY_THIRD_PARTY_LOGGERS: tuple[str, ...] = (
    "urllib3",
    "git",
    "git.cmd",
    "github",
    "httpcore",
    "httpx",
)


class _DropWarningsAndAbove(logging.Filter):
    """Drop WARNING+ so GitHubActionsHandler is the sole sink for those levels."""

    def filter(self, record: LogRecord) -> bool:
        """Return True only for records below WARNING.

        Args:
            record: Stdlib log record.

        Returns:
            Whether the record should pass to the stream handler.
        """
        return record.levelno < logging.WARNING


def _quiet_third_party_loggers() -> None:
    """Keep HTTP/GitPython chatter out of the operator-facing console."""
    for name in _NOISY_THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


class _SummaryState:
    """Mutable holder so we avoid module-level ``global`` statements."""

    current: JobSummary | None = None


def get_summary() -> JobSummary:
    """Return the process-wide JobSummary, creating one if needed.

    Returns:
        Shared JobSummary instance.
    """
    if _SummaryState.current is None:
        _SummaryState.current = JobSummary()
    return _SummaryState.current


def reset_summary() -> JobSummary:
    """Replace the process-wide JobSummary with a fresh instance.

    Returns:
        New empty JobSummary.
    """
    _SummaryState.current = JobSummary()
    return _SummaryState.current


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
    record = old_factory(*args, **kwargs)
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


logging.setLogRecordFactory(record_factory)


def resolve_log_file(log_file: str | Path | None = None) -> Path:
    """Resolve the forensic log file path.

    Precedence: explicit ``log_file``, then ``AUTO_SEMVER_LOG_FILE``, then
    ``auto-semver.log`` in the current working directory.

    Args:
        log_file: Optional CLI ``--log-file`` value.

    Returns:
        Path to the log file.
    """
    if log_file is not None:
        return Path(log_file)
    env = os.environ.get(_ENV_LOG_FILE)
    if env:
        return Path(env)
    return Path(DEFAULT_LOG_FILE)


def setup_logger(
    debug: bool = False,
    *,
    log_file: str | Path | None = None,
    command: str = "bump",
    start_live: bool = True,
) -> logging.Logger:
    """Configure root logging with Live view + file sinks.

    On a TTY, Live owns the console (no StreamHandler). When Live does not
    start (GitHub Actions / non-TTY), a plain stdout StreamHandler is attached
    so milestone ``INFO`` lines appear inside ``::group::`` sections.

    ``--debug`` raises the file (and Live) level to DEBUG for forensics, but
    the Actions stdout stream stays at INFO with message-only formatting so
    job logs stay readable.

    Args:
        debug: Enable DEBUG level for file/Live forensics.
        log_file: Optional forensic log path.
        command: Short command name for the Live outer title.
        start_live: When True and stdout is a TTY, start the Live dashboard.

    Returns:
        Configured root logger.
    """
    summary = reset_summary()
    console = Console()

    view = LiveView(console=console, summary=summary, command=command, debug=debug)
    set_view(view)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    _quiet_third_party_loggers()

    view_handler = LogViewHandler(view)
    view_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    view_handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(view_handler)

    file_path = resolve_log_file(log_file)
    file_handler = FileLogHandler(file_path)
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    root.addHandler(file_handler)

    if start_live:
        view.start()

    # Actions / pipes: Live never starts — mirror operator INFO to stdout.
    if not view.is_running:
        stream_handler = logging.StreamHandler(sys.stdout)
        # Job logs stay narrative even when --debug feeds the file logger.
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(logging.Formatter("{message}", style="{"))
        # In Actions, WARNING+ become ::warning:: / ::error:: annotations only.
        if is_github_actions():
            stream_handler.addFilter(_DropWarningsAndAbove())
        root.addHandler(stream_handler)

    return root
