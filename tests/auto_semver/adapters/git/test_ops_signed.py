# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Tests for verified (GraphQL createCommitOnBranch) GitOps commits."""

from __future__ import annotations

import base64
from typing import Any

import pytest
from github import GithubException
from pytest_mock import MockerFixture

from auto_semver.adapters.git.ops import GitOps


class TestSignedGitOps:
    """Verify API-backed commit/merge/tag paths."""

    @pytest.fixture
    def mock_repo(self, mocker: MockerFixture) -> Any:
        """Provide a minimal GitPython repo double."""
        mock = mocker.MagicMock()
        mock.git = mocker.MagicMock()
        mock.git.diff.side_effect = self._diff_side_effect
        mock.active_branch.name = "release/1.0.0-dev"
        mock.working_tree_dir = "/github/workspace"
        mock.head.commit.hexsha = "localhead"
        mock.is_dirty.return_value = False
        mock_remote = mocker.MagicMock()
        mock_remote.url = "git@github.com:owner/repo.git"
        mock.remote.return_value = mock_remote
        return mock

    @staticmethod
    def _diff_side_effect(*args: str, **_kwargs: Any) -> str:
        """Return staged paths based on ``--diff-filter``."""
        if "--diff-filter=D" in args:
            return ""
        if "--diff-filter=ACMR" in args:
            return "pyproject.toml\n"
        if "--cached" in args and "--name-only" in args:
            return "pyproject.toml\n"
        return "pyproject.toml\n"

    @pytest.fixture(autouse=True)
    def patch_repo(self, mocker: MockerFixture, mock_repo: Any) -> None:
        """Patch Repo construction for every signed GitOps test."""
        mocker.patch("auto_semver.adapters.git.local.Repo", return_value=mock_repo)
        mocker.patch(
            "auto_semver.adapters.git.local.GitLocal._parse_repository_name",
            return_value="owner/repo",
        )

    @pytest.mark.unit
    def test_signed_commits_requires_token(self) -> None:
        """Reject signed mode without a GitHub token."""
        with pytest.raises(ValueError, match="github_token is required"):
            GitOps(signed_commits=True)

    @pytest.mark.unit
    def test_api_commit_uses_graphql_create_commit_on_branch(
        self, mocker: MockerFixture, mock_repo: Any, tmp_path: Any
    ) -> None:
        """Signed commit should call createCommitOnBranch with base64 contents."""
        mock_repo.working_tree_dir = str(tmp_path)
        file_path = tmp_path / "pyproject.toml"
        file_content = 'version = "1.0.0"\n'
        file_path.write_text(file_content, encoding="utf-8")

        mock_gh_repo = mocker.MagicMock()
        mock_ref = mocker.MagicMock()
        mock_ref.object.sha = "abc123"
        mock_gh_repo.get_git_ref.return_value = mock_ref

        mock_requester = mocker.MagicMock()
        mock_requester.graphql_query.return_value = (
            {},
            {"data": {"createCommitOnBranch": {"commit": {"oid": "commitsha"}}}},
        )

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "_gh_repo", return_value=mock_gh_repo)
        mocker.patch.object(gitops, "_github_requester", return_value=mock_requester)
        mocker.patch.object(gitops, "fetch")

        gitops.commit("Release 1.0.0-dev", force=True)

        mock_requester.graphql_query.assert_called_once()
        query, variables = mock_requester.graphql_query.call_args.args
        assert "createCommitOnBranch" in query
        assert variables["input"]["expectedHeadOid"] == "abc123"
        assert variables["input"]["branch"]["branchName"] == "release/1.0.0-dev"
        assert variables["input"]["message"]["headline"] == "Release 1.0.0-dev"
        additions = variables["input"]["fileChanges"]["additions"]
        assert len(additions) == 1
        assert additions[0]["path"] == "pyproject.toml"
        assert additions[0]["contents"] == base64.b64encode(file_content.encode()).decode("ascii")
        assert variables["input"]["fileChanges"]["deletions"] == []
        mock_gh_repo.create_git_commit.assert_not_called()
        mock_repo.git.reset.assert_called_once_with("--hard", "commitsha")

    @pytest.mark.unit
    def test_api_commit_includes_staged_deletions(
        self, mocker: MockerFixture, mock_repo: Any, tmp_path: Any
    ) -> None:
        """Staged deletions should appear in fileChanges.deletions."""
        mock_repo.working_tree_dir = str(tmp_path)
        kept = tmp_path / "version.txt"
        kept.write_text("1.0.0\n", encoding="utf-8")

        def diff_side_effect(*args: str, **_kwargs: Any) -> str:
            if "--diff-filter=D" in args:
                return "obsolete.txt\n"
            if "--diff-filter=ACMR" in args:
                return "version.txt\n"
            return "version.txt\nobsolete.txt\n"

        mock_repo.git.diff.side_effect = diff_side_effect

        mock_gh_repo = mocker.MagicMock()
        mock_ref = mocker.MagicMock()
        mock_ref.object.sha = "tipsha"
        mock_gh_repo.get_git_ref.return_value = mock_ref

        mock_requester = mocker.MagicMock()
        mock_requester.graphql_query.return_value = (
            {},
            {"data": {"createCommitOnBranch": {"commit": {"oid": "newsha"}}}},
        )

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "_gh_repo", return_value=mock_gh_repo)
        mocker.patch.object(gitops, "_github_requester", return_value=mock_requester)
        mocker.patch.object(gitops, "fetch")

        gitops.commit("chore: drop obsolete file")

        _, variables = mock_requester.graphql_query.call_args.args
        assert variables["input"]["fileChanges"]["deletions"] == [{"path": "obsolete.txt"}]
        assert variables["input"]["fileChanges"]["additions"][0]["path"] == "version.txt"
        mock_repo.git.reset.assert_called_once_with("--hard", "newsha")

    @pytest.mark.unit
    def test_api_commit_retries_on_expected_head_mismatch(
        self, mocker: MockerFixture, mock_repo: Any, tmp_path: Any
    ) -> None:
        """Retry once when expectedHeadOid no longer matches the remote tip."""
        mock_repo.working_tree_dir = str(tmp_path)
        (tmp_path / "pyproject.toml").write_text("x = 1\n", encoding="utf-8")

        mock_gh_repo = mocker.MagicMock()
        first_ref = mocker.MagicMock()
        first_ref.object.sha = "oldtip"
        second_ref = mocker.MagicMock()
        second_ref.object.sha = "newtip"
        mock_gh_repo.get_git_ref.side_effect = [first_ref, second_ref]

        mismatch = GithubException(
            400,
            {
                "errors": [
                    {"message": "expectedHeadOid was outdated"},
                ]
            },
            None,
        )
        mock_requester = mocker.MagicMock()
        mock_requester.graphql_query.side_effect = [
            mismatch,
            (
                {},
                {"data": {"createCommitOnBranch": {"commit": {"oid": "retriedsha"}}}},
            ),
        ]

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "_gh_repo", return_value=mock_gh_repo)
        mocker.patch.object(gitops, "_github_requester", return_value=mock_requester)
        mock_fetch = mocker.patch.object(gitops, "fetch")

        gitops.commit("Release 1.0.0-dev")

        assert mock_requester.graphql_query.call_count == 2
        second_vars = mock_requester.graphql_query.call_args_list[1].args[1]
        assert second_vars["input"]["expectedHeadOid"] == "newtip"
        assert mock_fetch.call_count >= 1
        mock_repo.git.reset.assert_called_once_with("--hard", "retriedsha")

    @pytest.mark.unit
    def test_api_commit_routes_executable_to_verified_rest(
        self, mocker: MockerFixture, mock_repo: Any, tmp_path: Any
    ) -> None:
        """Executable staged files use verified REST instead of GraphQL."""
        mock_repo.working_tree_dir = str(tmp_path)
        script = tmp_path / "tool.sh"
        script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
        script.chmod(0o755)

        def diff_side_effect(*args: str, **_kwargs: Any) -> str:
            if "--diff-filter=D" in args:
                return ""
            return "tool.sh\n"

        mock_repo.git.diff.side_effect = diff_side_effect

        mock_gh_repo = mocker.MagicMock()
        mock_ref = mocker.MagicMock()
        mock_ref.object.sha = "tip"
        mock_gh_repo.get_git_ref.return_value = mock_ref

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "_gh_repo", return_value=mock_gh_repo)
        mock_rest = mocker.patch.object(
            gitops, "_rest_create_commit_on_branch", return_value="rest-sha"
        )
        mock_gql = mocker.patch.object(gitops, "_graphql_create_commit_on_branch")
        mocker.patch.object(gitops, "fetch")

        gitops.commit("chore: add tool")

        mock_rest.assert_called_once()
        assert mock_rest.call_args.kwargs["file_paths"] == ["tool.sh"]
        mock_gql.assert_not_called()
        mock_repo.git.reset.assert_called_once_with("--hard", "rest-sha")

    @pytest.mark.unit
    def test_rest_commit_requires_verified_before_ref_update(
        self, mocker: MockerFixture, mock_repo: Any, tmp_path: Any
    ) -> None:
        """REST path must not move the branch when verification.verified is false."""
        mock_repo.working_tree_dir = str(tmp_path)
        script = tmp_path / "tool.sh"
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        script.chmod(0o755)

        mock_gh_repo = mocker.MagicMock()
        mock_parent = mocker.MagicMock()
        mock_parent.tree = mocker.MagicMock()
        mock_gh_repo.get_git_commit.side_effect = [
            mock_parent,  # parent for create
            mocker.MagicMock(  # verification lookup
                verification=mocker.MagicMock(verified=False, reason="unsigned")
            ),
        ]
        mock_blob = mocker.MagicMock()
        mock_blob.sha = "blobsha"
        mock_gh_repo.create_git_blob.return_value = mock_blob
        mock_tree = mocker.MagicMock()
        mock_gh_repo.create_git_tree.return_value = mock_tree
        mock_commit = mocker.MagicMock()
        mock_commit.sha = "unsigned-sha"
        mock_gh_repo.create_git_commit.return_value = mock_commit
        mock_ref = mocker.MagicMock()
        mock_ref.object.sha = "base-sha"
        mock_gh_repo.get_git_ref.return_value = mock_ref

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "_gh_repo", return_value=mock_gh_repo)

        with pytest.raises(RuntimeError, match="not GitHub-verified"):
            gitops._rest_create_commit_on_branch(
                branch_name="staging",
                message="chore: tool",
                expected_head_oid="base-sha",
                file_paths=["tool.sh"],
                deletions=[],
            )

        mock_ref.edit.assert_not_called()
        # author/committer must be omitted for App signing
        _args, kwargs = mock_gh_repo.create_git_commit.call_args
        assert "author" not in kwargs
        assert "committer" not in kwargs

    @pytest.mark.unit
    def test_rest_commit_updates_ref_when_verified(
        self, mocker: MockerFixture, mock_repo: Any, tmp_path: Any
    ) -> None:
        """Verified REST commits may update the branch ref."""
        mock_repo.working_tree_dir = str(tmp_path)
        script = tmp_path / "tool.sh"
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        script.chmod(0o755)

        mock_gh_repo = mocker.MagicMock()
        mock_parent = mocker.MagicMock()
        mock_parent.tree = mocker.MagicMock()
        mock_verified = mocker.MagicMock(
            verification=mocker.MagicMock(verified=True, reason="valid")
        )
        mock_gh_repo.get_git_commit.side_effect = [mock_parent, mock_verified]
        mock_blob = mocker.MagicMock()
        mock_blob.sha = "blobsha"
        mock_gh_repo.create_git_blob.return_value = mock_blob
        mock_gh_repo.create_git_tree.return_value = mocker.MagicMock()
        mock_commit = mocker.MagicMock()
        mock_commit.sha = "verified-sha"
        mock_gh_repo.create_git_commit.return_value = mock_commit
        mock_ref = mocker.MagicMock()
        mock_ref.object.sha = "base-sha"
        mock_gh_repo.get_git_ref.return_value = mock_ref

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "_gh_repo", return_value=mock_gh_repo)

        sha = gitops._rest_create_commit_on_branch(
            branch_name="staging",
            message="chore: tool",
            expected_head_oid="base-sha",
            file_paths=["tool.sh"],
            deletions=[],
        )

        assert sha == "verified-sha"
        mock_ref.edit.assert_called_once_with(sha="verified-sha", force=False)
        blob_args = mock_gh_repo.create_git_blob.call_args.args
        assert blob_args[1] == "base64"

    @pytest.mark.unit
    def test_publish_tip_routes_mode_change_to_rest(
        self, mocker: MockerFixture, mock_repo: Any, tmp_path: Any
    ) -> None:
        """Mode-only 100755→100644 diffs publish via verified REST."""
        mock_repo.working_tree_dir = str(tmp_path)
        hook = tmp_path / "hook.py"
        hook.write_text("print('hi')\n", encoding="utf-8")
        # 100644 in worktree; base was 100755
        mock_repo.head.commit.hexsha = "local-tip"

        def diff_side_effect(*args: str, **_kwargs: Any) -> str:
            if "--raw" in args:
                return ":100755 100644 abc def M\thook.py\n"
            if "--diff-filter=D" in args:
                return ""
            if "--diff-filter=ACMR" in args:
                return "hook.py\n"
            return "hook.py\n"

        mock_repo.git.diff.side_effect = diff_side_effect

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "_remote_has_commit", return_value=False)
        mock_rest = mocker.patch.object(
            gitops, "_rest_create_commit_on_branch", return_value="rest-tip"
        )
        mock_gql = mocker.patch.object(gitops, "_graphql_create_commit_on_branch")
        mocker.patch.object(gitops, "fetch")

        result = gitops._publish_local_tip_once(
            branch_name="staging",
            base_sha="base-sha",
            message="chore: promote",
        )

        assert result == "rest-tip"
        mock_rest.assert_called_once()
        assert mock_rest.call_args.kwargs["file_paths"] == ["hook.py"]
        mock_gql.assert_not_called()

    @pytest.mark.unit
    def test_api_merge_promotion(self, mocker: MockerFixture, mock_repo: Any) -> None:
        """Signed auto-promote integrates locally and publishes one tip."""
        mock_repo.head.commit.hexsha = "base-sha"
        mock_repo.heads = mocker.MagicMock()
        mock_repo.heads.__contains__.return_value = True

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "fetch")
        mock_checkout = mocker.patch.object(gitops, "checkout")
        mocker.patch.object(gitops, "pull")
        mock_integrate = mocker.patch.object(gitops, "_integrate_source_for_promotion")
        mock_publish = mocker.patch.object(
            gitops,
            "_publish_local_tip_once",
            return_value="tip-sha",
        )
        mock_tag = mocker.patch.object(
            gitops,
            "_api_create_lightweight_tag",
            return_value="1.0.0-rc",
        )
        mock_merge_api = mocker.patch.object(gitops, "_integrate_source_for_promotion_api")

        result = gitops._auto_promote_api(
            source_branch="dev",
            target_branch="staging",
            version="1.0.0-rc",
            source_version="1.0.0-dev",
            merge_message="chore: promote",
            is_source_tag=False,
            post_merge_hook=None,
        )

        assert result == "1.0.0-rc"
        mock_checkout.assert_called_once_with(branch_name="staging")
        mock_integrate.assert_called_once_with(
            source_ref="dev",
            message="chore: promote",
            remote_name="origin",
            is_tag=False,
            prefer_source_paths=None,
        )
        mock_publish.assert_called_once_with(
            branch_name="staging",
            base_sha="base-sha",
            message="chore: promote",
        )
        mock_tag.assert_called_once_with(tag="1.0.0-rc", sha="tip-sha")
        mock_merge_api.assert_not_called()

    @pytest.mark.unit
    def test_api_promote_resets_dirty_worktree_before_checkout(
        self, mocker: MockerFixture, mock_repo: Any
    ) -> None:
        """Dirty .semver.lock must not block checkout of the promote target."""
        mock_repo.head.commit.hexsha = "base-sha"
        mock_repo.heads = mocker.MagicMock()
        mock_repo.heads.__contains__.return_value = True
        mock_repo.is_dirty.return_value = True

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "fetch")
        mock_checkout = mocker.patch.object(gitops, "checkout")
        mocker.patch.object(gitops, "pull")
        mocker.patch.object(gitops, "_integrate_source_for_promotion")
        mocker.patch.object(
            gitops,
            "_publish_local_tip_once",
            return_value="tip-sha",
        )
        mocker.patch.object(
            gitops,
            "_api_create_lightweight_tag",
            return_value="1.0.0-rc",
        )

        result = gitops._auto_promote_api(
            source_branch="1.0.0-dev",
            target_branch="staging",
            version="1.0.0-rc",
            source_version="1.0.0-dev",
            merge_message="chore: promote",
            is_source_tag=True,
            post_merge_hook=None,
        )

        assert result == "1.0.0-rc"
        mock_repo.is_dirty.assert_called()
        mock_repo.git.reset.assert_any_call("--hard", "HEAD")
        mock_checkout.assert_called_once_with(branch_name="staging")

    @pytest.mark.unit
    def test_api_promote_post_merge_creates_local_target_branch(
        self, mocker: MockerFixture, mock_repo: Any
    ) -> None:
        """Post-merge hook should create local target from origin when missing."""
        mock_repo.head.commit.hexsha = "base-sha"
        mock_repo.heads = mocker.MagicMock()
        mock_repo.heads.__contains__.return_value = False

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "fetch")
        mock_checkout = mocker.patch.object(gitops, "checkout")
        mocker.patch.object(gitops, "pull")
        mocker.patch.object(gitops, "_integrate_source_for_promotion")
        mocker.patch.object(gitops, "_collect_dirty_tracked_paths", return_value=[])
        mock_publish = mocker.patch.object(
            gitops,
            "_publish_local_tip_once",
            return_value="tip-sha",
        )
        mock_tag = mocker.patch.object(
            gitops,
            "_api_create_lightweight_tag",
            return_value="1.0.0-rc",
        )
        hook = mocker.MagicMock()

        result = gitops._auto_promote_api(
            source_branch="1.0.0-dev",
            target_branch="staging",
            version="1.0.0-rc",
            source_version="1.0.0-dev",
            merge_message="chore: promote",
            is_source_tag=True,
            post_merge_hook=hook,
            remote_name="origin",
        )

        assert result == "1.0.0-rc"
        mock_checkout.assert_called_once_with(
            branch_name="staging",
            create_from="origin/staging",
        )
        hook.assert_called_once_with("1.0.0-dev", "1.0.0-rc")
        mock_publish.assert_called_once_with(
            branch_name="staging",
            base_sha="base-sha",
            message="chore: promote",
        )
        mock_tag.assert_called_once_with(tag="1.0.0-rc", sha="tip-sha")

    @pytest.mark.unit
    def test_api_promote_dirty_hook_publishes_once(
        self, mocker: MockerFixture, mock_repo: Any
    ) -> None:
        """Metadata changes are committed locally and folded into one tip publish."""
        mock_repo.head.commit.hexsha = "base-sha"
        mock_repo.heads = mocker.MagicMock()
        mock_repo.heads.__contains__.return_value = True
        mock_index = mocker.MagicMock()
        mock_repo.index = mock_index

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "fetch")
        mocker.patch.object(gitops, "checkout")
        mocker.patch.object(gitops, "pull")
        mocker.patch.object(gitops, "_integrate_source_for_promotion")
        mocker.patch.object(
            gitops,
            "_collect_dirty_tracked_paths",
            return_value=["version.txt", ".semver.lock"],
        )
        mock_publish = mocker.patch.object(
            gitops,
            "_publish_local_tip_once",
            return_value="meta-tip-sha",
        )
        mock_tag = mocker.patch.object(
            gitops,
            "_api_create_lightweight_tag",
            return_value="1.0.0-rc",
        )
        mock_merge_api = mocker.patch.object(gitops, "_integrate_source_for_promotion_api")
        mock_api_commit = mocker.patch.object(gitops, "_api_commit_files_on_branch")
        hook = mocker.MagicMock()

        result = gitops._auto_promote_api(
            source_branch="1.0.0-dev",
            target_branch="staging",
            version="1.0.0-rc",
            source_version="1.0.0-dev",
            merge_message="chore: promote",
            is_source_tag=True,
            post_merge_hook=hook,
        )

        assert result == "1.0.0-rc"
        assert mock_repo.git.add.call_count == 2
        mock_index.commit.assert_called_once_with(
            "chore: update version metadata for 1.0.0-rc",
            author=gitops._identity,
            committer=gitops._identity,
            skip_hooks=True,
        )
        mock_publish.assert_called_once_with(
            branch_name="staging",
            base_sha="base-sha",
            message="chore: promote",
        )
        mock_tag.assert_called_once_with(tag="1.0.0-rc", sha="meta-tip-sha")
        mock_merge_api.assert_not_called()
        mock_api_commit.assert_not_called()

    @pytest.mark.unit
    def test_api_promote_clean_hook_publishes_once(
        self, mocker: MockerFixture, mock_repo: Any
    ) -> None:
        """Clean hook still results in a single tip publish and tag."""
        mock_repo.head.commit.hexsha = "base-sha"
        mock_repo.heads = mocker.MagicMock()
        mock_repo.heads.__contains__.return_value = True
        mock_index = mocker.MagicMock()
        mock_repo.index = mock_index

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "fetch")
        mocker.patch.object(gitops, "checkout")
        mocker.patch.object(gitops, "pull")
        mocker.patch.object(gitops, "_integrate_source_for_promotion")
        mocker.patch.object(gitops, "_collect_dirty_tracked_paths", return_value=[])
        mock_publish = mocker.patch.object(
            gitops,
            "_publish_local_tip_once",
            return_value="promote-tip-sha",
        )
        mock_tag = mocker.patch.object(
            gitops,
            "_api_create_lightweight_tag",
            return_value="1.0.0-rc",
        )
        hook = mocker.MagicMock()

        result = gitops._auto_promote_api(
            source_branch="1.0.0-dev",
            target_branch="staging",
            version="1.0.0-rc",
            source_version="1.0.0-dev",
            merge_message="chore: promote",
            is_source_tag=True,
            post_merge_hook=hook,
        )

        assert result == "1.0.0-rc"
        mock_index.commit.assert_not_called()
        mock_publish.assert_called_once_with(
            branch_name="staging",
            base_sha="base-sha",
            message="chore: promote",
        )
        mock_tag.assert_called_once_with(tag="1.0.0-rc", sha="promote-tip-sha")

    @pytest.mark.unit
    def test_publish_local_tip_once_uses_single_graphql_commit(
        self, mocker: MockerFixture, mock_repo: Any, tmp_path: Any
    ) -> None:
        """Local-only tip with file changes becomes one createCommitOnBranch."""
        mock_repo.working_tree_dir = str(tmp_path)
        (tmp_path / "version.txt").write_text("1.0.0-rc\n", encoding="utf-8")
        mock_repo.head.commit.hexsha = "local-tip"

        def diff_side_effect(*args: str, **_kwargs: Any) -> str:
            if "--diff-filter=D" in args:
                return ""
            if "--diff-filter=ACMR" in args:
                return "version.txt\n"
            return "version.txt\n"

        mock_repo.git.diff.side_effect = diff_side_effect

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "_remote_has_commit", return_value=False)
        mock_gql = mocker.patch.object(
            gitops,
            "_graphql_create_commit_on_branch",
            return_value="published-sha",
        )
        mocker.patch.object(gitops, "fetch")
        mock_ref_edit = mocker.MagicMock()
        mock_gh = mocker.MagicMock()
        mock_gh.get_git_ref.return_value = mock_ref_edit
        mocker.patch.object(gitops, "_gh_repo", return_value=mock_gh)

        result = gitops._publish_local_tip_once(
            branch_name="staging",
            base_sha="base-sha",
            message="chore: promote",
        )

        assert result == "published-sha"
        mock_gql.assert_called_once()
        mock_ref_edit.edit.assert_not_called()
        kwargs = mock_gql.call_args.kwargs
        assert kwargs["branch_name"] == "staging"
        assert kwargs["expected_head_oid"] == "base-sha"
        assert kwargs["additions"][0]["path"] == "version.txt"

    @pytest.mark.unit
    def test_publish_local_tip_once_fast_forwards_existing_remote_commit(
        self, mocker: MockerFixture, mock_repo: Any
    ) -> None:
        """When the tip already exists remotely, only edit the branch ref once."""
        mock_repo.head.commit.hexsha = "remote-tip"
        mock_repo.git.diff.return_value = "version.txt\n"
        mock_repo.git.merge_base.return_value = ""

        gitops = GitOps(signed_commits=True, github_token="token")
        mocker.patch.object(gitops, "_remote_has_commit", return_value=True)
        mock_gql = mocker.patch.object(gitops, "_graphql_create_commit_on_branch")
        mocker.patch.object(gitops, "fetch")
        mock_ref = mocker.MagicMock()
        mock_gh = mocker.MagicMock()
        mock_gh.get_git_ref.return_value = mock_ref
        mocker.patch.object(gitops, "_gh_repo", return_value=mock_gh)

        result = gitops._publish_local_tip_once(
            branch_name="staging",
            base_sha="base-sha",
            message="chore: promote",
        )

        assert result == "remote-tip"
        mock_ref.edit.assert_called_once_with(sha="remote-tip")
        mock_gql.assert_not_called()

    @pytest.mark.unit
    def test_api_squash_promote_uses_graphql(self, mocker: MockerFixture, mock_repo: Any) -> None:
        """Squash promote should build file changes and call createCommitOnBranch."""
        gitops = GitOps(signed_commits=True, github_token="token")

        mock_gh_repo = mocker.MagicMock()
        base_ref = mocker.MagicMock()
        base_ref.object.sha = "basesha"
        mock_gh_repo.get_git_ref.return_value = base_ref

        file_change = mocker.MagicMock()
        file_change.filename = "version.txt"
        file_change.status = "modified"
        file_change.previous_filename = None
        comparison = mocker.MagicMock()
        comparison.files = [file_change]
        mock_gh_repo.compare.return_value = comparison

        content_file = mocker.MagicMock()
        content_file.decoded_content = b"1.0.0-rc\n"
        mock_gh_repo.get_contents.return_value = content_file

        mocker.patch.object(gitops, "_gh_repo", return_value=mock_gh_repo)
        mocker.patch.object(gitops, "_resolve_ref_sha", return_value="headsha")
        mock_gql = mocker.patch.object(
            gitops,
            "_graphql_create_commit_on_branch",
            return_value="squashsha",
        )

        result = gitops._api_squash_promote(
            base="staging",
            head="1.0.0-dev",
            message="chore: promote",
        )

        assert result == "squashsha"
        mock_gql.assert_called_once()
        kwargs = mock_gql.call_args.kwargs
        assert kwargs["branch_name"] == "staging"
        assert kwargs["expected_head_oid"] == "basesha"
        assert kwargs["additions"][0]["path"] == "version.txt"
        assert kwargs["additions"][0]["contents"] == base64.b64encode(b"1.0.0-rc\n").decode("ascii")
        mock_gh_repo.create_git_commit.assert_not_called()
