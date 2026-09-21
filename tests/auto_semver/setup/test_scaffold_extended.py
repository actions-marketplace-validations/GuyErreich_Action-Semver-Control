"""Extended tests for repository scaffolding helpers."""

import logging
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from auto_semver.setup.scaffold import (
    RepoRef,
    detect_repo,
    scaffold_files,
    set_repo_secret,
    set_repo_variable,
    verify_gh_authenticated,
)


@pytest.mark.unit
def test_detect_repo_parses_remote_and_default_branch(
    mocker: MockerFixture,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """detect_repo reads origin URL and symbolic-ref for default branch."""
    mocker.patch(
        "auto_semver.setup.scaffold.subprocess.run",
        side_effect=[
            mocker.Mock(returncode=0, stdout="https://github.com/acme/demo.git\n"),
            mocker.Mock(returncode=0, stdout="refs/remotes/origin/dev\n"),
        ],
    )
    with caplog.at_level(logging.INFO, logger="auto_semver.setup.scaffold"):
        ref = detect_repo(tmp_path)
    assert ref == RepoRef(owner="acme", repo="demo", default_branch="dev")
    assert any("Detected repo acme/demo" in r.message for r in caplog.records)


@pytest.mark.unit
def test_detect_repo_falls_back_to_master_when_no_symbolic_ref(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """When origin/HEAD is missing, default branch is master."""
    mocker.patch(
        "auto_semver.setup.scaffold.subprocess.run",
        side_effect=[
            mocker.Mock(returncode=0, stdout="git@github.com:acme/demo.git"),
            mocker.Mock(returncode=1, stdout=""),
        ],
    )
    ref = detect_repo(tmp_path)
    assert ref.default_branch == "master"


@pytest.mark.unit
def test_scaffold_files_writes_missing_targets(
    tmp_path: Path,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """scaffold_files creates config and workflow files when absent."""
    mocker.patch(
        "auto_semver.setup.scaffold.load_template",
        side_effect=lambda name: f"content:{name}",
    )
    with caplog.at_level(logging.INFO, logger="auto_semver.setup.scaffold"):
        written = scaffold_files(tmp_path)
    assert len(written) == 3
    assert (tmp_path / "auto_semver_config.yml").read_text(encoding="utf-8") == (
        "content:auto_semver_config.yml"
    )
    assert any("Scaffolded 3 files" in r.message for r in caplog.records)


@pytest.mark.unit
def test_scaffold_files_skips_existing(tmp_path: Path, mocker: MockerFixture) -> None:
    """scaffold_files does not overwrite existing files."""
    mocker.patch("auto_semver.setup.scaffold.load_template", return_value="new")
    (tmp_path / "auto_semver_config.yml").write_text("existing", encoding="utf-8")
    written = scaffold_files(tmp_path)
    assert len(written) == 2
    assert (tmp_path / "auto_semver_config.yml").read_text(encoding="utf-8") == "existing"


@pytest.mark.unit
def test_scaffold_files_dry_run_lists_without_write(tmp_path: Path, mocker: MockerFixture) -> None:
    """Dry run returns paths without creating files."""
    mocker.patch("auto_semver.setup.scaffold.load_template", return_value="content")
    written = scaffold_files(tmp_path, dry_run=True)
    assert len(written) == 3
    assert not (tmp_path / "auto_semver_config.yml").exists()


@pytest.mark.unit
def test_set_repo_secret_skips_on_dry_run(mocker: MockerFixture) -> None:
    """Dry run does not invoke gh secret set."""
    mock_run = mocker.patch("auto_semver.setup.scaffold.subprocess.run")
    set_repo_secret(owner="acme", repo="demo", name="GH_APP_ID", value="1", dry_run=True)
    mock_run.assert_not_called()


@pytest.mark.unit
def test_set_repo_secret_invokes_gh(mocker: MockerFixture) -> None:
    """set_repo_secret calls gh with repo and secret name."""
    mock_run = mocker.patch("auto_semver.setup.scaffold.subprocess.run")
    set_repo_secret(
        owner="acme", repo="demo", name="GH_APP_PRIVATE_KEY", value="pem", dry_run=False
    )
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0] == [
        "gh",
        "secret",
        "set",
        "GH_APP_PRIVATE_KEY",
        "--repo",
        "acme/demo",
    ]


@pytest.mark.unit
def test_set_repo_variable_invokes_gh(mocker: MockerFixture) -> None:
    """set_repo_variable calls gh variable set with body."""
    mock_run = mocker.patch("auto_semver.setup.scaffold.subprocess.run")
    set_repo_variable(
        owner="acme",
        repo="demo",
        name="GH_APP_CLIENT_ID",
        value="Iv1.test",
        dry_run=False,
    )
    mock_run.assert_called_once_with(
        ["gh", "variable", "set", "GH_APP_CLIENT_ID", "--repo", "acme/demo", "--body", "Iv1.test"],
        check=True,
    )


@pytest.mark.unit
def test_verify_gh_authenticated(mocker: MockerFixture) -> None:
    """verify_gh_authenticated runs gh auth status."""
    mock_run = mocker.patch("auto_semver.setup.scaffold.subprocess.run")
    verify_gh_authenticated()
    mock_run.assert_called_once_with(
        ["gh", "auth", "status"],
        check=True,
        capture_output=True,
        text=True,
    )
