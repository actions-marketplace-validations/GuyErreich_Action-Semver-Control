# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Release branch lifecycle configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DEFAULT_BRANCH_PREFIX = "auto-semver/release/"


class ReleaseConfig(BaseModel):
    """Controls release branch naming, retention, and cleanup behavior."""

    strategy: Literal["single", "multi"] = Field(
        default="single",
        description="single closes superseded release PRs; multi keeps siblings open",
    )
    branch_prefix: str = Field(
        default=DEFAULT_BRANCH_PREFIX,
        description="Prefix auto-semver uses when creating release branches",
    )
    cleanup_merged: bool = Field(
        default=True,
        description=(
            "Delete owned release branches when superseded in single mode and after finalize"
        ),
    )
