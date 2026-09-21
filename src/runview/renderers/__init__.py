# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MPL-2.0
"""Renderer factory."""

from __future__ import annotations

import os

from rich.console import Console

from runview.config import Config
from runview.renderers.base import Renderer
from runview.renderers.github import GitHubRenderer
from runview.renderers.plain import PlainRenderer
from runview.renderers.rich_live import RichRenderer
from runview.summary import RunSummary


def select_renderer(
    config: Config,
    console: Console | None = None,
    *,
    summary: RunSummary | None = None,
) -> Renderer:
    """Choose exactly one renderer from config / environment / TTY.

    Args:
        config: Process-wide runview config.
        console: Optional shared Rich console (used for TTY detection + rich).
        summary: Optional shared RunSummary for the rich renderer.

    Returns:
        A concrete renderer instance.
    """
    style = config.style
    if style == "auto":
        if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
            style = "github"
        else:
            con = console or Console()
            style = "rich" if con.is_terminal else "plain"
            if console is None and style == "rich":
                console = con

    if style == "github":
        return GitHubRenderer(config)
    if style == "plain":
        return PlainRenderer(config)
    return RichRenderer(config, console=console, summary=summary)
