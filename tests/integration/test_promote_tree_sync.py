# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Promote must delete paths removed or renamed on the source tag (issue 322)."""

from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo
from pytest_mock import MockerFixture

from auto_semver.adapters.git import GitOps


def _init_promote_tree_repos(tmp_path: Path) -> tuple[Path, Path]:
    """Bare origin + clone: staging has leftovers that the source tag deletes/renames."""
    bare = tmp_path / "origin.git"
    Repo.init(bare, bare=True)

    seed = tmp_path / "seed"
    seed.mkdir()
    seed_repo = Repo.init(seed)
    seed_repo.config_writer().set_value("user", "name", "Test").release()
    seed_repo.config_writer().set_value("user", "email", "test@example.com").release()
    seed_repo.create_remote("origin", str(bare))

    (seed / "version.txt").write_text("1.0.0-rc\n", encoding="utf-8")
    (seed / "gone.txt").write_text("stale\n", encoding="utf-8")
    (seed / "old_name.txt").write_text("same-payload\n", encoding="utf-8")
    seed_repo.index.add(["version.txt", "gone.txt", "old_name.txt"])
    seed_repo.index.commit("chore: seed staging")
    seed_repo.create_head("staging")
    seed_repo.git.push("origin", "staging")

    seed_repo.git.checkout("-b", "dev")
    (seed / "version.txt").write_text("1.0.0-dev\n", encoding="utf-8")
    seed_repo.git.rm("gone.txt")
    seed_repo.git.mv("old_name.txt", "new_name.txt")
    seed_repo.index.add(["version.txt"])
    seed_repo.index.commit("chore: drop and rename on source")
    seed_repo.git.push("origin", "dev")
    seed_repo.create_tag("1.0.0-dev")
    seed_repo.git.push("origin", "1.0.0-dev")

    # Diverge staging so promote cannot fast-forward and must squash to the tag tree.
    seed_repo.git.checkout("staging")
    (seed / "staging_only.txt").write_text("target-only leftover\n", encoding="utf-8")
    seed_repo.index.add(["staging_only.txt"])
    seed_repo.index.commit("chore: staging-only file")
    seed_repo.git.push("origin", "staging")

    clone = tmp_path / "workspace"
    clone_repo = Repo.clone_from(str(bare), clone, branch="dev")
    clone_repo.config_writer().set_value("user", "name", "auto-semver-bot").release()
    clone_repo.config_writer().set_value("user", "email", "bot@users.noreply.github.com").release()
    clone_repo.delete_remote(clone_repo.remotes.origin)
    clone_repo.create_remote("origin", "https://github.com/owner/repo.git")
    clone_repo.git.config(f"url.{bare}.insteadOf", "https://github.com/owner/repo.git")
    clone_repo.git.fetch("--all", "--tags")
    for head in list(clone_repo.heads):
        if head.name != "dev":
            clone_repo.delete_head(head, force=True)

    return bare, clone


@pytest.mark.integration
def test_unsigned_tag_promote_deletes_removed_and_renamed_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Squash promote tree must drop files the source tag deleted or renamed."""
    _, clone = _init_promote_tree_repos(tmp_path)
    monkeypatch.chdir(clone)

    gitops = GitOps(repo_path=str(clone))
    gitops.fetch()
    gitops.checkout(branch_name="staging", create_from="origin/staging")
    gitops._integrate_source_for_promotion(
        source_ref="1.0.0-dev",
        message="chore: auto-promote",
        remote_name="origin",
        is_tag=True,
        prefer_source_paths=None,
    )

    root = Path(clone)
    assert not (root / "gone.txt").exists()
    assert not (root / "old_name.txt").exists()
    assert not (root / "staging_only.txt").exists()
    assert (root / "new_name.txt").read_text(encoding="utf-8") == "same-payload\n"
    tracked = set(gitops.repo.git.ls_tree("-r", "--name-only", "HEAD").splitlines())
    assert "gone.txt" not in tracked
    assert "old_name.txt" not in tracked
    assert "staging_only.txt" not in tracked
    assert "new_name.txt" in tracked


@pytest.mark.integration
def test_signed_publish_lists_delete_and_rename_old_paths(
    tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GraphQL overlay deletions must include removed files and rename old-paths."""
    _, clone = _init_promote_tree_repos(tmp_path)
    monkeypatch.chdir(clone)

    gitops = GitOps(repo_path=str(clone), signed_commits=True, github_token="token")
    gitops.fetch()
    gitops.checkout(branch_name="staging", create_from="origin/staging")
    base_sha = Repo(clone).head.commit.hexsha
    gitops._integrate_source_for_promotion(
        source_ref="1.0.0-dev",
        message="chore: auto-promote",
        remote_name="origin",
        is_tag=True,
        prefer_source_paths=None,
    )

    mocker.patch.object(gitops, "_remote_has_commit", return_value=False)
    mocker.patch.object(gitops, "_tree_diff_requires_rest", return_value=False)
    mocker.patch.object(gitops, "fetch")
    mock_gql = mocker.patch.object(
        gitops,
        "_graphql_create_commit_on_branch",
        return_value="published-sha",
    )

    result = gitops._publish_local_tip_once(
        branch_name="staging",
        base_sha=base_sha,
        message="chore: auto-promote",
    )

    assert result == "published-sha"
    kwargs = mock_gql.call_args.kwargs
    deletion_paths = {item["path"] for item in kwargs["deletions"]}
    addition_paths = {item["path"] for item in kwargs["additions"]}
    assert "gone.txt" in deletion_paths
    assert "old_name.txt" in deletion_paths
    assert "staging_only.txt" in deletion_paths
    assert "new_name.txt" in addition_paths
