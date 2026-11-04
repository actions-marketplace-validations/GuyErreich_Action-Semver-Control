#!/usr/bin/env python3
# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Match pull request paths against newline-separated glob patterns."""

from __future__ import annotations

import os
import re
import sys

_ANNOTATION_NAME_LIMIT = 15


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a glob. ``*`` stays in one path segment. ``**`` crosses directories."""
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
            continue
        if pattern.startswith("**", index):
            parts.append(".*")
            index += 2
            continue
        char = pattern[index]
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
        index += 1
    return re.compile("".join(parts) + r"\Z")


def path_matches(path: str, pattern: str) -> bool:
    """Return whether ``path`` matches one glob pattern.

    A pattern with no slash matches the file name in any directory, so ``*.py``
    matches ``src/app.py``. A pattern with a slash matches the full path.
    """
    normalized = path.replace("\\", "/").lstrip("/")
    cleaned = pattern.strip().replace("\\", "/").lstrip("/")
    if not cleaned or cleaned.startswith("#"):
        return False
    regex = _glob_to_regex(cleaned)
    if regex.fullmatch(normalized):
        return True
    if "/" not in cleaned:
        return regex.fullmatch(normalized.rsplit("/", 1)[-1]) is not None
    return False


def _pattern_lines(patterns: str) -> list[str]:
    return [
        line.strip()
        for line in patterns.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def matched_paths(paths: list[str], patterns: str) -> list[str]:
    """Return the changed paths that match at least one pattern."""
    pattern_lines = _pattern_lines(patterns)
    found: list[str] = []
    for path in paths:
        if any(path_matches(path, pattern) for pattern in pattern_lines):
            found.append(path)
    return found


def _escape_message(value: str) -> str:
    """Escape text placed after ``::`` in a workflow command."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    """Escape a workflow command property such as ``title``."""
    return _escape_message(value).replace(":", "%3A").replace(",", "%2C")


def _notice(title: str, message: str) -> str:
    return f"::notice title={_escape_property(title)}::{_escape_message(message)}"


def _group(title: str, lines: list[str]) -> list[str]:
    body = [f"- {line}" for line in lines] or ["- (none)"]
    return [f"::group::{title}", *body, "::endgroup::"]


def _name_list(names: list[str]) -> str:
    if len(names) <= _ANNOTATION_NAME_LIMIT:
        return ", ".join(names)
    shown = ", ".join(names[:_ANNOTATION_NAME_LIMIT])
    return f"{shown}, and {len(names) - _ANNOTATION_NAME_LIMIT} more"


def _decision_notice(paths: list[str], hits: list[str]) -> str:
    if hits:
        message = (
            f"{len(hits)} of {len(paths)} pull request files matched ({_name_list(hits)}). "
            "Downstream steps will run."
        )
        return _notice("Changed paths matched", message)
    if paths:
        message = (
            f"0 of {len(paths)} pull request files matched ({_name_list(paths)}). "
            "Downstream steps will skip."
        )
    else:
        message = "The pull request does not change any files. Downstream steps will skip."
    return _notice("Changed paths did not match", message)


def workflow_log(paths: list[str], patterns: str) -> tuple[bool, str]:
    """Build the log groups and annotation for one path check.

    Returns:
        Whether any path matched, and the workflow commands to write to stdout.
    """
    hits = matched_paths(paths, patterns)
    lines = [
        *_group(f"Patterns ({len(_pattern_lines(patterns))})", _pattern_lines(patterns)),
        *_group(f"Pull request files ({len(paths)})", paths),
        *_group(f"Matched files ({len(hits)})", hits),
        _decision_notice(paths, hits),
    ]
    return bool(hits), "\n".join(lines) + "\n"


def main() -> int:
    """Read paths on stdin, log the decision, and write ``matched``."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print("GITHUB_OUTPUT is not set", file=sys.stderr)
        return 1
    patterns = os.environ.get("PATTERNS", "")
    paths = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
    matched, log = workflow_log(paths, patterns)
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"matched={'true' if matched else 'false'}\n")
    sys.stdout.write(log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
