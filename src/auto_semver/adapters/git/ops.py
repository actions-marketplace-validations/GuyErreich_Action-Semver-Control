# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""GitOps facade composing local, verified, promote, and release-PR parts."""

from __future__ import annotations

from auto_semver.adapters.git.local import GitLocal
from auto_semver.adapters.git.promote import GitPromote
from auto_semver.adapters.git.release_pr import GitReleasePr
from auto_semver.adapters.git.verified import GitVerifiedCommits


class GitOps(GitLocal, GitVerifiedCommits, GitPromote, GitReleasePr):
    """Unified Git / GitHub operations for auto-semver pipelines."""

    pass
