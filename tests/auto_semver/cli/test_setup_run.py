"""Tests for setup.run onboarding flow."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from auto_semver.cli import setup
from auto_semver.setup.scaffold import RepoRef


@pytest.mark.unit
def test_setup_run_full_flow_with_explicit_owner(
    mocker: MockerFixture,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """setup.run scaffolds files and sets credentials when fully configured."""
    mocker.patch("auto_semver.cli.setup.webbrowser.open")
    mocker.patch("auto_semver.cli.setup.verify_gh_authenticated")
    mock_secret = mocker.patch("auto_semver.cli.setup.set_repo_secret")
    mock_variable = mocker.patch("auto_semver.cli.setup.set_repo_variable")
    key_file = tmp_path / "key.pem"
    key_file.write_text("-----BEGIN KEY-----\n", encoding="utf-8")
    mocker.patch(
        "auto_semver.cli.setup.scaffold_files",
        return_value=[tmp_path / "auto_semver_config.yml"],
    )

    setup.run(
        owner="acme",
        repo="demo",
        default_branch="dev",
        client_id="Iv1.test",
        private_key_path=key_file,
        dry_run=False,
        skip_scaffold=False,
        skip_secrets=False,
    )

    mock_variable.assert_called_once()
    assert mock_variable.call_args.kwargs["name"] == "GH_APP_CLIENT_ID"
    mock_secret.assert_called_once()
    assert mock_secret.call_args.kwargs["name"] == "GH_APP_PRIVATE_KEY"
    out = capsys.readouterr().out
    assert "Action-Semver-Control setup" in out
    assert "acme/demo" in out
    assert "semver-bump.reusable.yml" in out


@pytest.mark.unit
def test_setup_run_skip_secrets_and_scaffold(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """Flags skip secret write and file scaffold paths."""
    mocker.patch("auto_semver.cli.setup.verify_gh_authenticated")
    mock_secret = mocker.patch("auto_semver.cli.setup.set_repo_secret")
    mock_scaffold = mocker.patch("auto_semver.cli.setup.scaffold_files")

    setup.run(
        owner="acme",
        repo="demo",
        default_branch="master",
        dry_run=True,
        skip_secrets=True,
        skip_scaffold=True,
    )

    mock_secret.assert_not_called()
    mock_scaffold.assert_not_called()
    out = capsys.readouterr().out
    assert "Skipped credential configuration" in out
    assert "Skipped file scaffolding" in out


@pytest.mark.unit
def test_setup_run_opens_browser(mocker: MockerFixture, tmp_path: Path) -> None:
    """open_browser opens registration URL when not dry-run."""
    mock_browser = mocker.patch("auto_semver.cli.setup.webbrowser.open")
    mocker.patch("auto_semver.cli.setup.verify_gh_authenticated")
    mocker.patch("auto_semver.cli.setup.set_repo_secret")
    mocker.patch("auto_semver.cli.setup.set_repo_variable")
    mocker.patch("auto_semver.cli.setup.scaffold_files", return_value=[])
    key_file = tmp_path / "key.pem"
    key_file.write_text("pem", encoding="utf-8")

    setup.run(
        owner="acme",
        repo="demo",
        open_browser=True,
        skip_secrets=False,
        skip_scaffold=True,
        client_id="Iv1.test",
        private_key_path=key_file,
    )

    mock_browser.assert_called_once()


@pytest.mark.unit
def test_resolve_repo_detects_when_owner_missing(mocker: MockerFixture) -> None:
    """_resolve_repo falls back to detect_repo when owner/repo omitted."""
    detected = RepoRef(owner="org", repo="pkg", default_branch="main")
    mocker.patch("auto_semver.cli.setup.detect_repo", return_value=detected)
    ref = setup._resolve_repo(owner=None, repo=None, default_branch=None)
    assert ref == detected


@pytest.mark.unit
def test_resolve_repo_overrides_default_branch(mocker: MockerFixture) -> None:
    """Explicit default_branch overrides detected branch."""
    detected = RepoRef(owner="org", repo="pkg", default_branch="main")
    mocker.patch("auto_semver.cli.setup.detect_repo", return_value=detected)
    ref = setup._resolve_repo(owner=None, repo=None, default_branch="dev")
    assert ref.default_branch == "dev"


@pytest.mark.unit
def test_prompt_raises_on_empty(mocker: MockerFixture) -> None:
    """_prompt rejects blank input."""
    mocker.patch("builtins.input", return_value="  ")
    with pytest.raises(ValueError, match="required"):
        setup._prompt("GitHub App ID")
