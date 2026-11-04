# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Emit one deprecation warning per old name per process."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_warned: set[str] = set()


def warn_deprecated_once(*, code: str, message: str) -> None:
    """Log ``message`` the first time ``code`` is used in this process.

    Args:
        code: Stable id for the old name. Later uses of the same code are silent.
        message: Warning text: old name, replacement, and the removal version.
    """
    if code in _warned:
        return
    _warned.add(code)
    logger.warning(message)


def reset_deprecation_warnings() -> None:
    """Clear the once-per-process set so tests can observe the next warning."""
    _warned.clear()
