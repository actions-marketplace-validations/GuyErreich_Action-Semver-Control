# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verified commit transport (GraphQL + REST)."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from git import GitCommandError
from github import Github
from github.GithubException import GithubException
from github.InputGitTreeElement import InputGitTreeElement

from auto_semver.adapters.git.base import GitOpsBase
from auto_semver.adapters.git.constants import (
    _CREATE_COMMIT_ON_BRANCH_MUTATION,
    _KNOWN_GIT_FILE_MODES,
    _RAW_DIFF_MIN_MODE_FIELDS,
    _REST_TREE_MODES,
)

if TYPE_CHECKING:
    from github.Repository import Repository
    from github.Requester import Requester


logger = logging.getLogger(__package__)


class GitVerifiedCommits(GitOpsBase):
    """Verified commit transport (GraphQL + REST)."""

    def _get_github_repo(self, *, github_token: str, repo_full_name: str) -> Repository:
        return self._github_client_for(github_token).get_repo(repo_full_name)

    def _github_client_for(self, token: str) -> Github:
        """Return a cached Github client for ``token`` (closed via ``close``)."""
        cache: dict[str, Github] = getattr(self, "_github_clients", None) or {}
        self._github_clients = cache
        client = cache.get(token)
        if client is None:
            client = Github(login_or_token=token)
            cache[token] = client
        return client

    def _github_client(self) -> Github:
        if not self.github_token:
            raise ValueError("github_token is required for API git operations")
        return self._github_client_for(self.github_token)

    def close(self) -> None:
        """Close all cached PyGithub clients."""
        cache: dict[str, Github] = getattr(self, "_github_clients", {})
        for client in cache.values():
            client.close()
        cache.clear()

    def _gh_repo(self) -> Repository:
        if not self.github_token:
            raise ValueError("github_token is required for API git operations")
        return self._get_github_repo(
            github_token=self.github_token,
            repo_full_name=self._repo_full_name,
        )

    def _github_requester(self) -> Requester:
        return self._github_client().requester

    def _collect_staged_paths(self) -> list[str]:
        """Return repository-relative paths staged for the next commit (all change types)."""
        additions, deletions = self._collect_staged_file_changes()
        return additions + deletions

    def _collect_staged_file_changes(self) -> tuple[list[str], list[str]]:
        """
        Return staged paths split into additions/modifications and deletions.

        Uses ``git diff --cached --diff-filter`` so GraphQL ``createCommitOnBranch``
        receives correct ``fileChanges.additions`` and ``fileChanges.deletions``.
        """
        added = self.repo.git.diff("--cached", "--name-only", "--diff-filter=ACMR")
        deleted = self.repo.git.diff("--cached", "--name-only", "--diff-filter=D")
        additions = [line.strip() for line in added.splitlines() if line.strip()]
        deletions = [line.strip() for line in deleted.splitlines() if line.strip()]
        return additions, deletions

    def _collect_dirty_tracked_paths(self) -> list[str]:
        """Return tracked paths with unstaged modifications."""
        output = self.repo.git.diff("--name-only")
        return [line.strip() for line in output.splitlines() if line.strip()]

    @staticmethod
    def _normalize_repo_rel_path(rel_path: str) -> str:
        return rel_path.replace("\\", "/")

    @staticmethod
    def _split_commit_message(message: str) -> tuple[str, str | None]:
        """Split a commit message into GraphQL headline and optional body."""
        headline, sep, body = message.partition("\n")
        headline = headline.strip() or message.strip()
        body_text = body.strip() if sep and body.strip() else None
        return headline, body_text

    def _worktree_git_mode(self, *, rel_path: str, repo_root: Path) -> str | None:
        """Return git mode for a worktree path, or None if missing."""
        full_path = repo_root / rel_path
        if not full_path.exists() and not full_path.is_symlink():
            return None
        if full_path.is_symlink():
            return "120000"
        if full_path.is_file() and full_path.stat().st_mode & 0o111:
            return "100755"
        if full_path.is_file():
            return "100644"
        return None

    def _ls_tree_mode(self, *, ref: str, rel_path: str) -> str | None:
        """Return ``git ls-tree`` mode for ``rel_path`` at ``ref``, or None."""
        norm = self._normalize_repo_rel_path(rel_path)
        try:
            output = self.repo.git.ls_tree(ref, "--", norm)
        except GitCommandError:
            return None
        if not isinstance(output, str) or not output.strip():
            return None
        line = output.strip().splitlines()[0]
        # Format: <mode> <type> <sha>\t<path>
        mode = line.split(maxsplit=1)[0]
        if mode not in _KNOWN_GIT_FILE_MODES:
            return None
        return mode

    def _raw_diff_has_special_modes(self, *, base_sha: str, head_ref: str = "HEAD") -> bool:
        """True when ``git diff --raw`` shows 100755/120000 or a mode change."""
        try:
            raw = self.repo.git.diff(base_sha, head_ref, "--raw")
        except GitCommandError:
            return False
        if not isinstance(raw, str):
            return False
        for line in raw.splitlines():
            if not line.startswith(":"):
                continue
            # :oldmode newmode oldsha newsha status\tpath
            meta, _, _path = line.partition("\t")
            parts = meta.split()
            if len(parts) < _RAW_DIFF_MIN_MODE_FIELDS:
                continue
            old_mode = parts[0][1:]  # strip leading ':'
            new_mode = parts[1]
            if old_mode not in _KNOWN_GIT_FILE_MODES or new_mode not in _KNOWN_GIT_FILE_MODES:
                continue
            if old_mode in _REST_TREE_MODES or new_mode in _REST_TREE_MODES:
                return True
            if old_mode != new_mode:
                return True
        return False

    def _worktree_paths_require_rest(self, *, file_paths: list[str], repo_root: Path) -> bool:
        """True when any path is a symlink or executable in the worktree."""
        for rel_path in file_paths:
            mode = self._worktree_git_mode(rel_path=rel_path, repo_root=repo_root)
            if mode in _REST_TREE_MODES:
                return True
        return False

    def _paths_mode_conflict_with_base(
        self, *, base_sha: str, file_paths: list[str], repo_root: Path
    ) -> bool:
        """True when worktree mode differs from ``base_sha`` for any path."""
        for rel_path in file_paths:
            desired = self._worktree_git_mode(rel_path=rel_path, repo_root=repo_root)
            if desired is None:
                continue
            base_mode = self._ls_tree_mode(ref=base_sha, rel_path=rel_path)
            if base_mode is not None and base_mode != desired:
                return True
            if desired in _REST_TREE_MODES:
                return True
        return False

    def _tree_diff_requires_rest(self, *, base_sha: str, head_ref: str = "HEAD") -> bool:
        """True when publishing ``head_ref`` over ``base_sha`` needs REST modes."""
        if self._raw_diff_has_special_modes(base_sha=base_sha, head_ref=head_ref):
            return True
        additions, _deletions = self._diff_paths_between(base_sha=base_sha, head_ref=head_ref)
        repo_root = Path(self.repo.working_tree_dir or ".")
        return self._worktree_paths_require_rest(file_paths=additions, repo_root=repo_root)

    def _require_commit_verified(self, sha: str) -> None:
        """
        Abort unless GitHub reports ``verification.verified`` for ``sha``.

        Required for the REST Git Data fallback under ``signed-commits: true``.
        """
        git_commit = self._gh_repo().get_git_commit(sha)
        verification = git_commit.verification
        verified = bool(getattr(verification, "verified", False))
        reason = getattr(verification, "reason", "unknown")
        if not verified:
            raise RuntimeError(
                f"Signed REST commit {sha} is not GitHub-verified "
                f"(reason={reason}). Refusing to update the branch. "
                "Omit author/committer/signature on create_git_commit and use "
                "an App installation token."
            )
        logger.info("REST commit %s verified (reason=%s)", sha, reason)

    def _ensure_remote_branch(self, *, branch_name: str) -> str:
        """
        Ensure ``branch_name`` exists on the remote; return its tip OID.

        When the branch is missing, create it at the local HEAD commit.
        """
        gh_repo = self._gh_repo()
        ref_name = f"heads/{branch_name}"
        try:
            ref = gh_repo.get_git_ref(ref_name)
            return str(ref.object.sha)
        except GithubException:
            parent_sha = self.repo.head.commit.hexsha
            gh_repo.create_git_ref(f"refs/{ref_name}", parent_sha)
            logger.info("Created remote branch %s at %s", branch_name, parent_sha)
            return parent_sha

    def _build_file_additions(
        self, *, file_paths: list[str], repo_root: Path
    ) -> list[dict[str, str]]:
        """Build GraphQL ``FileAddition`` payloads (base64 contents, always 100644)."""
        additions: list[dict[str, str]] = []
        for rel_path in file_paths:
            full_path = repo_root / rel_path
            content = full_path.read_bytes()
            additions.append(
                {
                    "path": self._normalize_repo_rel_path(rel_path),
                    "contents": base64.b64encode(content).decode("ascii"),
                }
            )
        return additions

    def _rest_blob_for_path(self, *, rel_path: str, repo_root: Path) -> tuple[str, str]:
        """Return ``(mode, blob_sha)`` for a worktree path via Git Data ``create_git_blob``."""
        gh_repo = self._gh_repo()
        full_path = repo_root / rel_path
        mode = self._worktree_git_mode(rel_path=rel_path, repo_root=repo_root)
        if mode is None:
            raise ValueError(f"Cannot create REST blob for missing path: {rel_path}")

        if mode == "120000":
            target = str(full_path.readlink())
            blob = gh_repo.create_git_blob(target, "utf-8")
            return mode, str(blob.sha)

        raw = full_path.read_bytes()
        if mode == "100755":
            payload = base64.b64encode(raw).decode("ascii")
            blob = gh_repo.create_git_blob(payload, "base64")
            return mode, str(blob.sha)

        try:
            text = raw.decode("utf-8")
            blob = gh_repo.create_git_blob(text, "utf-8")
        except UnicodeDecodeError:
            payload = base64.b64encode(raw).decode("ascii")
            blob = gh_repo.create_git_blob(payload, "base64")
        return mode, str(blob.sha)

    def _rest_create_commit_on_branch(
        self,
        *,
        branch_name: str,
        message: str,
        expected_head_oid: str,
        file_paths: list[str],
        deletions: list[str],
    ) -> str:
        """
        Create a verified commit via Git Database REST (blob → tree → commit → ref).

        Used when GraphQL ``createCommitOnBranch`` cannot represent the tree
        (executables, symlinks, or mode changes). Omits author/committer/signature
        so GitHub App-signs the commit; refuses to move the ref unless
        ``verification.verified`` is true.
        """
        if not file_paths and not deletions:
            raise ValueError("file_paths/deletions must not be empty for REST commit")

        gh_repo = self._gh_repo()
        repo_root = Path(self.repo.working_tree_dir or ".")
        parent = gh_repo.get_git_commit(expected_head_oid)
        elements: list[InputGitTreeElement] = []

        for rel_path in file_paths:
            norm = self._normalize_repo_rel_path(rel_path)
            mode, blob_sha = self._rest_blob_for_path(rel_path=rel_path, repo_root=repo_root)
            elements.append(InputGitTreeElement(path=norm, mode=mode, type="blob", sha=blob_sha))

        for rel_path in deletions:
            norm = self._normalize_repo_rel_path(rel_path)
            elements.append(InputGitTreeElement(path=norm, mode="100644", type="blob", sha=None))

        tree = gh_repo.create_git_tree(elements, parent.tree)
        # Do not pass author/committer/signature — required for App auto-signing.
        commit = gh_repo.create_git_commit(message, tree, [parent])
        commit_sha = str(commit.sha)
        self._require_commit_verified(commit_sha)

        ref = gh_repo.get_git_ref(f"heads/{branch_name}")
        current = str(ref.object.sha)
        if current != expected_head_oid:
            raise GithubException(
                409,
                {
                    "message": (
                        f"expectedHeadOid mismatch on {branch_name}: "
                        f"expected {expected_head_oid}, remote is {current}"
                    )
                },
                None,
            )
        ref.edit(sha=commit_sha, force=False)
        logger.info(
            "Verified REST commit %s on %s (modes via Git Data API)",
            commit_sha,
            branch_name,
        )
        return commit_sha

    def _graphql_create_commit_on_branch(
        self,
        *,
        branch_name: str,
        message: str,
        expected_head_oid: str,
        additions: list[dict[str, str]],
        deletions: list[dict[str, str]],
    ) -> str:
        """Run ``createCommitOnBranch`` and return the new commit OID."""
        headline, body = self._split_commit_message(message)
        message_input: dict[str, str] = {"headline": headline}
        if body is not None:
            message_input["body"] = body

        variables = {
            "input": {
                "branch": {
                    "repositoryNameWithOwner": self._repo_full_name,
                    "branchName": branch_name,
                },
                "message": message_input,
                "expectedHeadOid": expected_head_oid,
                "fileChanges": {
                    "additions": additions,
                    "deletions": deletions,
                },
            }
        }

        _, data = self._github_requester().graphql_query(
            _CREATE_COMMIT_ON_BRANCH_MUTATION,
            variables,
        )
        try:
            oid = data["data"]["createCommitOnBranch"]["commit"]["oid"]
        except (KeyError, TypeError) as err:
            raise RuntimeError(f"createCommitOnBranch returned unexpected payload: {data}") from err
        return str(oid)

    @staticmethod
    def _is_expected_head_mismatch(exc: BaseException) -> bool:
        text = str(exc).lower()
        return "expectedheadoid" in text or "expected the head" in text

    def _api_commit_files_on_branch(
        self,
        *,
        branch_name: str,
        message: str,
        file_paths: list[str] | None = None,
        deletions: list[str] | None = None,
        force: bool = False,
    ) -> str:
        """
        Create a verified commit on a branch (GraphQL or REST Git Data).

        Default: GraphQL ``createCommitOnBranch`` for ordinary ``100644`` files.
        Falls back to REST when the change includes executables, symlinks, or a
        mode change GraphQL cannot apply. Both paths must be GitHub-verified;
        REST refuses to update the ref if ``verification.verified`` is false.

        Args:
            branch_name: Target branch (created on the remote if missing).
            message: Commit message (first line = headline, rest = body).
            file_paths: Paths to add or update (read from the local worktree).
            deletions: Paths to delete in the commit.
            force: Kept for call-site compatibility; both paths require a
                matching expected head (no force-push of divergent history).
        """
        del force  # Signed API paths cannot force-update divergent refs.
        addition_paths = list(file_paths or [])
        deletion_paths = list(deletions or [])
        if not addition_paths and not deletion_paths:
            raise ValueError("file_paths/deletions must not be empty for API commit")

        repo_root = Path(self.repo.working_tree_dir or ".")
        expected_head = self._ensure_remote_branch(branch_name=branch_name)
        use_rest = self._worktree_paths_require_rest(
            file_paths=addition_paths, repo_root=repo_root
        ) or self._paths_mode_conflict_with_base(
            base_sha=expected_head,
            file_paths=addition_paths,
            repo_root=repo_root,
        )

        def _publish(expected: str) -> str:
            if use_rest:
                logger.info(
                    "Using verified REST Git Data commit on %s (GraphQL cannot "
                    "represent executable/symlink/mode changes)",
                    branch_name,
                )
                return self._rest_create_commit_on_branch(
                    branch_name=branch_name,
                    message=message,
                    expected_head_oid=expected,
                    file_paths=addition_paths,
                    deletions=deletion_paths,
                )
            return self._graphql_create_commit_on_branch(
                branch_name=branch_name,
                message=message,
                expected_head_oid=expected,
                additions=self._build_file_additions(
                    file_paths=addition_paths, repo_root=repo_root
                ),
                deletions=[
                    {"path": self._normalize_repo_rel_path(path)} for path in deletion_paths
                ],
            )

        try:
            commit_sha = _publish(expected_head)
        except GithubException as err:
            if not self._is_expected_head_mismatch(err):
                raise
            logger.warning(
                "expectedHeadOid mismatch on %s; fetching and retrying once: %s",
                branch_name,
                err,
            )
            self.fetch()
            expected_head = self._ensure_remote_branch(branch_name=branch_name)
            commit_sha = _publish(expected_head)

        self.fetch()
        logger.info("Verified API commit %s on %s", commit_sha, branch_name)
        return commit_sha

    def _api_merge(self, *, base: str, head: str, message: str) -> str:
        """
        Merge ``head`` into ``base`` via the GitHub REST merges API.

        Kept on REST (not GraphQL) because ``POST /repos/{owner}/{repo}/merges``
        already produces a GitHub-signed, verified merge commit. There is no
        GraphQL equivalent that preserves merge semantics.
        """
        gh_repo = self._gh_repo()
        result = gh_repo.merge(base=base, head=head, commit_message=message)
        if result is None or not getattr(result, "sha", None):
            raise RuntimeError(f"Merge API returned no commit for {head} -> {base}")
        logger.info("Verified API merge %s into %s (%s)", head, base, result.sha)
        return str(result.sha)

    def _api_create_lightweight_tag(self, *, tag: str, sha: str) -> str:
        """Create a lightweight tag ref via the GitHub API."""
        gh_repo = self._gh_repo()
        ref_name = f"tags/{tag}"
        try:
            ref = gh_repo.get_git_ref(ref_name)
            ref.edit(sha=sha, force=True)
        except GithubException:
            gh_repo.create_git_ref(f"refs/{ref_name}", sha)
        logger.info("Verified API tag %s -> %s", tag, sha)
        return tag
