# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Commit grouping settings and group definitions."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from auto_semver.config._models.commit_group import CommitGroupConfig

DEFAULT_IGNORE_LINE_PATTERNS: list[str] = [
    r"^\[[ xX]\]",
    r"^Co-authored-by:",
    r"^Made with \[Cursor\]",
    r"^---------",
]


class CommitGroupsConfig(BaseModel):
    """Commit message grouping settings plus pattern-defined groups."""

    summary_mode: Literal["header_only", "expand_body"] = Field(
        default="header_only",
        description="header_only emits one entry per git commit; expand_body parses bullets/sections",
    )
    ignore_line_patterns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_IGNORE_LINE_PATTERNS),
        description="Regex patterns for lines dropped before grouping (expand_body mode)",
    )
    groups: list[CommitGroupConfig] = Field(
        default_factory=list,
        description="Pattern-defined commit groups for changelog and release PR templates",
    )

    @field_validator("ignore_line_patterns")
    @classmethod
    def validate_ignore_patterns(cls, patterns: list[str]) -> list[str]:
        """Validate ignore-line regex patterns."""
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as err:
                msg = f"Invalid ignore_line_patterns regex '{pattern}': {err}"
                raise ValueError(msg) from err
        return patterns

    @classmethod
    def from_yaml(cls, value: object | None) -> CommitGroupsConfig:
        """Parse commit_groups from legacy list or structured dict YAML."""
        if value is None:
            return cls()
        if isinstance(value, list):
            return cls(groups=value)
        if isinstance(value, dict):
            groups = value.get("groups", [])
            settings = {k: v for k, v in value.items() if k != "groups"}
            return cls(groups=groups, **settings)
        msg = f"commit_groups must be a list or mapping, got {type(value).__name__}"
        raise TypeError(msg)
