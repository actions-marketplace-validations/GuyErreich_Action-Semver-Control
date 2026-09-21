# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MPL-2.0
"""Frozen configuration and theme for runview."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from rich import box
from rich.box import Box

_DEFAULT_LEVEL_STYLES: dict[int, str] = {
    logging.DEBUG: "dim",
    logging.INFO: "cyan",
    logging.WARNING: "yellow",
    logging.ERROR: "red",
    logging.CRITICAL: "bold red",
}

_DEFAULT_LEVEL_LABELS: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRIT",
}


def _default_theme() -> Theme:
    """Build the default Theme matching the historic LiveView styles."""
    return Theme(
        level_styles=dict(_DEFAULT_LEVEL_STYLES),
        level_labels=dict(_DEFAULT_LEVEL_LABELS),
    )


@dataclass(frozen=True)
class Theme:
    """Visual tokens shared by renderers that support styling."""

    level_styles: Mapping[int, str]
    level_labels: Mapping[int, str]
    box: Box = box.ROUNDED
    accent: str = "cyan"
    muted: str = "dim"


@dataclass(frozen=True)
class Config:
    """Process-wide runview configuration."""

    app_name: str
    log_file_env: str | None = None
    default_log_file: str = "run.log"
    theme: Theme = field(default_factory=_default_theme)
    style: Literal["auto", "rich", "plain", "github"] = "auto"
    max_events: int = 50
    height_reserved: int = 14
    quiet_loggers: tuple[str, ...] = ()
    debug: bool = False
    command: str = "run"
    log_file: str | None = None
