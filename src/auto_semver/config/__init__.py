# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Public config package entry point.

Import ``Config`` and schema types from here — never from ``config._models``.
``_models`` is a private implementation detail of this package.
"""

from auto_semver.config._models import (
    BranchName,
    BumpConfig,
    ChangelogConfig,
    Commit,
    CommitGroup,
    CommitGroupConfig,
    CommitGroups,
    CommitGroupsConfig,
    ConfigData,
    PromotionRule,
    PullRequestConfig,
    RegexPattern,
    ReleaseConfig,
)
from auto_semver.config._models.changelog import ChangelogTemplateVars
from auto_semver.config._models.pull_request import PullRequestTemplateVars
from auto_semver.config.config import Config

__all__ = [
    "BranchName",
    "BumpConfig",
    "ChangelogConfig",
    "ChangelogTemplateVars",
    "Commit",
    "CommitGroup",
    "CommitGroupConfig",
    "CommitGroups",
    "CommitGroupsConfig",
    "Config",
    "ConfigData",
    "PromotionRule",
    "PullRequestConfig",
    "PullRequestTemplateVars",
    "RegexPattern",
    "ReleaseConfig",
]
