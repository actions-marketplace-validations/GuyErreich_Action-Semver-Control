# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deprecated template name ``grouped_messages``.

``grouped_messages`` is the old template variable for commit groups.
Use ``commit_groups``. Removed in 2.0. The old name still renders until then.
"""

from __future__ import annotations

import re

from auto_semver.compat._notice import warn_deprecated_once

_GROUPED_MESSAGES = re.compile(r"\bgrouped_messages\b")

_WARNING = (
    "grouped_messages is deprecated; use commit_groups in changelog and pull request "
    "templates. Removed in 2.0."
)


def apply_grouped_messages_alias[Value](
    template: str,
    template_vars: dict[str, Value],
) -> dict[str, Value]:
    """Copy ``commit_groups`` onto ``grouped_messages`` when the template names it.

    Warns once per process when the template text names ``grouped_messages``.
    A template that only uses ``commit_groups`` is unchanged and silent.

    Args:
        template: Jinja template source.
        template_vars: Variables passed to the template.

    Returns:
        The same mapping, or a copy that also defines ``grouped_messages``.
    """
    if _GROUPED_MESSAGES.search(template) is None:
        return template_vars
    warn_deprecated_once(code="grouped_messages", message=_WARNING)
    if "grouped_messages" in template_vars or "commit_groups" not in template_vars:
        return template_vars
    aliased = dict(template_vars)
    aliased["grouped_messages"] = template_vars["commit_groups"]
    return aliased
