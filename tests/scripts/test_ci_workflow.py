"""Python CI reports the required check names and skips the suite from a path match."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_ACTION = _REPO_ROOT / ".github" / "actions" / "changed-paths" / "action.yml"
_MATCH_PATHS = _REPO_ROOT / ".github" / "actions" / "changed-paths" / "match_paths.py"
_RUN_WHEN = "steps.python.outputs.matched == 'true'"
_REQUIRED_CHECK_NAMES = ("Python 3.12", "Python 3.13")


def _load_yaml(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _ci_job() -> dict[str, object]:
    workflow = _load_yaml(_CI_WORKFLOW)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs["ci"]
    assert isinstance(job, dict)
    return job


def _patterns() -> str:
    job = _ci_job()
    steps = job["steps"]
    assert isinstance(steps, list)
    for step in steps:
        assert isinstance(step, dict)
        if step.get("id") == "python":
            with_inputs = step["with"]
            assert isinstance(with_inputs, dict)
            patterns = with_inputs["patterns"]
            assert isinstance(patterns, str)
            return patterns
    raise AssertionError("changed-paths step not found")


def _match(paths: str, patterns: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    output = tmp_path / "github_output"
    env = os.environ.copy()
    env["PATTERNS"] = patterns
    env["GITHUB_OUTPUT"] = str(output)
    return subprocess.run(
        [sys.executable, str(_MATCH_PATHS)],
        input=paths,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def _matched_output(result: subprocess.CompletedProcess[str], tmp_path: Path) -> str:
    assert result.returncode == 0, result.stderr
    return (tmp_path / "github_output").read_text(encoding="utf-8").strip()


def test_matrix_jobs_always_start_under_the_required_names() -> None:
    """Dev and staging require Python 3.12 and Python 3.13 by those exact names.

    A job-level skip reports one check named ``Python ${{ matrix.python-version }}``
    and the required checks never start.
    """
    workflow = _load_yaml(_CI_WORKFLOW)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    assert list(jobs) == ["ci"]
    job = _ci_job()
    assert "if" not in job
    assert job["name"] == "Python ${{ matrix.python-version }}"
    strategy = job["strategy"]
    assert isinstance(strategy, dict)
    matrix = strategy["matrix"]
    assert isinstance(matrix, dict)
    versions = matrix["python-version"]
    assert versions == ["3.12", "3.13"]
    assert tuple(f"Python {version}" for version in versions) == _REQUIRED_CHECK_NAMES

    steps = job["steps"]
    assert isinstance(steps, list)
    checkout, detect, decision, *rest = steps
    assert isinstance(checkout, dict)
    assert isinstance(detect, dict)
    assert isinstance(decision, dict)
    assert checkout["uses"].startswith("actions/checkout@")
    assert "if" not in checkout
    assert detect["id"] == "python"
    assert detect["uses"] == "./.github/actions/changed-paths"
    assert "if" not in detect
    assert decision["name"] == "Report Python CI decision"
    assert "if" not in decision
    for step in rest:
        assert isinstance(step, dict)
        assert step["if"] == _RUN_WHEN


def test_changed_paths_action_matches_everything_outside_a_pull_request(tmp_path: Path) -> None:
    """workflow_dispatch and push have no pull request diff, so the suite runs."""
    action = _load_yaml(_ACTION)
    runs = action["runs"]
    assert isinstance(runs, dict)
    steps = runs["steps"]
    assert isinstance(steps, list)
    step = steps[0]
    assert isinstance(step, dict)
    script = step["run"]
    assert isinstance(script, str)
    output = tmp_path / "github_output"
    env = os.environ.copy()
    env.update(
        {
            "PR_NUMBER": "",
            "PATTERNS": "*.py",
            "REPO": "GuyErreich/Action-Semver-Control",
            "GITHUB_OUTPUT": str(output),
            "GH_TOKEN": "",
        }
    )
    result = subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8").strip() == "matched=true"
    assert "::group::Changed paths" in result.stdout
    assert "::endgroup::" in result.stdout
    assert "::notice title=Changed paths::" in result.stdout
    assert "Not a pull request" in result.stdout
    assert "Downstream steps will run." in result.stdout


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        ("src/auto_semver/cli/main.py\n", "matched=true"),
        (".github/workflows/ci.yml\n", "matched=true"),
        ("pyproject.toml\n", "matched=true"),
        ("packages/demo/uv.lock\n", "matched=true"),
        (".wtp.yml\nREADME.md\n", "matched=false"),
        ("", "matched=false"),
    ],
)
def test_ci_patterns_match_python_toolchain_paths(
    paths: str,
    expected: str,
    tmp_path: Path,
) -> None:
    """The workflow patterns cover Python source and the toolchain files."""
    result = _match(paths, _patterns(), tmp_path)
    assert _matched_output(result, tmp_path) == expected


def test_match_paths_supports_double_star_and_ignores_comments(tmp_path: Path) -> None:
    """``**`` crosses directories, and ``#`` lines are not patterns."""
    patterns = "# comment\n**/*.py\n"
    matched = _match("a/b/c.py\n", patterns, tmp_path / "hit")
    assert _matched_output(matched, tmp_path / "hit") == "matched=true"
    missed = _match("a/b/c.yml\n", patterns, tmp_path / "miss")
    assert _matched_output(missed, tmp_path / "miss") == "matched=false"


def test_match_log_explains_a_hit_with_groups_and_a_notice(tmp_path: Path) -> None:
    """A match lists patterns, files, and hits, and annotates that steps will run."""
    result = _match("src/app.py\nREADME.md\n", "*.py\n", tmp_path)
    assert _matched_output(result, tmp_path) == "matched=true"
    log = result.stdout
    assert "::group::Patterns (1)" in log
    assert "::group::Pull request files (2)" in log
    assert "::group::Matched files (1)" in log
    assert "- src/app.py" in log
    assert "- README.md" in log
    matched_section = log.split("::group::Matched files (1)", 1)[1].split("::endgroup::", 1)[0]
    assert "- src/app.py" in matched_section
    assert "README.md" not in matched_section
    assert "::notice title=Changed paths matched::" in log
    assert "Downstream steps will run." in log
    assert "matched=" not in log


def test_match_log_explains_a_skip_with_groups_and_a_notice(tmp_path: Path) -> None:
    """No match annotates that downstream steps will skip and leaves matched files empty."""
    result = _match(".wtp.yml\n", "*.py\n", tmp_path)
    assert _matched_output(result, tmp_path) == "matched=false"
    log = result.stdout
    assert "::group::Matched files (0)" in log
    assert "- (none)" in log.split("::group::Matched files (0)", 1)[1]
    assert "::notice title=Changed paths did not match::" in log
    assert ".wtp.yml" in log
    assert "Downstream steps will skip." in log


def test_percent_in_a_path_is_escaped_in_the_annotation(tmp_path: Path) -> None:
    """A percent sign in a file name must not break the workflow command."""
    result = _match("file%name.py\n", "*.py\n", tmp_path)
    assert _matched_output(result, tmp_path) == "matched=true"
    assert "file%25name.py" in result.stdout
    assert "file%name.py" not in result.stdout.split("::notice", 1)[1]


def _decision_script() -> str:
    job = _ci_job()
    steps = job["steps"]
    assert isinstance(steps, list)
    for step in steps:
        assert isinstance(step, dict)
        if step.get("name") == "Report Python CI decision":
            script = step["run"]
            assert isinstance(script, str)
            return script
    raise AssertionError("decision step not found")


@pytest.mark.parametrize(
    ("matched", "marker", "detail"),
    [
        ("true", "::notice title=Running Python 3.12::", "tests will run."),
        ("false", "::warning title=Skipping Python 3.12::", "tests are skipped."),
    ],
)
def test_python_ci_decision_annotates_skip_and_run(matched: str, marker: str, detail: str) -> None:
    """The Python job annotation says whether this version runs or skips the suite."""
    result = subprocess.run(
        ["bash", "-c", _decision_script()],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "MATCHED": matched, "PYTHON_VERSION": "3.12"},
    )
    assert result.returncode == 0, result.stderr
    assert "::group::Python 3.12 CI" in result.stdout
    assert "::endgroup::" in result.stdout
    assert marker in result.stdout
    assert detail in result.stdout
