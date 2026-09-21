# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""
Handles the finalization step of the auto-semver workflow.

This script is responsible for verifying that the merged PR is
an auto-generated release PR and, if so, creating and pushing a Git tag.
After tagging, it checks for auto-promotion rules and promotes directly
(App bypass + verified tip update + destination tag), not via a promotion PR.
"""

import logging

from auto_semver.adapters.git import GitOps
from auto_semver.adapters.github import GitHubEvent
from auto_semver.cli.utils import build_promotion_metadata_hook, promotion_prefer_source_paths
from auto_semver.config import Config
from auto_semver.config.constants import FINALIZE_LOCK_COMMIT
from auto_semver.core.semver import SemverLock, Version
from auto_semver.log import get_summary, log_group, status

logger = logging.getLogger(__package__)


def create_and_push_tag(*, gitops: GitOps, event: GitHubEvent, config: Config) -> tuple[str, str]:
    """
    Create and push a Git tag for the finalized version.

    Args:
        gitops (GitOps): Git operations handler.
        event (GitHubEvent): GitHub event wrapper for PR metadata.
        config (Config): Loaded configuration object.

    Returns:
        tuple[str, str]: A tuple of (target_branch, version) that was tagged.

    Raises:
        ValueError: If tagging is not allowed on the target branch.
    """
    target_branch: str = event.get_target_branch_name()
    version = SemverLock.load_from_file().version
    allowed_targets = list(config.data.suffixes.keys())

    logger.info("Tagging branch")

    if target_branch not in allowed_targets:
        logger.debug(
            f"Target branch '{target_branch}' not allowed for tagging. Allowed: {allowed_targets}"
        )
        raise ValueError(f"Tagging not allowed on branch '{target_branch}'.")

    tag = gitops.tag(tag=str(version), branch=target_branch)
    gitops.push(branch_name=tag)

    return target_branch, str(version)


def _rewrite_baseline_lock(*, gitops: GitOps, event: GitHubEvent, version: str) -> None:
    """Strip release-only lock markers from the integration branch after merge."""
    merge_sha = event.get_merged_commit_sha()
    lock = SemverLock.load_from_file()
    lock.version = Version.parse(version)
    lock.as_finalized_baseline(merge_sha=merge_sha)
    lock.save_to_file()
    gitops.add([lock.path])
    gitops.commit(FINALIZE_LOCK_COMMIT.format(version=version))


def _cleanup_release_branch(
    *,
    gitops: GitOps,
    event: GitHubEvent,
    config: Config,
    github_token: str | None,
) -> None:
    """Delete merged release branch when configured and ownership checks pass."""
    release_cfg = config.data.release
    if not release_cfg.cleanup_merged:
        logger.info("release.cleanup_merged=false — skipping branch deletion")
        return

    if not github_token:
        logger.warning("No GitHub token; skipping release branch cleanup")
        return

    source_branch = event.get_source_branch_name()
    owned, reason = gitops._is_closeable_release_pr(
        branch_name=source_branch,
        github_token=github_token,
        branch_prefix=release_cfg.branch_prefix,
        labels=config.data.pull_request.labels,
    )
    if not owned:
        logger.info("Skipping release branch delete for %s: %s", source_branch, reason)
        return

    gitops.delete_branch(branch_name=source_branch)
    logger.info("Deleted merged release branch %s", source_branch)


def create_auto_promotion_prs(
    *,
    gitops: GitOps,
    event: GitHubEvent,
    config: Config,
    target_branch: str,
    version: str,
    github_token: str | None = None,
) -> None:
    """
    Auto-promote to configured target branches after tagging.

    Despite the historical name, this does **not** open promotion PRs. It calls
    ``gitops.auto_promote`` so the App token can update each target branch and
    create the destination tag in one shot.

    Args:
        gitops (GitOps): Git operations handler.
        event (GitHubEvent): GitHub event wrapper for PR metadata.
        config (Config): Loaded configuration object.
        target_branch (str): The branch that was just tagged.
        version (str): The version that was just tagged.
        github_token (str, optional): Reserved for release-branch cleanup callers.
    """
    logger.info(f"Successfully tagged {target_branch} with {version}")

    auto_targets = config.data.get_auto_promotion_targets(from_branch=target_branch)

    if not auto_targets:
        logger.info(f"No auto-promotion rules found for branch '{target_branch}'")
        return

    for to_branch in auto_targets:
        logger.info(f"Auto-promoting {target_branch} → {to_branch}")

        target_suffix = config.data.suffixes.get(to_branch, "")

        current_version = Version.parse(version)
        promoted_version = Version(
            major=current_version.major,
            minor=current_version.minor,
            patch=current_version.patch,
            suffix=target_suffix if target_suffix else None,
        )

        logger.info(f"Promoting version {version} → {promoted_version}")

        metadata_hook = build_promotion_metadata_hook(
            config=config,
            source_branch=target_branch,
            target_branch=to_branch,
            gitops=gitops,
        )

        try:
            gitops.auto_promote(
                source_branch=str(version),
                target_branch=to_branch,
                version=str(promoted_version),
                source_version=version,
                is_source_tag=True,
                post_merge_hook=metadata_hook,
                prefer_source_paths=promotion_prefer_source_paths(config),
            )
        except Exception as e:
            logger.error(f"❌ Failed to auto-promote {target_branch} → {to_branch}: {e}")
            raise RuntimeError(
                f"Auto-promotion failed for {target_branch} → {to_branch}: {e}"
            ) from e

        logger.info(f"✅ Auto-promotion completed: {target_branch} → {to_branch}")


def run(
    *, gitops: GitOps, event: GitHubEvent, config: Config, github_token: str | None = None
) -> None:
    """
    Finalize the release process by tagging the merged version.

    After tagging, check for auto-promotion rules and promote directly when configured.

    Args:
        gitops (GitOps): Git operations handler.
        event (GitHubEvent): GitHub event wrapper for PR metadata.
        config (Config): Loaded configuration object.
        github_token (str, optional): GitHub token for App-backed git ops / cleanup.

    """
    summary = get_summary()

    with log_group("Tag"):
        with status("Creating and pushing tag..."):
            target_branch, version = create_and_push_tag(gitops=gitops, event=event, config=config)
        summary.set("branches", f"-> {target_branch}")
        summary.set("version", version)

    with log_group("Baseline lock"):
        try:
            with status("Rewriting baseline lock..."):
                _rewrite_baseline_lock(gitops=gitops, event=event, version=version)
        except Exception as err:
            logger.warning("Failed to rewrite baseline lock on %s: %s", target_branch, err)

    with log_group("Cleanup"):
        with status("Cleaning up release branch..."):
            _cleanup_release_branch(
                gitops=gitops,
                event=event,
                config=config,
                github_token=github_token,
            )

    with log_group("Auto-promote"):
        with status("Running auto-promotion..."):
            create_auto_promotion_prs(
                gitops=gitops,
                event=event,
                config=config,
                target_branch=target_branch,
                version=version,
                github_token=github_token,
            )
