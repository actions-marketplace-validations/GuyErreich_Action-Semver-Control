# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deprecated ``--app-id`` alias for ``--client-id``.

``--app-id`` is the old setup flag. Use ``--client-id``. Removed in 2.0.
The flag still resolves to the client id until then.
"""

from __future__ import annotations

import argparse

from auto_semver.compat._notice import warn_deprecated_once

_WARNING = "--app-id is deprecated; use --client-id. Removed in 2.0."


def add_app_id_alias(parser: argparse.ArgumentParser) -> None:
    """Register the deprecated ``--app-id`` flag on the setup parser.

    Args:
        parser: Setup subcommand parser.
    """
    parser.add_argument(
        "--app-id",
        type=str,
        help="Deprecated alias for --client-id. Removed in 2.0.",
    )


def resolve_client_id(*, client_id: str | None, app_id: str | None) -> str | None:
    """Return the client id, preferring ``client_id`` over deprecated ``app_id``.

    Warns once per process when ``app_id`` was passed.

    Args:
        client_id: GitHub App Client ID.
        app_id: Deprecated alias for ``client_id``. Removed in 2.0.

    Returns:
        The client id to use, or None when neither argument was provided.
    """
    if app_id is not None:
        warn_deprecated_once(code="app_id", message=_WARNING)
    if client_id:
        return client_id
    return app_id
