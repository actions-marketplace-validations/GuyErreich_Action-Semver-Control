# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Unit tests for PlainRenderer."""

from __future__ import annotations

import logging

import pytest

from runview.config import Config
from runview.renderers.plain import PlainRenderer
from runview.summary import RunSummary


class TestPlainRenderer:
    """Tests for plain stdout presentation."""

    @pytest.mark.unit
    def test_message_prints_info(self, capsys: pytest.CaptureFixture[str]) -> None:
        """INFO messages are printed; DEBUG is skipped."""
        renderer = PlainRenderer(Config(app_name="test", style="plain"))
        renderer.open()
        renderer.message(logging.DEBUG, "hidden")
        renderer.message(logging.INFO, "visible")
        out = capsys.readouterr().out
        assert "visible" in out
        assert "hidden" not in out

    @pytest.mark.unit
    def test_table_and_summary(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Table and flush_summary emit plain text."""
        renderer = PlainRenderer(Config(app_name="test", style="plain"))
        renderer.table("Versions", ["from", "to"], [["1.0.0", "1.1.0"]])
        summary = RunSummary(app_name="test")
        summary.set("outcome", "success")
        renderer.flush_summary(summary)
        out = capsys.readouterr().out
        assert "Versions" in out
        assert "1.0.0" in out
        assert "outcome: success" in out

    @pytest.mark.unit
    def test_is_not_live(self) -> None:
        """Plain renderer never reports as live."""
        renderer = PlainRenderer(Config(app_name="test"))
        assert renderer.is_live is False
