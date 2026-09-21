"""Tests for parser ignore-line filtering."""

import re

from auto_semver.core.commits.parser import CommitParser


def test_parser_skips_checkbox_lines_when_configured() -> None:
    """Ignore patterns drop checklist lines in expand_body parsing."""
    parser = CommitParser(ignore_line_patterns=[re.compile(r"^\[[ xX]\]")])
    body = "- [x] Tests added and passing\n- Real change item"
    parsed = parser.parse(f"feat: example\n\n{body}")

    assert parsed.bullet_points == ["Real change item"]
