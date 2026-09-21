# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""
GHA-shaped scenario: signed finalize then auto-promote on a dirty runner worktree.

Reproduces Auto Semver Bump failure after Release 1.6.12-dev where GraphQL
lock rewrite left ``.semver.lock`` dirty and ``git checkout staging`` aborted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from git import Repo
from git.exc import HookExecutionError
from pytest_mock import MockerFixture

from auto_semver.adapters.git import GitOps
from auto_semver.adapters.github import GitHubEvent
from auto_semver.adapters.github.event import _GITHUB_EVENT_PATH_ENV
from auto_semver.cli import finalize
from auto_semver.config import Config
from auto_semver.core.semver import SemverLock, Version


def _write_lock(
    path: Path,
    *,
    version: str,
    source_branch: str,
    target_branch: str,
    target_base_sha: str,
    finalized: bool = False,
) -> None:
    path.write_text(
        yaml.dump(
            {
                "version": version,
                "source_branch": source_branch,
                "target_branch": target_branch,
                "target_base_sha": target_base_sha,
                "finalized": finalized,
                "managed_by": "auto-semver",
                "branch_role": "release" if not finalized else None,
            },
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _init_gha_style_repos(tmp_path: Path) -> tuple[Path, Path, str]:
    """Create bare origin + clone with divergent ``dev`` and ``staging`` tips."""
    bare = tmp_path / "origin.git"
    Repo.init(bare, bare=True)

    seed = tmp_path / "seed"
    seed.mkdir()
    seed_repo = Repo.init(seed)
    seed_repo.config_writer().set_value("user", "name", "Test").release()
    seed_repo.config_writer().set_value("user", "email", "test@example.com").release()
    seed_repo.create_remote("origin", str(bare))

    (seed / "version.txt").write_text("1.0.0-rc\n", encoding="utf-8")
    (seed / "auto_semver_config.yml").write_text(
        """
start_version: "0.1.0"
suffixes:
  dev: "-dev"
  staging: "-rc"
  master: ""
promotions:
  - from_branch: dev
    to_branch: staging
    auto_promote: true
  - from_branch: staging
    to_branch: master
    auto_promote: false
version_files:
  - version.txt
release:
  strategy: single
  branch_prefix: auto-semver/release/
  cleanup_merged: false
pull_request:
  title: "Release {{ version }}"
  body: |
    {{ changelog }}
    <!-- auto-semver -->
  labels:
    - semver-bump
changelog:
  file: CHANGELOG.md
  title: "Changelog"
""",
        encoding="utf-8",
    )
    (seed / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0.0-rc\n\n- seed\n", encoding="utf-8")
    _write_lock(
        seed / ".semver.lock",
        version="1.0.0-rc",
        source_branch="dev",
        target_branch="staging",
        target_base_sha="stagingbase",
        finalized=True,
    )
    seed_repo.index.add(["version.txt", "auto_semver_config.yml", ".semver.lock", "CHANGELOG.md"])
    seed_repo.index.commit("chore: seed staging")
    seed_repo.create_head("staging")
    seed_repo.git.push("origin", "staging")

    seed_repo.git.checkout("-b", "dev")
    (seed / "version.txt").write_text("1.0.0-dev\n", encoding="utf-8")
    merge_sha = "abc123merge"
    _write_lock(
        seed / ".semver.lock",
        version="1.0.0-dev",
        source_branch="auto-semver/release/1.0.0-dev",
        target_branch="dev",
        target_base_sha=merge_sha,
        finalized=False,
    )
    seed_repo.index.add(["version.txt", ".semver.lock"])
    seed_repo.index.commit("Release 1.0.0-dev")
    seed_repo.git.push("origin", "dev")
    seed_repo.create_tag("1.0.0-dev")
    seed_repo.git.push("origin", "1.0.0-dev")

    clone = tmp_path / "workspace"
    clone_repo = Repo.clone_from(str(bare), clone, branch="dev")
    clone_repo.config_writer().set_value("user", "name", "auto-semver-bot").release()
    clone_repo.config_writer().set_value("user", "email", "bot@users.noreply.github.com").release()
    # GitOps requires a GitHub remote URL; map it back to the local bare repo.
    clone_repo.delete_remote(clone_repo.remotes.origin)
    clone_repo.create_remote("origin", "https://github.com/owner/repo.git")
    clone_repo.git.config(f"url.{bare}.insteadOf", "https://github.com/owner/repo.git")
    clone_repo.git.fetch("--all", "--tags")
    # Match Actions checkout: only the event branch is local until we create others.
    for head in list(clone_repo.heads):
        if head.name != "dev":
            clone_repo.delete_head(head, force=True)

    return bare, clone, clone_repo.head.commit.hexsha


def _install_failing_hooks(repo_path: Path) -> Path:
    """Install ``core.hooksPath`` with a ``pre-commit`` that always fails."""
    hooks_dir = repo_path / ".githooks-fail"
    hooks_dir.mkdir(exist_ok=True)
    pre_commit = hooks_dir / "pre-commit"
    pre_commit.write_text(
        "#!/bin/sh\necho 'hook deliberately fails' >&2\nexit 1\n", encoding="utf-8"
    )
    pre_commit.chmod(0o755)
    Repo(repo_path).git.config("core.hooksPath", str(hooks_dir))
    return hooks_dir


@pytest.mark.integration
def test_signed_commit_resets_worktree_after_graphql(tmp_path: Path, mocker: MockerFixture) -> None:
    """Signed commit must leave a clean worktree matching the published tip."""
    _, clone, _ = _init_gha_style_repos(tmp_path)
    os.chdir(clone)

    published_sha = Repo(clone).head.commit.hexsha
    lock_path = Path(clone) / ".semver.lock"
    lock_path.write_text(
        lock_path.read_text(encoding="utf-8").replace("finalized: false", "finalized: true"),
        encoding="utf-8",
    )
    Repo(clone).index.add([".semver.lock"])

    gitops = GitOps(
        repo_path=str(clone),
        signed_commits=True,
        github_token="token",
    )
    mocker.patch.object(
        gitops,
        "_api_commit_files_on_branch",
        return_value=published_sha,
    )
    mocker.patch.object(gitops, "fetch")

    gitops.commit("chore: finalize semver lock for 1.0.0-dev")

    assert not Repo(clone).is_dirty(index=True, working_tree=True, untracked_files=False)
    assert Repo(clone).head.commit.hexsha == published_sha


@pytest.mark.integration
def test_local_commit_skips_failing_pre_commit_hooks(tmp_path: Path) -> None:
    """Unsigned local commits must ignore consumer pre-commit hooks (``git commit -n``)."""
    _, clone, _ = _init_gha_style_repos(tmp_path)
    os.chdir(clone)
    _install_failing_hooks(Path(clone))

    # Prove the hook is installed and would block a normal GitPython commit.
    version_path = Path(clone) / "version.txt"
    version_path.write_text("hook-probe\n", encoding="utf-8")
    probe_repo = Repo(clone)
    probe_repo.index.add(["version.txt"])
    with pytest.raises(HookExecutionError):
        probe_repo.index.commit("should fail under pre-commit")

    version_path.write_text("1.0.0-dev-hooked\n", encoding="utf-8")
    gitops = GitOps(repo_path=str(clone))
    gitops.add(files=["version.txt"])
    gitops.commit(message="chore: bump despite failing hooks")

    head = Repo(clone).head.commit
    assert "chore: bump despite failing hooks" in head.message
    assert head.author.name == gitops._identity.name
    assert head.author.email == gitops._identity.email


@pytest.mark.integration
def test_dirty_lock_does_not_block_signed_promote_checkout(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """
    GHA job shape: dirty ``.semver.lock`` on ``dev`` then promote to ``staging``.

    Before the fix, checkout failed with:
    ``Your local changes to the following files would be overwritten by checkout``.
    """
    bare, clone, _ = _init_gha_style_repos(tmp_path)
    os.chdir(clone)
    clone_repo = Repo(clone)

    # Simulate GraphQL lock rewrite that updated remote but left the runner dirty.
    lock_path = Path(clone) / ".semver.lock"
    dirty_contents = lock_path.read_text(encoding="utf-8").replace(
        "finalized: false", "finalized: true"
    )
    lock_path.write_text(dirty_contents, encoding="utf-8")
    assert clone_repo.is_dirty(index=False, working_tree=True, untracked_files=False)

    publish_calls: list[dict[str, Any]] = []

    def fake_publish(*, branch_name: str, base_sha: str, message: str) -> str:
        tip = Repo(clone).head.commit.hexsha
        publish_calls.append(
            {"branch_name": branch_name, "base_sha": base_sha, "message": message, "tip": tip}
        )
        # Mirror createCommitOnBranch: advance remote staging once.
        Repo(clone).git.push("origin", f"{tip}:refs/heads/staging", force=True)
        return tip

    gitops = GitOps(
        repo_path=str(clone),
        signed_commits=True,
        github_token="token",
    )
    mocker.patch.object(gitops, "_publish_local_tip_once", side_effect=fake_publish)
    mocker.patch.object(gitops, "_api_create_lightweight_tag", return_value="1.0.0-rc")

    result = gitops._auto_promote_api(
        source_branch="1.0.0-dev",
        target_branch="staging",
        version="1.0.0-rc",
        source_version="1.0.0-dev",
        merge_message=("chore: auto-promote 1.0.0-dev from 1.0.0-dev to staging as 1.0.0-rc"),
        is_source_tag=True,
        post_merge_hook=None,
        prefer_source_paths=[".semver.lock", "version.txt"],
    )

    assert result == "1.0.0-rc"
    assert len(publish_calls) == 1
    assert publish_calls[0]["branch_name"] == "staging"
    assert publish_calls[0]["tip"] != publish_calls[0]["base_sha"]
    assert Repo(bare).commit("staging").hexsha == publish_calls[0]["tip"]
    assert Repo(clone).active_branch.name == "staging"


@pytest.mark.integration
def test_gha_finalize_then_promote_with_signed_commits(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """
    End-to-end GHA job order: finalize (tag + lock) then auto-promote to staging.

    Mirrors ``.github/workflows/auto-semver.yml`` after a release PR merge with
    ``signed-commits: true``, using a real two-branch git layout and mocked
    GitHub GraphQL / tag APIs.
    """
    bare, clone, merge_sha = _init_gha_style_repos(tmp_path)
    os.chdir(clone)
    # Consumer hooks must not abort finalize/promote (GraphQL + skip_hooks local path).
    _install_failing_hooks(Path(clone))

    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "action": "closed",
                "pull_request": {
                    "title": "Release 1.0.0-dev",
                    "body": "<!-- auto-semver -->\n",
                    "merged": True,
                    "merge_commit_sha": merge_sha,
                    "head": {
                        "ref": "auto-semver/release/1.0.0-dev",
                        "sha": "deadbeef",
                    },
                    "base": {"ref": "dev", "sha": merge_sha},
                    "labels": [{"name": "semver-bump"}],
                },
                "repository": {"full_name": "owner/repo"},
            }
        ),
        encoding="utf-8",
    )
    mocker.patch.dict(
        os.environ,
        {
            _GITHUB_EVENT_PATH_ENV: str(event_path),
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_WORKSPACE": str(clone),
            "GITHUB_REPOSITORY": "owner/repo",
        },
    )

    publish_calls: list[str] = []

    def fake_api_commit(
        *,
        branch_name: str,
        message: str,
        file_paths: list[str] | None = None,
        deletions: list[str] | None = None,
        force: bool = False,
    ) -> str:
        del deletions, force
        # Simulate GraphQL: commit files into a new local commit, return its SHA.
        repo = Repo(clone)
        if file_paths:
            repo.index.add(file_paths)
        # GraphQL path never runs hooks; mirror that in the local stand-in.
        commit = repo.index.commit(message, skip_hooks=True)
        # Push object + ref to bare the way createCommitOnBranch updates GitHub.
        repo.git.push("origin", f"{commit.hexsha}:refs/heads/{branch_name}", force=True)
        return commit.hexsha

    def fake_publish(*, branch_name: str, base_sha: str, message: str) -> str:
        del message, base_sha
        tip = Repo(clone).head.commit.hexsha
        publish_calls.append(tip)
        Repo(clone).git.push("origin", f"{tip}:refs/heads/{branch_name}", force=True)
        return tip

    tagged: list[tuple[str, str]] = []

    def fake_tag(*, tag: str, sha: str) -> str:
        tagged.append((tag, sha))
        Repo(clone).git.push("origin", f"{sha}:refs/tags/{tag}", force=True)
        return tag

    gitops = GitOps(
        repo_path=str(clone),
        signed_commits=True,
        github_token="token",
    )
    mocker.patch.object(gitops, "_api_commit_files_on_branch", side_effect=fake_api_commit)
    mocker.patch.object(gitops, "_publish_local_tip_once", side_effect=fake_publish)
    mocker.patch.object(gitops, "_api_create_lightweight_tag", side_effect=fake_tag)
    # Local lightweight tag for create_and_push_tag path before promote.
    mocker.patch.object(
        gitops,
        "tag",
        side_effect=lambda *, tag, branch: Repo(clone).create_tag(tag, force=True).name,
    )
    mocker.patch.object(gitops, "push")

    config = Config()
    event = GitHubEvent()
    # Ensure lock matches finalize expectations.
    lock = SemverLock.load_from_file()
    lock.version = Version.parse("1.0.0-dev")
    lock.save_to_file()
    Repo(clone).index.add([".semver.lock"])
    Repo(clone).index.commit("chore: sync lock for finalize test", skip_hooks=True)

    finalize.run(gitops=gitops, event=event, config=config, github_token="token")

    assert len(publish_calls) == 1
    assert ("1.0.0-rc", publish_calls[0]) in tagged
    staging_tip = Repo(bare).commit("staging").hexsha
    assert staging_tip == publish_calls[0]
    # Runner worktree must be clean enough that promote already switched branches.
    assert not Repo(clone).is_dirty(index=True, working_tree=True, untracked_files=False)
