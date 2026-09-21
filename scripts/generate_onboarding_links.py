#!/usr/bin/env python3
# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate onboarding deep links for Action-Semver-Control documentation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without install
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auto_semver.setup.links import (
    MARKETPLACE_URL,
    SETUP_DOC_URL,
    app_registration_url,
    workflow_bump_deep_link,
    workflow_promote_deep_link,
)


def main() -> None:
    """Print prefilled onboarding URLs for docs and README."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True, help="Repository owner (for workflow deep links)")
    parser.add_argument("--repo", required=True, help="Repository name")
    parser.add_argument("--branch", default="master", help="Default branch")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    args = parser.parse_args()

    payload = {
        "setup_doc": SETUP_DOC_URL,
        "marketplace": MARKETPLACE_URL,
        "app_registration": app_registration_url(),
        "workflow_bump": workflow_bump_deep_link(
            owner=args.owner,
            repo=args.repo,
            branch=args.branch,
        ),
        "workflow_promote": workflow_promote_deep_link(
            owner=args.owner,
            repo=args.repo,
            branch=args.branch,
        ),
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    for key, value in payload.items():
        print(f"{key}:")
        print(f"  {value}")
        print()


if __name__ == "__main__":
    main()
