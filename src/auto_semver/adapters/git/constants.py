# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Shared constants for git adapters."""

LEGACY_RELEASE_PREFIX = "release/"
DEFAULT_RELEASE_PREFIX = "auto-semver/release/"

# Git tree modes that GraphQL createCommitOnBranch cannot express (FileAddition
# always lands as 100644). REST Git Data is required for these.
_REST_TREE_MODES = frozenset({"100755", "120000"})
_KNOWN_GIT_FILE_MODES = frozenset({"100644", "100755", "120000", "040000", "160000"})
_RAW_DIFF_MIN_MODE_FIELDS = 2

# GraphQL mutation that GitHub auto-signs (verified) in one request for multiple
# file changes. Default for ordinary 100644 metadata. When the tree needs
# 100755/120000 or a dest↔source mode change, use the REST Git Data fallback
# (#286) which must still produce verification.verified=true.
_CREATE_COMMIT_ON_BRANCH_MUTATION = """
mutation($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) {
    commit {
      oid
    }
  }
}
"""
