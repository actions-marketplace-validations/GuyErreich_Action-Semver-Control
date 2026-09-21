# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Constants for auto-semver configuration."""

CONFIG_FILE: str = "auto_semver_config.yml"
DEFAULT_CHANGELOG: str = "CHANGELOG.md"
PR_HIDDEN_MARKER: str = "<!-- auto-semver:pr -->"

# Housekeeping commits written by finalize / promote; filtered from changelogs.
FINALIZE_LOCK_COMMIT: str = "chore: finalize semver lock for {version}"
VERSION_METADATA_COMMIT: str = "chore: update version metadata for {version}"
INTERNAL_COMMIT_PREFIXES: tuple[str, ...] = tuple(
    template.split("{version}", 1)[0]
    for template in (FINALIZE_LOCK_COMMIT, VERSION_METADATA_COMMIT)
)
