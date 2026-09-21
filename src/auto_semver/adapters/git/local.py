# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Local GitPython plumbing."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from git import Actor, Commit, GitCommandError, Head, Repo
from git.remote import PushInfo, Remote

from auto_semver.adapters.git.base import GitOpsBase

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__package__)


class GitLocal(GitOpsBase):
    """Local GitPython plumbing."""

    def __init__(
        self,
        *,
        repo_path: str = ".",
        ensure_safe: bool = False,
        signed_commits: bool = False,
        github_token: str | None = None,
    ) -> None:
        """
        Initialize GitOps for the given repository path.

        Args:
            repo_path (str): Path to the local Git repository (default: current directory).
            ensure_safe (bool): If True, ensures the repository is marked as a safe directory in Git config.
            signed_commits (bool): When True, create commits/merges/tags via the GitHub API so
                GitHub signs them as verified (requires ``github_token``).
            github_token (str | None): Token for API-backed commits (App installation token).

        """

        self.repo = Repo(path=repo_path)
        self._repo_full_name: str = self._parse_repository_name()  # Cache repository name on init
        self.signed_commits = signed_commits
        self.github_token = github_token
        self._github_clients = {}
        if signed_commits and not github_token:
            raise ValueError("github_token is required when signed_commits=True")
        if ensure_safe:
            self.__ensure_git_safe_directory()
        self._identity = self.__ensure_git_identity()

    def __ensure_git_safe_directory(self) -> None:
        """
        Ensure the repository path is listed as a safe Git directory in the repository config.

        This is important for CI environments that may require explicitly trusting the repo.
        Uses repository-level config which doesn't require elevated privileges and is scoped to this repo.
        """

        logger.debug("Ensuring the repository is marked as a safe directory.")

        safe_key: str = "safe"
        directory_key: str = "directory"

        path: str = str(self.repo.working_tree_dir)

        logger.debug(f"Working tree directory: {path}")

        try:
            git_config = self.repo.config_writer(config_level="global")

            logger.debug(f"Checking if {path} is in safe directories.")

            raw_values = git_config.get_values(section=safe_key, option=directory_key, default="")
            safe_dirs: list[str] = [v for v in raw_values if isinstance(v, str)]

            if path not in safe_dirs:
                logger.debug(f"{path} is not in safe directories.")
                logger.debug(f"Adding {path} to safe directories.")

                git_config.set_value(section=safe_key, option=directory_key, value=path)

            git_config.release()

        except (OSError, PermissionError) as e:
            logger.error(f"Failed to configure git safe directory due to permission error: {e}")
            logger.error(
                "Git safe directory configuration is required for proper operation in CI environments."
            )
            raise RuntimeError(f"Unable to configure git safe directory: {e}") from e

    @staticmethod
    def _redact_remote_url(url: str) -> str:
        """Strip userinfo (e.g. tokens) from a remote URL before logging or raising."""
        try:
            parts = urlsplit(url)
            if parts.scheme in {"http", "https"} and (parts.username or parts.password):
                host = parts.hostname or ""
                if parts.port:
                    host = f"{host}:{parts.port}"
                return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
        except ValueError:
            pass
        # Fallback for non-standard URLs that still embed userinfo before '@'
        return re.sub(r"(https?://)[^/@\s]+@", r"\1", url)

    def _parse_repository_name(self, *, remote_name: str = "origin") -> str:
        """
        Extract the repository name from the Git remote URL.

        Args:
            remote_name (str): Name of the Git remote (default: 'origin').

        Returns:
            str: Repository name in "owner/repo" format.

        Raises:
            ValueError: If remote URL cannot be parsed or is not a GitHub URL.
        """
        try:
            remote: Remote = self.repo.remote(name=remote_name)
            remote_url = remote.url

            # Handle both SSH and HTTPS GitHub URLs
            # SSH: git@github.com:owner/repo.git
            # HTTPS: https://github.com/owner/repo.git

            patterns = [
                r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$",  # SSH format
                r"https://(?:.*?@)?github\.com/([^/]+)/(.+?)(?:\.git)?$",  # HTTPS format (supports auth)
            ]

            for pattern in patterns:
                match = re.match(pattern, remote_url)
                if match:
                    owner, repo = match.groups()
                    return f"{owner}/{repo}"

            safe_url = self._redact_remote_url(remote_url)
            raise ValueError(f"Unable to parse GitHub repository from remote URL: {safe_url}")

        except ValueError:
            raise
        except Exception as e:
            raise ValueError(
                f"Failed to get repository name from remote '{remote_name}': {e}"
            ) from e

    def get_repository_name(self) -> str:
        """
        Get the cached repository name.

        Returns:
            str: Repository name in "owner/repo" format.
        """
        return self._repo_full_name

    def create_branch(self, *, branch_name: str, force: bool = False) -> None:
        """
        Create a new Git branch or overwrites an existing one if specified.

        Args:
            branch_name (str): The name of the branch to create.
            force (bool): If True, overwrites the existing branch with the same name.
                Defaults to False, which prevents overwriting.

        """

        if branch_name in self.repo.heads:
            if not force:
                logger.info(f"Branch '{branch_name}' already exists and force is False.")
                return

            logger.info(f"Deleting existing branch '{branch_name}'")

            existing_branch: Head = self.repo.heads[branch_name]
            existing_branch.delete(repo=self.repo, force=True)

        logger.info(f"Creating new branch '{branch_name}'")

        new_branch: Head = self.repo.create_head(path=branch_name)
        new_branch.checkout()

    def add(self, files: list[str] | list[Path] | list[str | Path]) -> None:
        """
        Stage the specified files for commit.

        Args:
            files (list[str]): List of file paths to add to the Git index.

        """
        files = [str(f) for f in files]

        logger.info(f"Adding files: {files}")

        if not self.repo.is_dirty(untracked_files=True):
            logger.warning("Repo is not dirty — no changes staged or committed.")
        else:
            logger.debug("Repo has staged/committed changes.")

        for file_path in files:
            try:
                self.repo.index.add(items=[file_path])

                logger.debug(f"Added {file_path} to git.")

            except GitCommandError as err:
                logger.error(f"Failed to add {file_path} to git: {err}")
                raise

    def commit(self, message: str, *, force: bool = False) -> None:
        """
        Commit staged changes with the provided message.

        Args:
            message (str): Commit message.
            force (bool): Kept for compatibility with signed commits. GraphQL
                ``createCommitOnBranch`` cannot force-update divergent refs;
                concurrent updates retry once on ``expectedHeadOid`` mismatch.
        """

        logger.info(f"Committing changes with message: {message}")
        logger.debug(f"Staged changes: {self.repo.index.diff('HEAD')}")

        if self.signed_commits:
            branch_name = self.repo.active_branch.name
            additions, deletions = self._collect_staged_file_changes()
            if not additions and not deletions:
                logger.warning("No staged files for signed commit")
                return
            commit_sha = self._api_commit_files_on_branch(
                branch_name=branch_name,
                message=message,
                file_paths=additions,
                deletions=deletions,
                force=force,
            )
            # GraphQL commits update the remote only; sync the runner worktree so
            # later checkouts (e.g. auto-promote to staging) are not blocked by
            # leftover dirty files such as .semver.lock.
            self.repo.git.reset("--hard", commit_sha)
            logger.info("Synced local worktree to signed commit %s", commit_sha)
            return

        self._local_commit(message)
        logger.info("Committed changes.")

    def _local_commit(self, message: str) -> Commit:
        """
        Create a local commit as the bot, bypassing repository hooks.

        Two deliberate deviations from ``git commit``:
        - ``GIT_AUTHOR_*``/``GIT_COMMITTER_*`` are ignored so bot attribution is
          deterministic; ``user.*`` config is the override channel.
        - Hooks are skipped (``git commit -n``). Lint/commit-msg policy belongs on
          the PR, and the signed GraphQL path cannot run hooks, so skipping keeps
          both paths symmetric.
        """
        return self.repo.index.commit(
            message, author=self._identity, committer=self._identity, skip_hooks=True
        )

    def push(self, *, branch_name: str, remote_name: str = "origin", force: bool = False) -> None:
        """
        Push the specified branch to the remote repository, optionally forcing the push.

        Args:
            branch_name (str): The branch to push.
            remote_name (str): Name of the Git remote (default: 'origin').
            force (bool): If True, force push the branch.

        """

        logger.info(f"Pushing branch '{branch_name}' to remote '{remote_name}' with force={force}.")

        if self.signed_commits:
            logger.info(
                "Signed commit path: branch/tag refs updated via GitHub API; syncing local clone"
            )
            self.fetch(remote_name=remote_name)
            return

        try:
            remote: Remote = self.repo.remote(name=remote_name)
            push_infos = remote.push(refspec=branch_name, force=force)

            for info in push_infos:
                if info.flags & (
                    PushInfo.ERROR
                    | PushInfo.REJECTED
                    | PushInfo.REMOTE_REJECTED
                    | PushInfo.REMOTE_FAILURE
                ):
                    error_msg = f"Push failed for {branch_name}: {info.summary}"
                    if info.flags & PushInfo.REJECTED:
                        error_msg += ". Check if remote has diverged or if 'force' is required."

                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

            logger.debug(f"Push result: {push_infos}")

        except GitCommandError as err:
            logger.error(f"Failed to push branch '{branch_name}' to remote '{remote_name}': {err}")
            raise

    def tag(self, *, tag: str, branch: str) -> str:
        """
        Create a new tag on the given branch.

        Args:
            tag (str): Tag name.
            branch (str): Branch name.

        """
        if self.signed_commits:
            gh_repo = self._gh_repo()
            branch_ref = gh_repo.get_git_ref(f"heads/{branch}")
            return self._api_create_lightweight_tag(tag=tag, sha=branch_ref.object.sha)

        return self.repo.create_tag(path=tag, ref=branch, message="").name

    def fetch(self, *, remote_name: str = "origin") -> None:
        """
        Fetch all refs from the remote repository.

        Args:
            remote_name (str): Name of the Git remote (default: 'origin').

        Raises:
            GitCommandError: If fetch operation fails.
        """
        logger.info(f"Fetching from remote '{remote_name}'")

        try:
            remote: Remote = self.repo.remote(name=remote_name)
            remote.fetch()
            logger.debug(f"Fetch from '{remote_name}' completed")
        except GitCommandError as err:
            logger.error(f"Failed to fetch from remote '{remote_name}': {err}")
            raise

    def checkout(self, *, branch_name: str, create_from: str | None = None) -> None:
        """
        Checkout an existing branch or create and checkout a new branch.

        Args:
            branch_name (str): Name of the branch to checkout.
            create_from (str | None): If provided, create the branch from this ref before checkout.

        Raises:
            GitCommandError: If checkout operation fails.
        """
        try:
            if create_from:
                logger.info(
                    f"Creating and checking out branch '{branch_name}' from '{create_from}'"
                )
                new_branch = self.repo.create_head(branch_name, create_from)
                new_branch.checkout()
            else:
                logger.info(f"Checking out branch '{branch_name}'")
                self.repo.heads[branch_name].checkout()

            logger.debug(f"Checked out branch '{branch_name}'")
        except (GitCommandError, IndexError) as err:
            logger.error(f"Failed to checkout branch '{branch_name}': {err}")
            raise GitCommandError(f"Checkout failed for branch '{branch_name}'") from err

    def __ensure_git_identity(
        self,
        *,
        email: str = "256984269+auto-semver-bot[bot]@users.noreply.github.com",
        name: str = "auto-semver-bot[bot]",
    ) -> Actor:
        """
        Resolve and cache the bot Actor used for local commits.

        Prefer an existing ``user.name`` / ``user.email`` from git config (CI
        usually sets these from App token ``user-name`` / ``user-email``
        outputs). Otherwise write the App bot defaults into repo config so
        subprocess git operations (merge, etc.) also attribute correctly.

        When the config write fails (read-only FS, permissions), still return
        the in-memory defaults so ``_local_commit`` can proceed.

        Args:
            email: Git user email (default: App bot users.noreply address).
            name: Git user name (default: auto-semver-bot[bot]).

        Returns:
            Actor to use as both author and committer for local commits.
        """
        defaults = Actor(name=name, email=email)
        try:
            with self.repo.config_reader() as config:
                try:
                    existing_email = config.get_value("user", "email")
                    existing_name = config.get_value("user", "name")
                    logger.debug(
                        f"Git identity already configured: {existing_name} <{existing_email}>"
                    )
                    return Actor(name=str(existing_name), email=str(existing_email))
                except Exception:
                    # Not configured, will set below
                    pass

            logger.debug(f"Configuring Git identity: {name} <{email}>")
            with self.repo.config_writer() as config:
                config.set_value("user", "email", email)
                config.set_value("user", "name", name)

            logger.debug("Git identity configured successfully")
            return defaults
        except Exception as err:
            logger.warning(
                "Failed to configure Git identity: %s; using in-memory defaults %s <%s>",
                err,
                name,
                email,
            )
            return defaults

    def pull(self, *, branch_name: str, remote_name: str = "origin") -> None:
        """
        Pull the latest changes for the current branch from remote.

        Args:
            branch_name (str): Name of the branch to pull.
            remote_name (str): Name of the Git remote (default: 'origin').

        Raises:
            GitCommandError: If pull operation fails.
        """
        logger.info(f"Pulling latest changes for '{branch_name}' from '{remote_name}'")

        try:
            remote: Remote = self.repo.remote(name=remote_name)
            remote.pull(branch_name)
            logger.debug(f"Pull for '{branch_name}' completed")
        except GitCommandError as err:
            logger.error(f"Failed to pull '{branch_name}' from '{remote_name}': {err}")
            raise
