# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Unit tests for runview.bridge and record factory."""

from __future__ import annotations

import logging
from collections.abc import Generator

import pytest

from runview.bridge import ReporterHandler
from runview.config import Config
from runview.record import record_factory
from runview.reporter import Reporter
from runview.summary import RunSummary
from tests.fixtures.fake_renderer import FakeRenderer


class TestRecordFactory:
    """Tests for the custom log record factory."""

    @pytest.fixture
    def reset_logging_factory(self) -> Generator[None, None, None]:
        """Reset the logging record factory after each test."""
        original_factory = logging.getLogRecordFactory()
        yield
        logging.setLogRecordFactory(original_factory)

    @pytest.mark.unit
    def test_record_factory_adds_qualname(self, reset_logging_factory: None) -> None:
        """record_factory adds qualname and full_name attributes."""
        record_args = [
            "test_logger",
            logging.INFO,
            "file.py",
            10,
            "Test message",
            (),
            None,
        ]
        record = record_factory(*record_args)
        assert hasattr(record, "qualname")
        assert hasattr(record, "full_name")
        assert record.full_name == f"[{record.name}.{record.module}][{record.funcName}]"


class TestReporterHandler:
    """Tests for bridge routing into the reporter."""

    @pytest.mark.unit
    def test_emit_forwards_structured_fields(self) -> None:
        """ReporterHandler forwards level, text, and qualname."""
        fake = FakeRenderer()
        config = Config(app_name="test")
        reporter = Reporter(config, fake, RunSummary(app_name="test"))
        handler = ReporterHandler(reporter)
        handler.setLevel(logging.INFO)

        record = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname="x.py",
            lineno=1,
            msg="hello view",
            args=(),
            exc_info=None,
        )
        record.__dict__["qualname"] = "SampleClass.sample_method"
        handler.emit(record)
        assert fake.messages
        level, text, qualname, _created = fake.messages[0]
        assert level == logging.INFO
        assert text == "hello view"
        assert qualname == "SampleClass.sample_method"

    @pytest.mark.unit
    def test_emit_falls_back_to_func_name(self) -> None:
        """Without qualname attribute, handler uses record.funcName."""
        fake = FakeRenderer()
        config = Config(app_name="test")
        reporter = Reporter(config, fake, RunSummary(app_name="test"))
        handler = ReporterHandler(reporter)
        record = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname="x.py",
            lineno=1,
            msg="fallback",
            args=(),
            exc_info=None,
            func="my_func",
        )
        handler.emit(record)
        assert fake.messages[0][2] == "my_func"
