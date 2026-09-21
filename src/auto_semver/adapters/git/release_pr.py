# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Release PR ownership and discovery."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import yaml
from git import Commit, GitCommandError
from git.remote import PushInfo, Remote
from github.GithubException import GithubException

from auto_semver.adapters.git.base import GitOpsBase
from auto_semver.adapters.git.constants import (
    DEFAULT_RELEASE_PREFIX,
    LEGACY_RELEASE_PREFIX,
)
from auto_semver.config.constants import (
    INTERNAL_COMMIT_PREFIXES,
    PR_HIDDEN_MARKER,
)
from auto_semver.core.semver import SemverLock, Version

if TYPE_CHECKING:
    from github.PullRequest import PullRequest
    from github.Repository import Repository

    from auto_semver.config import Config

logger = logging.getLogger(__package__)


class GitReleasePr(GitOpsBase):
    """Release PR ownership and discovery."""

    def get_lock_at_ref(self, ref: str) -> SemverLock | None:
        """Load `.semver.lock` from a branch or tag ref."""
        try:
            blob = self.repo.git.show(f"{ref}:{SemverLock.path}")
            return SemverLock.from_dict(yaml.safe_load(blob))
        except GitCommandError as err:
            logger.debug("No lockfile at ref %s: %s", ref, err)
            return None

    def delete_branch(self, *, branch_name: str, remote_name: str = "origin") -> None:
        """Delete a remote branch ref."""
        logger.info("Deleting remote branch '%s' on '%s'", branch_name, remote_name)
        if self.signed_commits:
            gh_repo = self._gh_repo()
            ref_name = f"heads/{branch_name}"
            ref = gh_repo.get_git_ref(ref_name)
            ref.delete()
            self.fetch(remote_name=remote_name)
            return

        remote: Remote = self.repo.remote(name=remote_name)
        push_infos = remote.push(refspec=f":{branch_name}")
        for info in push_infos:
            if info.flags & (PushInfo.ERROR | PushInfo.REJECTED | PushInfo.REMOTE_FAILURE):
                raise RuntimeError(f"Failed to delete branch {branch_name}: {info.summary}")

    @staticmethod
    def _normalize_branch_name(ref: str) -> str:
        """Strip remote prefix from a git ref name."""
        for prefix in ("origin/", "refs/heads/"):
            if ref.startswith(prefix):
                return ref.removeprefix(prefix)
        return ref

    @staticmethod
    def _branch_matches_prefix(branch_name: str, branch_prefix: str) -> bool:
        """Return True when branch_name matches `{prefix}{semver}`."""
        prefix = branch_prefix if branch_prefix.endswith("/") else f"{branch_prefix}/"
        pattern = re.compile(re.escape(prefix) + r"\d+\.\d+\.\d+(?:-[\w.]+)?$")
        return bool(pattern.match(branch_name))

    def get_merged_source_branches_since(
        self,
        *,
        base_sha: str,
        target_branch: str,
        github_token: str,
    ) -> list[str]:
        """List merged PR head branch names on target_branch since base_sha."""
        repo_full_name = self._repo_full_name
        gh = self._github_client_for(github_token)
        repo: Repository = gh.get_repo(full_name_or_id=repo_full_name)
        branches: list[str] = []

        for pr in repo.get_pulls(
            state="closed", base=target_branch, sort="updated", direction="desc"
        ):
            if not pr.merged or not pr.merge_commit_sha:
                continue
            merge_sha = pr.merge_commit_sha
            try:
                self.repo.git.merge_base("--is-ancestor", base_sha, merge_sha)
                self.repo.git.merge_base("--is-ancestor", merge_sha, f"origin/{target_branch}")
            except GitCommandError:
                continue
            branches.append(pr.head.ref)

        return list(reversed(branches))

    def get_open_release_version(
        self,
        *,
        github_token: str,
        target_branch: str,
        branch_prefix: str,
        labels: list[str] | None = None,
    ) -> Version | None:
        """Return the highest version from open owned release PRs targeting target_branch."""
        repo_full_name = self._repo_full_name
        gh = self._github_client_for(github_token)
        repo: Repository = gh.get_repo(full_name_or_id=repo_full_name)
        highest: Version | None = None

        for pr in repo.get_pulls(state="open"):
            head_ref = pr.head.ref
            if pr.base.ref != target_branch:
                continue
            if not self._is_candidate_release_branch(head_ref, branch_prefix):
                continue
            pr_labels = [label.name for label in pr.labels]
            if labels and not any(label in pr_labels for label in labels):
                continue
            if PR_HIDDEN_MARKER not in (pr.body or ""):
                continue

            lock = self.get_lock_at_ref(f"origin/{head_ref}")
            if lock is None:
                continue

            if highest is None or lock.version > highest:
                highest = lock.version

        return highest

    def _is_candidate_release_branch(self, branch_name: str, branch_prefix: str) -> bool:
        """Return True for configured or legacy release branch names."""
        return self._branch_matches_prefix(branch_name, branch_prefix) or (
            branch_name.startswith(LEGACY_RELEASE_PREFIX)
            and branch_name != LEGACY_RELEASE_PREFIX.rstrip("/")
        )

    def _find_release_pr(
        self,
        *,
        github_token: str,
        branch_name: str,
        target_branch: str | None = None,
    ) -> PullRequest | None:
        repo: Repository = self._get_github_repo(
            github_token=github_token,
            repo_full_name=self._repo_full_name,
        )
        for pr in repo.get_pulls(state="all"):
            if pr.head.ref != branch_name:
                continue
            if target_branch and pr.base.ref != target_branch:
                continue
            return pr
        return None

    def is_auto_semver_release_branch(
        self,
        *,
        branch_name: str,
        github_token: str,
        branch_prefix: str,
        labels: list[str] | None = None,
        require_closed_pr: bool = False,
        skip_pr_check: bool = False,
    ) -> tuple[bool, str]:
        """
        Verify branch ownership for cleanup/delete operations.

        Returns:
            Tuple of (is_owned, skip_reason). skip_reason is empty when owned.
        """
        skip_reason = ""
        if not self._is_candidate_release_branch(branch_name, branch_prefix):
            skip_reason = "branch name does not match release prefix"
        else:
            lock = self.get_lock_at_ref(f"origin/{branch_name}")
            if lock is None:
                skip_reason = "no lockfile at branch tip"
            elif not lock.is_release_branch_lock() and not lock.is_legacy_managed_lock():
                skip_reason = "lock is not auto-semver managed"

        if skip_reason:
            return False, skip_reason

        if skip_pr_check:
            return True, ""

        pr = self._find_release_pr(github_token=github_token, branch_name=branch_name)
        if pr is None:
            return False, "no associated pull request"

        pr_reason = self._release_pr_ownership_reason(
            pr=pr,
            labels=labels,
            require_closed_pr=require_closed_pr,
        )
        if pr_reason:
            return False, pr_reason

        return True, ""

    def _release_pr_ownership_reason(
        self,
        *,
        pr: PullRequest,
        labels: list[str] | None,
        require_closed_pr: bool,
    ) -> str:
        """Return a skip reason when the release PR fails ownership checks."""
        if require_closed_pr and pr.state == "open":
            return "pull request still open"

        pr_labels = [label.name for label in pr.labels]
        if labels and not any(label in pr_labels for label in labels):
            return "pull request missing configured label"

        if PR_HIDDEN_MARKER not in (pr.body or ""):
            return "pull request missing auto-semver marker"

        return ""

    def _is_closeable_release_pr(
        self,
        *,
        branch_name: str,
        github_token: str,
        branch_prefix: str,
        labels: list[str] | None,
    ) -> tuple[bool, str]:
        """
        Decide whether an open release PR can be superseded in single mode.

        Accepts pre-ownership locks (no managed_by metadata) on candidate release
        branches so legacy release/* PRs are closed when a new release opens.
        """
        owned, reason = self.is_auto_semver_release_branch(
            branch_name=branch_name,
            github_token=github_token,
            branch_prefix=branch_prefix,
            labels=labels,
            skip_pr_check=True,
        )
        if owned:
            return True, ""

        lock = self.get_lock_at_ref(f"origin/{branch_name}")
        if lock is None:
            return False, reason or "no lockfile at branch tip"

        if lock.finalized:
            return False, "lock already finalized"

        if lock.is_preownership_release_lock() and self._is_candidate_release_branch(
            branch_name, branch_prefix
        ):
            return True, ""

        return False, reason or "lock is not auto-semver managed"

    def close_old_release_prs(
        self,
        *,
        github_token: str,
        target_branch: str,
        labels: list[str] | None = None,
        branch_prefix: str = DEFAULT_RELEASE_PREFIX,
        exclude_branch: str | None = None,
        delete_branches: bool = False,
    ) -> None:
        """
        Close open owned release PRs targeting the specified branch.

        Args:
            github_token: GitHub access token.
            target_branch: The target branch (e.g., 'dev' or 'main').
            labels: Optional list of label names to match.
            branch_prefix: Configured release branch prefix.
            exclude_branch: Optional branch name to keep open (current release).
            delete_branches: When True, delete each superseded release branch after closing.

        Raises:
            GithubException: If there is an error with the GitHub API.

        """
        repo_full_name = self._repo_full_name

        logger.info(f"Checking for existing PRs for target branch: {target_branch}")

        gh = self._github_client_for(github_token)

        try:
            repo: Repository = gh.get_repo(full_name_or_id=repo_full_name)
            open_prs = repo.get_pulls(state="open")

            for pr in open_prs:
                head_ref: str = pr.head.ref
                base_ref: str = pr.base.ref

                if head_ref == exclude_branch:
                    continue

                if base_ref != target_branch:
                    continue

                if not self._is_candidate_release_branch(head_ref, branch_prefix):
                    continue

                pr_labels: list[str] = [label.name for label in pr.labels]
                if labels and not any(label in pr_labels for label in labels):
                    continue

                if PR_HIDDEN_MARKER not in (pr.body or ""):
                    continue

                owned, reason = self._is_closeable_release_pr(
                    branch_name=head_ref,
                    github_token=github_token,
                    branch_prefix=branch_prefix,
                    labels=labels,
                )
                if not owned:
                    logger.info("Skipping PR #%s (%s): %s", pr.number, head_ref, reason)
                    continue

                logger.info(f"Closing old PR #{pr.number}: {head_ref} → {base_ref}")
                pr.edit(state="closed")
                if delete_branches:
                    self._delete_superseded_release_branch(branch_name=head_ref)

        except GithubException as err:
            logger.error(f"GitHub API error while closing PRs: {err}")
            raise

    def cleanup_stale_release_branches(
        self,
        *,
        github_token: str,
        target_branch: str,
        labels: list[str] | None = None,
        branch_prefix: str = DEFAULT_RELEASE_PREFIX,
        exclude_branch: str | None = None,
    ) -> None:
        """
        Delete owned release branches that no longer have an open PR (single mode).

        Handles branches left behind when a previous bump closed the PR but did not
        delete the remote ref.
        """
        self.fetch()
        remote: Remote = self.repo.remote()
        candidates: list[str] = []

        for ref in remote.refs:
            branch_name = self._normalize_branch_name(ref.name)
            if branch_name == exclude_branch:
                continue
            if not self._is_candidate_release_branch(branch_name, branch_prefix):
                continue
            candidates.append(branch_name)

        for branch_name in sorted(set(candidates)):
            pr = self._find_release_pr(
                github_token=github_token,
                branch_name=branch_name,
                target_branch=target_branch,
            )
            if pr is not None and pr.state == "open":
                continue
            if pr is not None:
                pr_labels = [label.name for label in pr.labels]
                if labels and not any(label in pr_labels for label in labels):
                    continue
                if PR_HIDDEN_MARKER not in (pr.body or ""):
                    continue

            closeable, reason = self._is_closeable_release_pr(
                branch_name=branch_name,
                github_token=github_token,
                branch_prefix=branch_prefix,
                labels=labels,
            )
            if not closeable:
                logger.info("Skipping stale branch delete for %s: %s", branch_name, reason)
                continue

            self._delete_superseded_release_branch(branch_name=branch_name)

    def _delete_superseded_release_branch(self, *, branch_name: str) -> None:
        """Delete a superseded release branch, logging failures without raising."""
        try:
            self.delete_branch(branch_name=branch_name)
            logger.info("Deleted superseded release branch %s", branch_name)
        except Exception as err:
            logger.warning("Failed to delete superseded release branch %s: %s", branch_name, err)

    def create_pr(
        self,
        *,
        github_token: str,
        title: str,
        body: str,
        source: str,
        target: str,
        labels: list[str] | None = None,
    ) -> int:
        """
        Create a pull request from the source branch to the target branch.

        Args:
            github_token (str): GitHub API token.
            title (str): Title for the PR.
            body (str): Body for the PR content.
            source (str): Source branch.
            target (str): Target branch.
            labels (str | None): Optional label to add to the PR.
                If None, no label is added.

        Returns:
            The PR number.

        """

        # Get the repository name (uses cached value)
        repo_full_name = self._repo_full_name

        logger.debug("Creating PR with the following parameters:")
        logger.debug(f"  Repo: {repo_full_name}")
        logger.debug(f"  Title: {title}")
        logger.debug(f"  Body: {body}")
        logger.debug(f"  Source: {source}")
        logger.debug(f"  Target: {target}")
        logger.debug(f"  Labels: {labels}")

        gh = self._github_client_for(github_token)

        try:
            repo: Repository = gh.get_repo(full_name_or_id=repo_full_name)

            for pr in repo.get_pulls(state="open"):
                if pr.head.ref == source and pr.base.ref == target:
                    logger.warning(
                        f"PR already exists for branch '{source}' → '{target}', skipping creation."
                    )

                    return pr.number

            new_pr: PullRequest = repo.create_pull(title=title, body=body, head=source, base=target)

            if labels:
                try:
                    new_pr.add_to_labels(*labels)

                    label_str = ", ".join(f"'{label}'" for label in labels)
                    logger.info(f"Labels [{label_str}] added to PR #{new_pr.number}.")

                except GithubException as err:
                    logger.error(f"Failed to add labels '{labels}' to PR #{new_pr.number}: {err}")

                    raise

            logger.info(f"PR created successfully: #{new_pr.number}")

            return new_pr.number

        except GithubException as err:
            logger.error(f"GitHub API error during PR creation: {err}")

            raise

    def get_recent_commits(
        self,
        commit_sha: str,
        *,
        filter_release_commits: bool = True,
        config: Config | None = None,
    ) -> list[str]:
        """
        Get commit messages between the specified commit SHA and HEAD.

        This method attempts to fetch the commit SHA from the remote if it doesn't exist locally.

        Args:
            commit_sha (str): The base commit SHA to compare against HEAD.
            filter_release_commits (bool): If True, filters out release-related commits.
            config (Config): Configuration object to determine release commit patterns.

        Returns:
            list[str]: A list of commit messages.

        Raises:
            RuntimeError: If the git command fails.

        """

        logger.info(f"Fetching recent commits between {commit_sha} and HEAD.")

        try:
            # Check if SHA exists locally
            self.repo.git.rev_parse(commit_sha)
        except GitCommandError:
            logger.warning(f"SHA {commit_sha} not found locally. Attempting to fetch...")
            try:
                self.repo.git.fetch("origin", commit_sha, "--depth=1")
            except GitCommandError as fetch_err:
                logger.error(f"Failed to fetch missing SHA '{commit_sha}': {fetch_err}")
                raise RuntimeError(f"Failed to fetch SHA {commit_sha}: {fetch_err}") from fetch_err

        try:
            commits: list[Commit] = list(self.repo.iter_commits(f"{commit_sha}..HEAD"))
            messages: list[str] = [str(commit.message).strip() for commit in reversed(commits)]

            if filter_release_commits and config:
                original_count = len(messages)
                messages = self._filter_internal_commits(messages, config)
                filtered_count = original_count - len(messages)

                if filtered_count > 0:
                    logger.debug(f"Filtered out {filtered_count} auto-semver commits")
                else:
                    logger.debug("No auto-semver commits found to filter out.")
            elif not filter_release_commits:
                logger.debug("Filtering of release commits is disabled.")
            elif not config:
                logger.warning("No config provided, skipping release commit filtering.")

            for message in messages:
                logger.debug(f"Commit message: {message}")

            logger.debug(f"Found {len(messages)} commits.")

            return messages

        except GitCommandError as err:
            logger.error(f"Failed to fetch recent commits: {err}")

            raise RuntimeError(f"Failed to fetch recent commits: {err}") from err

    def get_lock_version_from_branch(
        self,
        branch_name: str,
        remote_name: str = "origin",
    ) -> Version | None:
        """
        Get the version from the lockfile on a specific branch.

        Args:
            branch_name (str): The branch to check.
            remote_name (str): The name of the remote to check.

        Returns:
            The Version object found, or None if none found.

        """
        try:
            logger.info(f"Fetching branch '{branch_name}' from remote '{remote_name}'...")
            self.repo.git.fetch(remote_name, branch_name)

            full_branch_ref = f"{remote_name}/{branch_name}"
            logger.debug(f"Checking branch for lockfile: {full_branch_ref}")

            try:
                blob = self.repo.git.show(f"{full_branch_ref}:{SemverLock.path}")
                lock = SemverLock.from_dict(yaml.safe_load(blob))
                logger.debug(f"Loaded lockfile from {branch_name}: {lock}")
                return lock.version
            except Exception as err:
                logger.warning(f"No lockfile in {branch_name}: {err}")
                return None

        except Exception as err:
            logger.error(f"Failed to get lock version from branch {branch_name}: {err}")
            return None

    def get_file_content_at_commit(self, commit_sha: str, file_path: str) -> str | None:
        """
        Retrieve file content from a specific commit SHA.

        Args:
            commit_sha (str): The git commit SHA to read from.
            file_path (str): Relative path to the file in the repository.

        Returns:
            str | None: The file content as a string, or None if the file/commit is missing
                        or cannot be read.
        """
        try:
            logger.debug(f"Reading {file_path} at {commit_sha}")
            return str(self.repo.git.show(f"{commit_sha}:{file_path}"))
        except GitCommandError as e:
            logger.warning(f"Failed to read {file_path} at {commit_sha}: {e}")
            return None

    def get_lock_version_from_tag(self, tag_name: str) -> Version | None:
        """
        Get the version from the lockfile at a specific tag.

        Args:
            tag_name (str): The tag to check.

        Returns:
            The Version object found, or None if none found.
        """
        try:
            logger.debug(f"Checking tag for lockfile: {tag_name}")
            blob = self.repo.git.show(f"{tag_name}:{SemverLock.path}")
            lock = SemverLock.from_dict(yaml.safe_load(blob))
            logger.debug(f"Loaded lockfile from {tag_name}: {lock}")
            return lock.version
        except Exception as err:
            logger.warning(f"No lockfile in tag {tag_name}: {err}")
            return None

    def _filter_internal_commits(self, messages: list[str], config: Config) -> list[str]:
        """
        Filter out auto-semver housekeeping and release commit messages.

        Drops release title commits plus finalize/promote lock metadata commits so
        they never appear in generated changelogs or release PR bodies.

        Args:
            messages (list[str]): List of commit messages to filter.
            config (Config): Configuration object to get release title template.

        Returns:
            list[str]: Filtered list of commit messages with internal commits removed.

        """

        # Get the release commit prefix from config
        release_prefix = config.data.pull_request.get_release_commit_prefix()

        # Robust fallback: strict "Release " check if config extraction fails
        if not release_prefix:
            logger.warning(
                "No release prefix found in config title template. Falling back to default 'Release '."
            )
            # Default fallback for most common case
            release_prefix = "Release "
        else:
            logger.debug(f"Using config-based release prefix: '{release_prefix}'")

        prefixes = [release_prefix, *INTERNAL_COMMIT_PREFIXES]
        filtered_messages = []

        for message in messages:
            # Normalize message for checking - only check the first line (title)
            first_line = message.splitlines()[0].strip() if message else ""

            if any(first_line.startswith(prefix) for prefix in prefixes if prefix):
                logger.debug(f"Filtering out auto-semver commit: {first_line}")
            else:
                filtered_messages.append(message)

        return filtered_messages
