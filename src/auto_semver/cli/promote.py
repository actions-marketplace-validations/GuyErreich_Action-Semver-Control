# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""
CLI command for manually promoting versions between branches.

This command allows users to promote versions manually, with validation
against the configured promotion rules.
"""

import logging

from auto_semver.adapters.git import GitOps
from auto_semver.cli.utils import build_promotion_metadata_hook, promotion_prefer_source_paths
from auto_semver.config import Config
from auto_semver.core.semver import Version
from auto_semver.log import get_summary, log_group, status

logger = logging.getLogger(__name__)


def run(
    *,
    gitops: GitOps,
    config: Config,
    to_branch: str,
    from_branch: str | None = None,
    from_tag: str | None = None,
    dry_run: bool = False,
) -> None:
    """
    Promote a version from one branch to another directly (merge + tag).

    Args:
        gitops (GitOps): Git operations handler.
        config (Config): Loaded configuration object.
        to_branch (str): Target branch name.
        from_branch (str | None): Source branch name. Optional if tag is provided.
        from_tag (str | None): Specific tag to promote. If None, uses latest from branch.
        dry_run (bool): If True, validate only without performing git operations.

    Raises:
        ValueError: If promotion is not allowed or fails.
    """
    logger.info(f"Initiating manual promotion to {to_branch}")
    summary = get_summary()
    summary.set("command", "promote")
    summary.set("dry-run", "yes" if dry_run else "no")

    with log_group("Validate"):
        with status("Resolving source version..."):
            try:
                version, source_branch = _get_source_version(gitops, config, from_tag, from_branch)
            except Exception as e:
                raise ValueError(f"Failed to get version from source: {e}") from e

        # Validate promotion is allowed
        promotion_rule = config.data.validate_promotion(
            from_branch=source_branch,
            to_branch=to_branch,
            require_auto_promote=False,
        )

        logger.info(
            f"Promotion validated: {promotion_rule.from_branch} → {promotion_rule.to_branch}"
        )
        logger.info(f"Found version {version} to promote")
        summary.set("branches", f"{source_branch} -> {to_branch}")

        _validate_target_version(gitops, to_branch, version)

        if dry_run:
            logger.info("🧪 Dry run mode: Skipping promotion.")
            summary.set("outcome", "dry-run")
            return

        # Calculate promoted version
        target_suffix = config.data.suffixes.get(to_branch, "")
        promoted_version = Version(
            major=version.major,
            minor=version.minor,
            patch=version.patch,
            suffix=target_suffix if target_suffix else None,
        )
        summary.set("version", f"{version} -> {promoted_version}")
        logger.info(f"Promoting version {version} → {promoted_version}")

    with log_group("Merge/tag"):
        try:
            # Use tag as source if available, otherwise use branch
            merge_source = from_tag if from_tag else source_branch
            use_source_tag = bool(from_tag)

            metadata_hook = build_promotion_metadata_hook(
                config=config,
                source_branch=source_branch,
                target_branch=to_branch,
                gitops=gitops,
            )

            with status("Merging and tagging..."):
                gitops.auto_promote(
                    source_branch=merge_source,
                    target_branch=to_branch,
                    version=str(promoted_version),
                    source_version=str(version),
                    is_source_tag=use_source_tag,
                    post_merge_hook=metadata_hook,
                    prefer_source_paths=promotion_prefer_source_paths(config),
                )

            logger.info(f"✅ Promotion completed successfully: {source_branch} → {to_branch}")
            logger.info(f"Tagged {to_branch} with {promoted_version}")

        except Exception as e:
            raise ValueError(f"Failed to promote: {e}") from e


def _get_source_version(
    gitops: GitOps,
    config: Config,
    from_tag: str | None,
    from_branch: str | None,
) -> tuple[Version, str]:
    """
    Retrieve the source version and branch.

    Args:
        gitops: Git operations handler.
        config: Configuration object.
        from_tag: Optional tag to promote from.
        from_branch: Optional branch to promote from.

    Returns:
        tuple[Version, str]: The version and the source branch name.

    Raises:
        ValueError: If version cannot be determined or source branch cannot be inferred.
    """
    if from_tag:
        logger.info(f"Using specified tag: {from_tag}")

        version: Version | None
        # Try to parse version from tag name first
        try:
            version = Version.parse(from_tag)
            logger.info(f"Parsed version from tag name: {version}")
        except ValueError:
            logger.warning(
                f"Could not parse version from tag name '{from_tag}'. Falling back to lockfile."
            )
            version = gitops.get_lock_version_from_tag(tag_name=from_tag)

        if not version:
            raise ValueError(f"No version found for tag '{from_tag}'.")

        suffix = version.suffix or ""
        # Find branch that matches the version's suffix
        from_branch = None
        for branch, s in config.data.suffixes.items():
            if s == suffix:
                from_branch = branch
                break

        if not from_branch:
            raise ValueError(
                f"Could not determine source branch from version suffix '{suffix}' "
                f"in tag '{from_tag}'."
            )
        logger.info(f"Inferred source branch '{from_branch}' from tag '{from_tag}'")
        return version, from_branch

    if from_branch:
        logger.info(f"Using latest version from branch: {from_branch}")
        branch_version = gitops.get_lock_version_from_branch(branch_name=from_branch)
        if not branch_version:
            raise ValueError(
                f"No version found for branch '{from_branch}'. Ensure the branch is tagged."
            )
        return branch_version, from_branch

    raise ValueError("Either --from-branch or --from-tag must be provided.")


def _validate_target_version(gitops: GitOps, to_branch: str, source_version: Version) -> None:
    """
    Ensure the source version is greater than the target branch version.

    Args:
        gitops: Git operations handler.
        to_branch: Target branch name.
        source_version: The version being promoted.

    Raises:
        ValueError: If source version is not greater than target version.
    """
    try:
        target_version = gitops.get_lock_version_from_branch(branch_name=to_branch)
        if target_version:
            logger.info(f"Current version on {to_branch}: {target_version}")
            if source_version <= target_version:
                raise ValueError(
                    f"Cannot promote version {source_version} to {to_branch} because it is not greater "
                    f"than the current version {target_version}."
                )
        else:
            logger.info(f"No existing version found on {to_branch}. Proceeding.")
    except Exception as e:
        if isinstance(e, ValueError) and "Cannot promote" in str(e):
            raise
        logger.warning(f"Could not verify target branch version: {e}. Proceeding with caution.")
