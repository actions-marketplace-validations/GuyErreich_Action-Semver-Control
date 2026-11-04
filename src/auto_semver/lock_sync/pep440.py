# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small version normalizers for lockfiles the host CLI did not rewrite."""

from __future__ import annotations

import re

_DEV = re.compile(r"^(?P<base>\d+\.\d+\.\d+)-dev(?P<n>\d*)$")
_RC = re.compile(r"^(?P<base>\d+\.\d+\.\d+)-rc(?P<n>\d*)$")
_PRE = re.compile(r"^(?P<base>\d+\.\d+\.\d+)-(?P<kind>a|b|alpha|beta)(?P<n>\d*)$")
_PEP503_RUN = re.compile(r"[-_.]+")


def to_pep440(version: str) -> str:
    """Return the PEP 440 form of a project version string.

    ``1.8.5-dev`` becomes ``1.8.5.dev0``. Versions that are already plain
    ``major.minor.patch`` are returned unchanged.

    Args:
        version: Version text from ``pyproject.toml`` or the bump.

    Returns:
        A PEP 440 version string suitable for ``uv.lock``.
    """
    dev = _DEV.match(version)
    if dev is not None:
        number = dev.group("n") or "0"
        return f"{dev.group('base')}.dev{number}"

    rc = _RC.match(version)
    if rc is not None:
        number = rc.group("n") or "0"
        return f"{rc.group('base')}rc{number}"

    pre = _PRE.match(version)
    if pre is not None:
        kind = {"alpha": "a", "beta": "b"}.get(pre.group("kind"), pre.group("kind"))
        number = pre.group("n") or "0"
        return f"{pre.group('base')}{kind}{number}"

    return version


def pep503_name(name: str) -> str:
    """Normalize a distribution name the way ``uv.lock`` compares packages.

    Args:
        name: Project or package name.

    Returns:
        Lower-case name with runs of ``-``, ``_``, and ``.`` collapsed to ``-``.
    """
    return _PEP503_RUN.sub("-", name).lower()
