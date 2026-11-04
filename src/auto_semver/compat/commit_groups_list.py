# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deprecated bare-list form of ``commit_groups``.

A YAML list of groups is the old shape. Use a mapping with a ``groups`` key.
Removed in 2.0. A list still loads as ``groups`` until then.
"""

from __future__ import annotations

from auto_semver.compat._notice import warn_deprecated_once

_WARNING = (
    "commit_groups as a YAML list is deprecated; use a mapping with a groups key. "
    "Removed in 2.0."
)


def accept_legacy_commit_groups_list[Group](groups: list[Group]) -> list[Group]:
    """Warn once and return a legacy ``commit_groups`` list to store as ``groups``.

    Args:
        groups: Group entries from the old YAML list shape.

    Returns:
        The same list.
    """
    warn_deprecated_once(code="commit_groups_list", message=_WARNING)
    return groups
