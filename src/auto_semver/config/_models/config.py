# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Main configuration data model."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from auto_semver.config._models.bump import BumpConfig
from auto_semver.config._models.changelog import ChangelogConfig
from auto_semver.config._models.commit_group import CommitGroups
from auto_semver.config._models.commit_groups import CommitGroupsConfig
from auto_semver.config._models.promotion import PromotionRule
from auto_semver.config._models.pull_request import PullRequestConfig
from auto_semver.config._models.release import ReleaseConfig
from auto_semver.core.semver import Version

logger = logging.getLogger(__name__)


class ConfigData(BaseModel):
    """
    Holds all validated configuration values loaded from auto_semver_config.yml.

    This model represents the user-defined configuration for the auto-semver
    process, including versioning behavior, changelog generation, PR metadata, and
    supported branch strategies. It ensures that required fields are present and typed.

    Attributes:
        start_version (Version): The default version to use if no version file is found.
        suffixes (dict[str, str]): Mapping of target branches to version suffixes
            (e.g., {"main": "", "dev": "-dev"}).
        version_files (list[str]): List of files to update with the new version string.
        pull_request (PullRequestConfig): Configuration for the pull request title, body, and labels.
        changelog (_ChangelogConfig): Changelog file behavior and formatting templates.

    """

    start_version: Version = Field(
        default_factory=lambda: Version.parse("0.1.0"), description="Optional start_version."
    )
    suffixes: dict[str, str] = Field(..., description="Required branch suffix mapping.")
    promotions: list[PromotionRule] = Field(
        ..., description="Allowed branch promotion rules (from → to)."
    )
    version_files: list[str] = Field(
        default=["version.txt"], description="Optional files that hold version format to update."
    )
    commit_groups: CommitGroupsConfig = Field(
        default_factory=CommitGroupsConfig,
        description="Commit grouping settings and pattern-defined groups for templates",
    )
    release: ReleaseConfig = Field(
        default_factory=ReleaseConfig,
        description="Release branch lifecycle (single vs multi, prefix, cleanup)",
    )
    bump: BumpConfig = Field(
        default_factory=BumpConfig,
        description="Version bump mode (classic semver vs cumulative)",
    )
    pull_request: PullRequestConfig
    changelog: ChangelogConfig

    @field_validator("commit_groups", mode="before")
    @classmethod
    def parse_commit_groups(cls, value: CommitGroupsConfig | object | None) -> CommitGroupsConfig:
        """Accept legacy YAML list format or structured commit_groups mapping."""
        if isinstance(value, CommitGroupsConfig):
            return value
        return CommitGroupsConfig.from_yaml(value)

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("start_version", mode="before")
    @classmethod
    def validate_version(cls, value: str | Version) -> Version:
        """Validate and parse the start_version field."""
        if isinstance(value, Version):
            return value
        try:
            return Version.parse(value)
        except ValueError:
            raise

    @field_serializer("start_version")
    def serialize_version(self, value: Version) -> str:
        """Serialize Version objects to strings."""
        return str(value)

    @model_validator(mode="after")
    def validate_promotions_have_suffixes(self) -> ConfigData:
        """Validate that all branches in promotion rules have suffix definitions."""
        # Validate that all promotion targets have suffixes
        missing_suffixes = {
            rule.to_branch for rule in self.promotions if rule.to_branch not in self.suffixes
        }

        if missing_suffixes:
            raise ValueError(
                f"The following promotion targets are missing suffix definitions: {sorted(missing_suffixes)}"
            )

        # Validate no reverse rules exist
        seen_pairs = set()
        for rule in self.promotions:
            reverse = (rule.to_branch, rule.from_branch)
            if reverse in seen_pairs:
                raise ValueError(
                    f"Invalid promotion configuration: reverse rule found for "
                    f"'{rule.from_branch} → {rule.to_branch}'"
                )
            seen_pairs.add((rule.from_branch, rule.to_branch))

        return self

    @model_validator(mode="after")
    def validate_unique_patterns(self) -> ConfigData:
        """
        Validate that regex patterns are unique across all commit groups.

        This ensures deterministic grouping of commits. If a pattern appears
        in multiple groups, it creates ambiguity about which group a commit
        should belong to.
        """
        seen_patterns: dict[str, str] = {}

        for group in self.commit_groups.groups:
            for pattern in group.patterns:
                # We check for exact string matches.
                # Semantically identical regexes (e.g. [a-z] vs [a-z]) are hard to detect,
                # but catching exact duplicates prevents most configuration errors.
                if pattern in seen_patterns:
                    existing_group = seen_patterns[pattern]
                    # Allow duplicate patterns only if they are the catch-all ".*"
                    # strictly speaking catch-all should also be unique, but let's be strict for now.
                    if pattern == ".*":
                        logger.debug("Duplicate catch-all pattern '.*' detected, permitting.")
                        continue

                    raise ValueError(
                        f"Duplicate pattern '{pattern}' found in groups: "
                        f"'{existing_group}' and '{group.title}'. "
                        "Patterns must be unique to ensure deterministic grouping."
                    )
                seen_patterns[pattern] = group.title

        return self

    def group_commit_messages(self, messages: list[str]) -> CommitGroups:
        """
        Group commit messages using the configured commit groups.

        Args:
            messages: List of commit messages to group

        Returns:
            CommitGroups: list of CommitGroup dataclasses for template rendering.
        """
        # Lazy import: config package init must not pull core.commits at module load.
        from auto_semver.core.commits.grouper import CommitGrouper  # noqa: PLC0415

        return CommitGrouper.group_messages(messages, self.commit_groups)

    def find_promotion_rule(self, *, from_branch: str, to_branch: str) -> PromotionRule | None:
        """
        Find a promotion rule that allows promotion from source to target branch.

        Args:
            from_branch: Source branch name
            to_branch: Target branch name

        Returns:
            PromotionRule if found, None otherwise
        """
        for rule in self.promotions:
            if rule.from_branch == from_branch and rule.to_branch == to_branch:
                return rule
        return None

    def validate_promotion(
        self, *, from_branch: str, to_branch: str, require_auto_promote: bool = False
    ) -> PromotionRule:
        """
        Validate that a promotion between branches is allowed by configuration.

        Args:
            from_branch: Source branch name
            to_branch: Target branch name
            require_auto_promote: If True, only allow promotions with auto_promote=True

        Returns:
            PromotionRule: The matching promotion rule

        Raises:
            ValueError: If promotion is not allowed
        """
        # Check if both branches are configured
        if from_branch not in self.suffixes:
            raise ValueError(f"Source branch '{from_branch}' is not configured in suffixes")

        if to_branch not in self.suffixes:
            raise ValueError(f"Target branch '{to_branch}' is not configured in suffixes")

        # Find promotion rule
        rule = self.find_promotion_rule(from_branch=from_branch, to_branch=to_branch)

        if rule is None:
            raise ValueError(
                f"No promotion rule found from '{from_branch}' to '{to_branch}'. "
                f"Available rules: {[(r.from_branch, r.to_branch) for r in self.promotions]}"
            )

        # Check auto_promote requirement if specified
        if require_auto_promote and not rule.auto_promote:
            raise ValueError(
                f"Promotion from '{from_branch}' to '{to_branch}' is not configured for auto-promotion"
            )

        logger.info(
            f"Promotion validated: {from_branch} → {to_branch} (auto_promote={rule.auto_promote})"
        )
        return rule

    def get_auto_promotion_targets(self, *, from_branch: str) -> list[str]:
        """
        Get all target branches that can be auto-promoted from the given branch.

        Args:
            from_branch: Source branch name

        Returns:
            List of target branch names that have auto_promote=True
        """
        targets = []
        for rule in self.promotions:
            if rule.from_branch == from_branch and rule.auto_promote:
                targets.append(rule.to_branch)

        return targets
