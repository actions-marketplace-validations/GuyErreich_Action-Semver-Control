# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Unit tests for GitHubRenderer."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from runview import get_summary, log_group
from runview.config import Config
from runview.renderers.github import GitHubRenderer
from runview.reporter import install
from runview.summary import RunSummary


class _CaptureStdout:
    """Collect writes for assertion."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, data: str) -> int:
        self.lines.append(data)
        return len(data)

    def flush(self) -> None:
        return None


class TestGitHubRenderer:
    """Tests for Actions annotations, groups, and step summary."""

    @pytest.mark.unit
    def test_warning_emits_single_annotation_only(self, mocker: MockerFixture) -> None:
        """WARNING emits exactly one ::warning:: line and no plain duplicate."""
        capture = _CaptureStdout()
        mocker.patch("runview.renderers.github.sys.stdout", capture)
        mocker.patch("runview.renderers.plain.sys.stdout", capture)

        renderer = GitHubRenderer(Config(app_name="test", style="github"))
        renderer.message(logging.WARNING, "warn\nline")
        renderer.message(logging.ERROR, "boom%1")
        renderer.message(logging.INFO, "ok")

        out = "".join(capture.lines)
        assert out.count("::warning::") == 1
        assert out.count("::error::") == 1
        assert "%0A" in out
        assert "%25" in out
        assert "ok\n" in out
        # No plain duplicate of the warning text alongside the annotation.
        assert "warn\nline" not in out
        matching = [line for line in out.splitlines() if "warn%0Aline" in line]
        assert matching == ["::warning::warn%0Aline"]

    @pytest.mark.unit
    def test_groups_and_info_inside(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Non-TTY GitHub install prints INFO between group markers."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        mocker.patch.object(GitHubRenderer, "open")
        install(
            Config(
                app_name="auto-semver",
                default_log_file=str(tmp_path / "gha.log"),
                style="github",
                debug=True,
            )
        )

        with log_group("Tag"):
            logging.getLogger("auto_semver").info("Tagging branch")
            logging.getLogger("auto_semver").debug("hidden from stdout")

        out = capsys.readouterr().out
        assert "::group::Tag" in out
        assert "Tagging branch" in out
        assert "hidden from stdout" not in out
        assert " | " not in out.split("Tagging branch")[0].splitlines()[-1]
        assert "::endgroup::" in out
        assert out.index("::group::Tag") < out.index("Tagging branch") < out.index("::endgroup::")

    @pytest.mark.unit
    def test_flush_writes_step_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """flush_summary appends markdown to GITHUB_STEP_SUMMARY."""
        summary_path = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
        mocker.patch.object(GitHubRenderer, "open")
        reporter = install(
            Config(
                app_name="auto-semver",
                default_log_file=str(tmp_path / "a.log"),
                style="github",
            )
        )
        with log_group("Resolve version"):
            pass
        get_summary().set("version", "1.0.0")
        reporter.close()
        content = summary_path.read_text(encoding="utf-8")
        assert "auto-semver" in content
        assert "1.0.0" in content


class TestRunSummary:
    """Tests for RunSummary rendering."""

    @pytest.mark.unit
    def test_as_markdown(self) -> None:
        """as_markdown produces a GFM table."""
        summary = RunSummary(app_name="auto-semver")
        summary.set("command", "bump")
        md = summary.as_markdown()
        assert "| **command** | bump |" in md
