# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Promotion rule models."""

import re

from pydantic import BaseModel, Field, field_validator

# Constants for branch name validation
MIN_BRANCH_NAME_LENGTH = 1
MAX_BRANCH_NAME_LENGTH = 250

# Git branch name validation pattern
BRANCH_NAME_PATTERN = re.compile(
    r"^(?!.*(?:\.lock$|\.lock/|/\.|\.{2}|@{|\\))"  # Cannot end with .lock, contain /.., @{, or \
    r"(?!.*(?://|^/|/$))"  # Cannot contain //, start/end with /
    r"(?![~^:\s?*\[\]])"  # Cannot start with ~^: or contain space?*[]
    r"[^\000-\037\177~^:\s?*\[\]]*"  # Cannot contain control chars, space, ~^:?*[]
    r"(?<!\.lock)$"  # Cannot end with .lock
)

type BranchName = str


class PromotionRule(BaseModel):
    """Represents a rule for promoting versions between branches."""

    from_branch: BranchName = Field(
        ...,
        min_length=MIN_BRANCH_NAME_LENGTH,
        max_length=MAX_BRANCH_NAME_LENGTH,
        description="Source branch name",
    )

    to_branch: BranchName = Field(
        ...,
        min_length=MIN_BRANCH_NAME_LENGTH,
        max_length=MAX_BRANCH_NAME_LENGTH,
        description="Target branch name",
    )

    auto_promote: bool = Field(
        default=False,
        description=(
            "Whether to automatically promote (direct branch update + tag) after "
            "tagging the source branch. Does not open a promotion PR."
        ),
    )

    @field_validator("from_branch", "to_branch")
    @classmethod
    def validate_branch_name(cls, value: str) -> str:
        """
        Validate that the branch name follows Git branch naming rules.

        Args:
            value: The branch name to validate.

        Returns:
            str: The validated branch name.

        Raises:
            ValueError: If the branch name is invalid.
        """
        if not BRANCH_NAME_PATTERN.match(value):
            raise ValueError(
                f"Invalid branch name '{value}'. Branch names must follow Git naming rules: "
                "cannot contain spaces, control characters, or special sequences like //, .., "
                "cannot start with /, cannot end with .lock, etc."
            )
        return value
