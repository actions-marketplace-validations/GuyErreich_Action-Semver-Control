# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Promotion orchestration."""

from __future__ import annotations

import base64
import logging
from collections.abc import Callable, Collection
from pathlib import Path
from typing import TYPE_CHECKING

from git import GitCommandError
from git.remote import Remote
from github.GithubException import GithubException

from auto_semver.adapters.git.base import GitOpsBase
from auto_semver.config.constants import (
    VERSION_METADATA_COMMIT,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__package__)


class GitPromote(GitOpsBase):
    """Promotion orchestration."""

    def merge(
        self,
        *,
        source_ref: str,
        message: str,
        no_ff: bool = True,
        remote_name: str = "origin",
        is_tag: bool = False,
        prefer_source_paths: Collection[str] | None = None,
    ) -> None:
        """
        Merge a source ref into the current branch.

        Args:
            source_ref (str): Source reference to merge (branch name, will use remote/branch).
            message (str): Merge commit message.
            no_ff (bool): If True, create a merge commit even if fast-forward is possible.
            remote_name (str): Remote name to prefix to source_ref (default: 'origin').
            is_tag (bool): If True, treat source_ref as a tag (do not prepend remote).
            prefer_source_paths: Relative paths where conflicts may be auto-resolved by
                taking the source (theirs) side. Used during promotion for version
                metadata files that diverge by design between branches.

        Raises:
            RuntimeError: If merge fails due to conflicts or other errors.
        """
        if is_tag:
            full_source_ref = source_ref
        else:
            full_source_ref = f"{remote_name}/{source_ref}"

        logger.info(f"Merging '{full_source_ref}' into current branch (no-ff={no_ff})")

        try:
            self.repo.git.merge(full_source_ref, no_ff=no_ff, m=message)
            logger.info(f"Merge successful: {full_source_ref} → HEAD")
        except GitCommandError as merge_err:
            stderr = str(merge_err)
            if "CONFLICT" in stderr or "conflict" in stderr.lower():
                if prefer_source_paths and self._resolve_promotion_conflicts(
                    prefer_source_paths=prefer_source_paths,
                    merge_message=message,
                ):
                    logger.info(
                        "Resolved promotion-file conflicts preferring source; merge completed"
                    )
                    return

                logger.error(f"Merge conflict detected: {merge_err}")
                # Attempt to abort the merge to keep repo clean
                try:
                    self.repo.git.merge("--abort")
                    logger.debug("Aborted merge after conflict")
                except Exception:
                    logger.warning("Failed to abort merge after conflict")

                raise RuntimeError(
                    f"Merge conflict detected when merging '{full_source_ref}'. "
                    "Please resolve conflicts manually."
                ) from merge_err

            logger.error(f"Merge failed: {merge_err}")
            raise RuntimeError(f"Merge failed: {merge_err}") from merge_err

    def _unmerged_paths(self) -> list[str]:
        """Return paths with unresolved merge conflicts."""
        raw = self.repo.git.diff(name_only=True, diff_filter="U")
        if not raw:
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _resolve_promotion_conflicts(
        self,
        *,
        prefer_source_paths: Collection[str],
        merge_message: str,
    ) -> bool:
        """
        Resolve conflicts by taking the source (theirs) side for allowlisted paths.

        Returns True when every conflicted path was allowlisted and the merge was
        completed; False when unresolved or non-allowlisted conflicts remain.
        """
        allowed = {str(Path(p)).replace("\\", "/") for p in prefer_source_paths}
        conflicted = self._unmerged_paths()
        if not conflicted:
            return False

        normalized = [str(Path(p)).replace("\\", "/") for p in conflicted]
        disallowed = [p for p in normalized if p not in allowed]
        if disallowed:
            logger.error(
                "Cannot auto-resolve merge conflicts outside promotion files: %s",
                ", ".join(disallowed),
            )
            return False

        for path in conflicted:
            logger.info("Preferring source version for conflicted file: %s", path)
            self.repo.git.checkout("--theirs", "--", path)
            self.repo.git.add("--", path)

        remaining = self._unmerged_paths()
        if remaining:
            logger.error("Unresolved conflicts remain after prefer-source: %s", remaining)
            return False

        # Complete the in-progress merge without re-invoking git merge.
        self.repo.git.commit(m=merge_message, no_edit=False)
        logger.info("Completed merge after resolving promotion-file conflicts")
        return True

    def _resolve_ref_sha(self, ref: str) -> str:
        """Resolve a branch or tag name to a commit SHA."""
        try:
            return str(self.repo.commit(ref).hexsha)
        except GitCommandError as err:
            raise RuntimeError(f"Could not resolve ref '{ref}': {err}") from err

    def _squash_commit_from_ref(self, *, ref: str, message: str) -> str:
        """
        Create a single promotion commit whose tree matches ``ref``.

        Uses the current branch tip as the sole parent so protected branches that
        reject merge commits still receive a linear promote commit.
        """
        source_commit = self.repo.commit(ref)
        parent = self.repo.head.commit
        new_sha = str(
            self.repo.git.commit_tree(
                source_commit.tree.hexsha,
                "-p",
                parent.hexsha,
                "-m",
                message,
            )
        )
        self.repo.head.set_commit(self.repo.commit(new_sha))
        # HEAD moved but index/worktree still reflect pre-promotion target; sync before hooks.
        self.repo.git.reset("--hard", new_sha)
        logger.info("Created squash promotion commit %s from %s", new_sha[:8], ref)
        return new_sha

    def _integrate_source_for_promotion(
        self,
        *,
        source_ref: str,
        message: str,
        remote_name: str,
        is_tag: bool,
        prefer_source_paths: Collection[str] | None,
    ) -> None:
        """
        Integrate a promotion source into the current branch.

        Tag sources try fast-forward first, then fall back to a single squash commit
        (no merge commit). Branch sources merge with ff when possible and auto-resolve
        metadata conflicts by preferring the source side.
        """
        full_ref = source_ref if is_tag else f"{remote_name}/{source_ref}"

        if is_tag:
            try:
                self.repo.git.merge(full_ref, ff_only=True)
                logger.info("Fast-forward promotion merge successful: %s", full_ref)
                return
            except GitCommandError as err:
                stderr = str(err)
                if "CONFLICT" in stderr or "conflict" in stderr.lower():
                    raise RuntimeError(
                        f"Fast-forward promotion conflict for '{full_ref}'. "
                        "Resolve manually before promoting."
                    ) from err
                logger.info(
                    "Fast-forward not possible for %s; creating squash promotion commit",
                    full_ref,
                )
                self._squash_commit_from_ref(ref=full_ref, message=message)
                return

        self.merge(
            source_ref=source_ref,
            message=message,
            remote_name=remote_name,
            is_tag=False,
            prefer_source_paths=prefer_source_paths,
            no_ff=False,
        )

    def _api_squash_promote(self, *, base: str, head: str, message: str) -> str:
        """
        Create a single verified commit on ``base`` whose tree matches ``head``.

        Uses GraphQL ``createCommitOnBranch`` with the file diff from
        ``base...head`` so the resulting commit is GitHub-signed.
        """
        gh_repo = self._gh_repo()
        base_ref = gh_repo.get_git_ref(f"heads/{base}")
        base_sha = str(base_ref.object.sha)
        head_sha = self._resolve_ref_sha(head)

        comparison = gh_repo.compare(base_sha, head_sha)
        additions: list[dict[str, str]] = []
        deletions: list[dict[str, str]] = []

        for file in comparison.files or []:
            path = self._normalize_repo_rel_path(file.filename)
            status = (file.status or "").lower()
            if status == "removed":
                deletions.append({"path": path})
                continue
            if status == "renamed" and file.previous_filename:
                deletions.append({"path": self._normalize_repo_rel_path(file.previous_filename)})
            content_file = gh_repo.get_contents(path, ref=head_sha)
            if isinstance(content_file, list):
                raise RuntimeError(f"Expected a file at {path}@{head_sha}, got a directory listing")
            raw = bytes(content_file.decoded_content)
            additions.append(
                {
                    "path": path,
                    "contents": base64.b64encode(raw).decode("ascii"),
                }
            )

        if not additions and not deletions:
            logger.info(
                "Squash promote %s -> %s has no file diff; leaving %s at %s",
                head,
                base,
                base,
                base_sha,
            )
            return base_sha

        try:
            commit_sha = self._graphql_create_commit_on_branch(
                branch_name=base,
                message=message,
                expected_head_oid=base_sha,
                additions=additions,
                deletions=deletions,
            )
        except GithubException as err:
            if not self._is_expected_head_mismatch(err):
                raise
            logger.warning(
                "expectedHeadOid mismatch on squash promote to %s; retrying once: %s",
                base,
                err,
            )
            self.fetch()
            base_ref = gh_repo.get_git_ref(f"heads/{base}")
            base_sha = str(base_ref.object.sha)
            commit_sha = self._graphql_create_commit_on_branch(
                branch_name=base,
                message=message,
                expected_head_oid=base_sha,
                additions=additions,
                deletions=deletions,
            )

        logger.info("Verified squash promotion commit on %s (%s)", base, commit_sha)
        return commit_sha

    def _integrate_source_for_promotion_api(
        self,
        *,
        target_branch: str,
        source_ref: str,
        message: str,
        is_source_tag: bool,
    ) -> str:
        """Integrate promotion source via GitHub API (ff merge or squash commit)."""
        try:
            return self._api_merge(base=target_branch, head=source_ref, message=message)
        except (GithubException, RuntimeError) as err:
            if not is_source_tag:
                raise
            logger.info(
                "API merge failed for tag promotion (%s); using squash commit: %s",
                source_ref,
                err,
            )
            return self._api_squash_promote(base=target_branch, head=source_ref, message=message)

    def auto_promote(
        self,
        *,
        source_branch: str,
        target_branch: str,
        version: str,
        source_version: str | None = None,
        remote_name: str = "origin",
        is_source_tag: bool = False,
        post_merge_hook: Callable[[str, str], None] | None = None,
        prefer_source_paths: Collection[str] | None = None,
    ) -> str:
        """
        Automatically promote changes from source branch to target branch.

        This performs a local merge operation (SCM-agnostic) that:
        1. Fetches latest changes from remote
        2. Checks out/creates the target branch
        3. Pulls latest changes on target
        4. Merges source branch into target
        5. Creates a tag on target
        6. Pushes target branch and tags to remote

        Args:
            source_branch (str): Source branch name (e.g., 'dev') or tag name.
            target_branch (str): Target branch name (e.g., 'staging').
            version (str): Version tag to create on the target branch.
            source_version (str | None): Original version tag from source branch.
            remote_name (str): Remote name (default: 'origin').
            is_source_tag (bool): If True, treat source_branch as a tag.
            post_merge_hook (Callable[[str, str], None] | None): Optional hook function to execute after merge
            but before commit/tag.
            Receives (source_version_str, target_version_str).
            prefer_source_paths: Paths to auto-resolve favoring the source branch on
                conflict (changelog, lockfile, version files).

        Returns:
            str: The version tag that was created.

        Raises:
            RuntimeError: If any operation fails (fetch, merge, push, etc.).
        """
        logger.info(f"Starting auto-promotion: {source_branch} → {target_branch}")

        if source_version:
            merge_message = (
                f"chore: auto-promote {source_version} from {source_branch} "
                f"to {target_branch} as {version}"
            )
        else:
            merge_message = (
                f"chore: auto-promote from {source_branch} to {target_branch} as {version}"
            )

        if self.signed_commits:
            return self._auto_promote_api(
                source_branch=source_branch,
                target_branch=target_branch,
                version=version,
                source_version=source_version,
                merge_message=merge_message,
                is_source_tag=is_source_tag,
                post_merge_hook=post_merge_hook,
                prefer_source_paths=prefer_source_paths,
                remote_name=remote_name,
            )

        try:
            # 1. Fetch latest changes
            self.fetch(remote_name=remote_name)

            # 2. Checkout or create target branch
            if target_branch in self.repo.heads:
                self.checkout(branch_name=target_branch)
            else:
                self.checkout(
                    branch_name=target_branch, create_from=f"{remote_name}/{target_branch}"
                )

            # 3. Pull latest changes on target
            self.pull(branch_name=target_branch, remote_name=remote_name)

            # 4. Integrate source into target (ff, squash, or merge + metadata wins)
            self._integrate_source_for_promotion(
                source_ref=source_branch,
                message=merge_message,
                remote_name=remote_name,
                is_tag=is_source_tag,
                prefer_source_paths=prefer_source_paths,
            )

            # Executing post-merge hook if provided
            if post_merge_hook:
                logger.info("Executing post-merge hook")
                # Fallback to source_branch if version not explicit
                src_v = source_version if source_version else source_branch

                try:
                    post_merge_hook(src_v, version)

                    dirty_paths = self._collect_dirty_tracked_paths()
                    if dirty_paths:
                        logger.info(
                            "Changes detected after post-merge hook; committing metadata: %s",
                            ", ".join(dirty_paths),
                        )
                        for path in dirty_paths:
                            self.repo.git.add("--", path)
                        self._local_commit(VERSION_METADATA_COMMIT.format(version=version))
                except Exception as e:
                    logger.error(f"Post-merge hook failed: {e}")
                    raise RuntimeError(f"Post-merge hook failed: {e}") from e

            # 5. Create tag on target branch
            logger.info(f"Creating tag '{version}' on '{target_branch}'")
            tag_ref = self.repo.create_tag(version, message=f"Auto-promotion: {version}")

            # 6. Push target branch
            self.push(branch_name=target_branch, remote_name=remote_name)

            # 7. Push tags
            logger.info("Pushing tags to remote")
            remote: Remote = self.repo.remote(name=remote_name)
            remote.push(tags=True)

            logger.info(
                f"✅ Auto-promotion complete: {source_branch} → {target_branch} (tagged: {version})"
            )

            return str(tag_ref)

        except (GitCommandError, RuntimeError) as err:
            logger.error(f"Auto-promotion failed: {err}")
            raise RuntimeError(f"Auto-promotion failed: {err}") from err
        except Exception as err:
            logger.error(f"Unexpected error during auto-promotion: {err}")
            raise RuntimeError(f"Auto-promotion failed unexpectedly: {err}") from err

    def _diff_paths_between(
        self, *, base_sha: str, head_ref: str = "HEAD"
    ) -> tuple[list[str], list[str]]:
        """Return (additions/modifications, deletions) between two commits."""
        added = self.repo.git.diff(base_sha, head_ref, "--name-only", "--diff-filter=ACMR")
        deleted = self.repo.git.diff(base_sha, head_ref, "--name-only", "--diff-filter=D")
        additions = [line.strip() for line in added.splitlines() if line.strip()]
        deletions = [line.strip() for line in deleted.splitlines() if line.strip()]
        return additions, deletions

    def _remote_has_commit(self, sha: str) -> bool:
        """Return True when ``sha`` is already present on the GitHub remote."""
        try:
            self._gh_repo().get_git_commit(sha)
        except GithubException:
            return False
        return True

    def _publish_local_tip_once(
        self,
        *,
        branch_name: str,
        base_sha: str,
        message: str,
    ) -> str:
        """
        Move ``branch_name`` to the local tip with a single remote ref update.

        Fast-forwards the branch when HEAD already exists on the remote and
        matches ``base_sha``'s descendant with no unpublished local-only history
        that needs signing. Otherwise publishes the final worktree as one
        verified ``createCommitOnBranch`` or REST Git Data commit so promote +
        metadata never produce two push events on the integration branch. REST
        is used when the tip needs executable/symlink modes GraphQL cannot
        express.
        """
        local_tip = self.repo.head.commit.hexsha
        if local_tip == base_sha:
            logger.info("No promotion changes on %s; leaving branch at %s", branch_name, base_sha)
            return base_sha

        additions, deletions = self._diff_paths_between(base_sha=base_sha, head_ref=local_tip)
        if not additions and not deletions:
            if self._remote_has_commit(local_tip):
                ref = self._gh_repo().get_git_ref(f"heads/{branch_name}")
                ref.edit(sha=local_tip)
                self.fetch()
                logger.info(
                    "Fast-forwarded %s to existing commit %s (single ref update)",
                    branch_name,
                    local_tip,
                )
                return local_tip
            logger.info(
                "Empty tree diff for %s but tip %s is local-only; leaving at %s",
                branch_name,
                local_tip,
                base_sha,
            )
            return base_sha

        # Prefer a true fast-forward when the tip is already on the remote and
        # there are no local-only commits beyond that tip (e.g. tag promote ff).
        if self._remote_has_commit(local_tip):
            try:
                self.repo.git.merge_base("--is-ancestor", base_sha, local_tip)
                ref = self._gh_repo().get_git_ref(f"heads/{branch_name}")
                ref.edit(sha=local_tip)
                self.fetch()
                logger.info(
                    "Fast-forwarded %s to %s (single ref update)",
                    branch_name,
                    local_tip,
                )
                return local_tip
            except GitCommandError:
                pass

        repo_root = Path(self.repo.working_tree_dir or ".")
        use_rest = self._tree_diff_requires_rest(base_sha=base_sha, head_ref=local_tip)

        def _publish_tip(expected: str) -> str:
            if use_rest:
                logger.info(
                    "Publishing promotion tip on %s via verified REST "
                    "(GraphQL cannot represent executable/symlink/mode changes)",
                    branch_name,
                )
                return self._rest_create_commit_on_branch(
                    branch_name=branch_name,
                    message=message,
                    expected_head_oid=expected,
                    file_paths=additions,
                    deletions=deletions,
                )
            return self._graphql_create_commit_on_branch(
                branch_name=branch_name,
                message=message,
                expected_head_oid=expected,
                additions=self._build_file_additions(
                    file_paths=additions,
                    repo_root=repo_root,
                ),
                deletions=[{"path": self._normalize_repo_rel_path(path)} for path in deletions],
            )

        try:
            commit_sha = _publish_tip(base_sha)
        except GithubException as err:
            if not self._is_expected_head_mismatch(err):
                raise
            logger.warning(
                "expectedHeadOid mismatch publishing tip on %s; retrying once: %s",
                branch_name,
                err,
            )
            self.fetch()
            expected_head = self._ensure_remote_branch(branch_name=branch_name)
            commit_sha = _publish_tip(expected_head)
        self.fetch()
        logger.info(
            "Published verified promotion tip %s on %s (single ref update)",
            commit_sha,
            branch_name,
        )
        return commit_sha

    def _auto_promote_api(
        self,
        *,
        source_branch: str,
        target_branch: str,
        version: str,
        source_version: str | None,
        merge_message: str,
        is_source_tag: bool,
        post_merge_hook: Callable[[str, str], None] | None,
        prefer_source_paths: Collection[str] | None = None,
        remote_name: str = "origin",
    ) -> str:
        """
        Promote via local integrate + one verified remote tip update.

        Builds promote (and optional metadata) commits locally, then moves the
        target branch once so concurrent workflows (e.g. Secret Scan) are not
        canceled by a second push from the same job.
        """
        self.fetch(remote_name=remote_name)
        # Signed finalize may leave the worktree dirty if a prior sync was
        # skipped; discard local dirt so checkout of the promote target works.
        if self.repo.is_dirty(index=True, working_tree=True, untracked_files=False):
            logger.warning(
                "Dirty worktree before promote checkout; resetting to HEAD "
                "(remote already has signed changes)"
            )
            self.repo.git.reset("--hard", "HEAD")
        if target_branch in self.repo.heads:
            self.checkout(branch_name=target_branch)
        else:
            self.checkout(
                branch_name=target_branch,
                create_from=f"{remote_name}/{target_branch}",
            )
        self.pull(branch_name=target_branch, remote_name=remote_name)
        base_sha = self.repo.head.commit.hexsha

        self._integrate_source_for_promotion(
            source_ref=source_branch,
            message=merge_message,
            remote_name=remote_name,
            is_tag=is_source_tag,
            prefer_source_paths=prefer_source_paths,
        )

        if post_merge_hook:
            logger.info("Executing post-merge hook")
            src_v = source_version if source_version else source_branch
            try:
                post_merge_hook(src_v, version)
                dirty_paths = self._collect_dirty_tracked_paths()
                if dirty_paths:
                    logger.info(
                        "Changes detected after post-merge hook; committing metadata locally: %s",
                        ", ".join(dirty_paths),
                    )
                    for path in dirty_paths:
                        self.repo.git.add("--", path)
                    # Local-only; folded into the single verified tip published below.
                    self._local_commit(VERSION_METADATA_COMMIT.format(version=version))
            except Exception as exc:
                logger.error(f"Post-merge hook failed: {exc}")
                raise RuntimeError(f"Post-merge hook failed: {exc}") from exc

        tip_sha = self._publish_local_tip_once(
            branch_name=target_branch,
            base_sha=base_sha,
            message=merge_message,
        )
        self._api_create_lightweight_tag(tag=version, sha=tip_sha)
        self.fetch(remote_name=remote_name)
        logger.info(
            "✅ Verified auto-promotion complete: %s → %s (tagged: %s)",
            source_branch,
            target_branch,
            version,
        )
        return version
