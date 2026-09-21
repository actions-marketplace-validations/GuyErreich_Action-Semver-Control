#!/usr/bin/env python3
# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Update copyright year ranges across LICENSE, licenserc, and source headers."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

START_YEAR = 2025
COPYRIGHT_RE = re.compile(r"Copyright \(c\) 20\d{2}(?:-20\d{2})? Guy Erreich")

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("src", "scripts", ".github")
SCAN_FILES = ("action.yml", "LICENSE", ".licenserc.yaml", ".licenserc.runview.yaml")
TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".md", ".toml", ".txt", ""}


def copyright_line(end_year: int) -> str:
    """Return the canonical copyright line for the given end year."""
    if end_year < START_YEAR:
        raise ValueError(f"end_year {end_year} is before start year {START_YEAR}")
    if end_year == START_YEAR:
        return f"Copyright (c) {START_YEAR} Guy Erreich"
    return f"Copyright (c) {START_YEAR}-{end_year} Guy Erreich"


def rewrite_text(text: str, end_year: int) -> str:
    """Replace copyright year ranges in text with the canonical form."""
    replacement = copyright_line(end_year)
    return COPYRIGHT_RE.sub(replacement, text)


def iter_files() -> list[Path]:
    """Collect files that may contain copyright notices."""
    files: list[Path] = []
    for name in SCAN_FILES:
        path = ROOT / name
        if path.is_file():
            files.append(path)
    for rel in SCAN_ROOTS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in TEXT_SUFFIXES or path.name in {
                "LICENSE",
                "action.yml",
                ".licenserc.yaml",
                ".licenserc.runview.yaml",
            }:
                # Skip consumer templates (license-check ignores them too).
                if "templates" in path.parts and path.suffix in {".yml", ".yaml"}:
                    continue
                if path.suffix == ".json" or path.name == "py.typed":
                    continue
                if "__pycache__" in path.parts:
                    continue
                files.append(path)
    return sorted(set(files))


def update_files(*, end_year: int, dry_run: bool) -> list[Path]:
    """Update copyright years; return paths that would change or changed."""
    changed: list[Path] = []
    for path in iter_files():
        original = path.read_text(encoding="utf-8")
        updated = rewrite_text(original, end_year)
        if updated == original:
            continue
        changed.append(path)
        if not dry_run:
            path.write_text(updated, encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="Ending copyright year (default: current UTC calendar year)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print files that would change without writing",
    )
    args = parser.parse_args(argv)

    end_year = args.end_year
    if end_year is None:
        end_year = datetime.now(UTC).year

    changed = update_files(end_year=end_year, dry_run=args.dry_run)
    line = copyright_line(end_year)
    print(f"target_copyright={line}")
    print(f"changed_files={len(changed)}")
    for path in changed:
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
