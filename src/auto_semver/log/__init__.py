# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Public logging API for auto_semver."""

from auto_semver.log.github import attach_github_adapter, is_github_actions
from auto_semver.log.setup import get_summary, reset_summary, setup_logger
from auto_semver.log.summary import JobSummary
from auto_semver.log.view import get_view, log_group, status

__all__ = [
    "JobSummary",
    "attach_github_adapter",
    "get_summary",
    "get_view",
    "is_github_actions",
    "log_group",
    "reset_summary",
    "setup_logger",
    "status",
]
