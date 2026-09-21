# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Version bump mode configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BumpConfig(BaseModel):
    """Controls how version numbers increment between releases."""

    mode: Literal["classic", "cumulative"] = Field(
        default="classic",
        description=(
            "classic: semver (minor resets patch). "
            "cumulative: patch accumulates fixes, minor accumulates features without patch reset"
        ),
    )
