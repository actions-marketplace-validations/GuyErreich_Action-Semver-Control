# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Version bump CLI operations for auto_semver."""

import datetime
import logging

import yaml

from auto_semver.adapters.git import GitOps
from auto_semver.adapters.github import GitHubEvent
from auto_semver.config import Config
from auto_semver.core.changelog.manager import ChangelogManager
from auto_semver.core.commits.grouper import CommitGrouper
from auto_semver.core.pr.github_builder import GitHubPRBuilder, GitHubPRTemplateVariables
from auto_semver.core.semver import Version
from auto_semver.core.semver.lock import SemverLock
from auto_semver.core.semver.updater import VersionFileUpdater
from auto_semver.core.semver.version import BumpCounts
from auto_semver.log import get_summary, log_group, status

logger = logging.getLogger(__package__)


def _detect_tag_source_branch(*, version: Version, config: Config) -> str | None:
    """
    Detect which branch a version tag belongs to based on its suffix.

    This function maps the version's suffix back to the source branch using
    the suffixes configuration.

    Args:
        version: The version object with a suffix
        config: The configuration containing suffix mappings

    Returns:
        The branch name that corresponds to the version's suffix, or None if not found
    """
    target_suffix = version.suffix or ""

    for branch, suffix in config.data.suffixes.items():
        if suffix == target_suffix:
            return branch

    return None


def _is_tag_promotion_scenario(*, version: Version, target_branch: str, config: Config) -> bool:
    """
    Check if the current scenario represents a tag promotion.

    A tag promotion scenario occurs when:
    1. We have an existing version with a suffix that maps to a source branch
    2. There's a promotion rule from that source branch to the target branch
    3. This should result in suffix change only, no version bump

    Args:
        version: The current version object
        target_branch: The target branch of the PR
        config: The configuration containing promotion rules and suffixes

    Returns:
        True if this is a tag promotion scenario, False otherwise

    Raises:
        ValueError: If the version has a suffix that doesn't match any configured branch
    """
    source_branch = _detect_tag_source_branch(version=version, config=config)

    if source_branch is None:
        suffix_display = f"'{version.suffix}'" if version.suffix else "None (empty)"
        error_msg = (
            f"Version {version} has suffix {suffix_display} that doesn't match any "
            f"configured branch suffix in: {list(config.data.suffixes.values())}"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    for rule in config.data.promotions:
        if rule.from_branch == source_branch and rule.to_branch == target_branch:
            logger.info(f"Tag promotion detected: {version} from {source_branch} → {target_branch}")
            return True

    logger.debug(f"No promotion rule found from {source_branch} → {target_branch}")
    return False


def _resolve_baseline_version(
    *,
    gitops: GitOps,
    config: Config,
    target_branch: str,
    github_token: str,
) -> Version:
    """Resolve starting version from dev lock and open release PR (single mode)."""
    gitops.fetch()
    dev_version = gitops.get_lock_version_from_branch(target_branch)

    if not dev_version:
        try:
            with open("version.txt") as f:
                dev_version = Version.parse(f.read().strip())
        except FileNotFoundError:
            dev_version = config.data.start_version

    baseline = dev_version
    release_cfg = config.data.release

    if release_cfg.strategy == "single":
        open_release = gitops.get_open_release_version(
            github_token=github_token,
            target_branch=target_branch,
            branch_prefix=release_cfg.branch_prefix,
            labels=config.data.pull_request.labels,
        )
        if open_release and open_release > baseline:
            logger.info(
                "Using open release version %s as baseline (dev lock: %s)",
                open_release,
                baseline,
            )
            baseline = open_release

    return Version(
        major=baseline.major,
        minor=baseline.minor,
        patch=baseline.patch,
        suffix=baseline.suffix,
    )


def _apply_version_bump(
    *,
    version: Version,
    config: Config,
    current_branch: str,
    gitops: GitOps,
    target_branch: str,
    baseline_sha: str | None,
    github_token: str,
) -> BumpCounts | None:
    """Apply classic or cumulative bump rules."""
    if config.data.bump.mode == "cumulative":
        base_sha = baseline_sha or ""
        if not base_sha:
            logger.warning("No baseline SHA for cumulative bump; using current branch only")
            branch_names = [current_branch]
        else:
            branch_names = gitops.get_merged_source_branches_since(
                base_sha=base_sha,
                target_branch=target_branch,
                github_token=github_token,
            )
            if current_branch not in branch_names:
                branch_names.append(current_branch)
        return version.bump_cumulative(branch_names=branch_names)

    version.bump(branch_name=current_branch)
    return None


def _push_release_branch(
    *,
    gitops: GitOps,
    release_branch_name: str,
    force: bool = True,
) -> None:
    """Push release branch with one retry after re-fetch on rejection."""
    try:
        gitops.push(branch_name=release_branch_name, force=force)
    except RuntimeError as err:
        if "REJECTED" not in str(err).upper() and "rejected" not in str(err).lower():
            raise
        logger.warning("Push rejected; re-fetching and retrying once: %s", err)
        gitops.fetch()
        gitops.push(branch_name=release_branch_name, force=force)


def _supersede_old_releases_in_single_mode(
    *,
    gitops: GitOps,
    config: Config,
    github_token: str,
    target_branch: str,
    release_branch_name: str,
) -> None:
    """Close and optionally delete superseded release PRs/branches in single mode."""
    release_cfg = config.data.release
    logger.info("Closing old release PRs...")
    gitops.close_old_release_prs(
        github_token=github_token,
        target_branch=target_branch,
        labels=config.data.pull_request.labels,
        branch_prefix=release_cfg.branch_prefix,
        exclude_branch=release_branch_name,
        delete_branches=release_cfg.cleanup_merged,
    )
    if release_cfg.cleanup_merged:
        logger.info("Cleaning stale release branches...")
        gitops.cleanup_stale_release_branches(
            github_token=github_token,
            target_branch=target_branch,
            labels=config.data.pull_request.labels,
            branch_prefix=release_cfg.branch_prefix,
            exclude_branch=release_branch_name,
        )


def run(*, gitops: GitOps, event: GitHubEvent, config: Config, github_token: str) -> None:
    """
    Run the bump workflow.

    Args:
        gitops (GitOps): GitOps object.
        event (GitHubEvent): GitHubEvent object.
        config (Config): Config object.
        github_token (str): A token for github to generate a new PR.

    """
    changelog = ChangelogManager.from_config(config)
    summary = get_summary()

    current_branch: str = event.get_source_branch_name()
    target_branch: str = event.get_target_branch_name()
    release_cfg = config.data.release

    repo_full_name: str = gitops.get_repository_name()
    summary.set("branches", f"{current_branch} -> {target_branch}")

    if target_branch not in config.data.suffixes:
        logger.error(f"Target branch '{target_branch}' not found in suffixes configuration.")
        raise ValueError(f"Target branch '{target_branch}' is not configured in suffixes.")

    with log_group("Resolve version"):
        logger.info(f"Branch name: {current_branch}")
        with status("Fetching baseline..."):
            gitops.fetch()
            version = _resolve_baseline_version(
                gitops=gitops,
                config=config,
                target_branch=target_branch,
                github_token=github_token,
            )
        previous_version_str = str(version)

        is_tag_promotion = _is_tag_promotion_scenario(
            version=version, target_branch=target_branch, config=config
        )

        if is_tag_promotion:
            logger.info(f"Detected tag promotion: {version} → {target_branch}")
        else:
            logger.info(f"Standard bump workflow: {current_branch} → {target_branch}")

        logger.info(f"Current version: {version}")

        bump_counts: BumpCounts | None = None

        lockfile = SemverLock.get_or_create(
            version=version,
            source_branch=current_branch,
            target_branch=target_branch,
        )
        baseline_sha = lockfile.target_base_sha

        if not is_tag_promotion:
            with status("Applying version bump..."):
                bump_counts = _apply_version_bump(
                    version=version,
                    config=config,
                    current_branch=current_branch,
                    gitops=gitops,
                    target_branch=target_branch,
                    baseline_sha=baseline_sha,
                    github_token=github_token,
                )
        else:
            logger.info("Skipping version bump for tag promotion - preserving version numbers")

        suffix: str = config.data.suffixes[target_branch]
        version.set_suffix(suffix=suffix)
        new_version: str = str(version)
        summary.set("version", f"{previous_version_str} -> {new_version}")
        logger.info(f"New version: {new_version}")

    with log_group("Update files/changelog"):
        files_to_update: list[str] = config.data.version_files

        with status("Updating version files and changelog..."):
            for path in files_to_update:
                VersionFileUpdater(file_path=path, version=version).update()

            release_branch_name = f"{release_cfg.branch_prefix.rstrip('/')}/{new_version}"

            lockfile.version = version
            lockfile.as_release_branch_lock()

            try:
                previous_lock_content = gitops.get_file_content_at_commit("HEAD~1", SemverLock.path)
                if previous_lock_content:
                    previous_lock = SemverLock.from_dict(yaml.safe_load(previous_lock_content))
                    if previous_lock.target_base_sha != lockfile.target_base_sha:
                        logger.info(
                            "Baseline SHA changed in previous commit. "
                            "Detected potential Release PR match. Starting fresh changelog."
                        )
                        changelog.truncate = True
            except Exception as e:
                logger.warning(
                    f"Failed to compare lockfile with previous commit (HEAD~1). "
                    f"Skipping baseline check. Details: {e}"
                )

            latest_commit_sha = lockfile.target_base_sha or event.get_merged_commit_sha()

            commit_messages = gitops.get_recent_commits(latest_commit_sha, config=config)
            changelog.update(
                version=new_version,
                messages=commit_messages,
                commit_groups=config.data.commit_groups.groups,
            )

            lockfile.target_base_sha = event.get_merged_commit_sha()
            lockfile.save_to_file()

    with log_group("Git commit/push"):
        with status("Creating release branch and pushing..."):
            gitops.create_branch(branch_name=release_branch_name, force=True)
            gitops.add(files_to_update)
            gitops.add([lockfile.path])
            gitops.add([changelog.path])
            gitops.commit(f"Release {new_version}", force=True)
            _push_release_branch(gitops=gitops, release_branch_name=release_branch_name)

        if release_cfg.strategy == "single":
            _supersede_old_releases_in_single_mode(
                gitops=gitops,
                config=config,
                github_token=github_token,
                target_branch=target_branch,
                release_branch_name=release_branch_name,
            )
        else:
            logger.info("release.strategy=multi — keeping existing open release PRs")

    with log_group("Open PR"):
        release_date = datetime.date.today().strftime("%d-%m-%Y")

        commit_groups_data = None
        if config.data.commit_groups.groups:
            commit_groups_data = CommitGrouper.group_messages(
                commit_messages, config.data.commit_groups
            )

        pr_variables = GitHubPRTemplateVariables(
            version=new_version,
            previous_version=previous_version_str,
            commit_groups=commit_groups_data or [],
            breaking_changes=[],
            author=event.get_actor() if hasattr(event, "get_actor") else "auto-semver",
            repository=repo_full_name,
            date=release_date,
            branch=release_branch_name,
            base_branch=target_branch,
            labels=config.data.pull_request.labels,
            groups=commit_groups_data,
            feature_count=bump_counts.feature_count if bump_counts else 0,
            fix_count=bump_counts.fix_count if bump_counts else 0,
        )

        pr_builder = GitHubPRBuilder(
            data=pr_variables,
            title_template=config.data.pull_request.title,
            body_template=config.data.pull_request.body,
            labels_template=",".join(config.data.pull_request.labels or []),
        )

        pr_title: str = pr_builder.title
        pr_body: str = pr_builder.body

        with status("Opening pull request..."):
            pr_number = gitops.create_pr(
                title=pr_title,
                body=pr_body,
                source=release_branch_name,
                target=target_branch,
                github_token=github_token,
                labels=config.data.pull_request.labels,
            )
        summary.set("pr", f"#{pr_number}")
