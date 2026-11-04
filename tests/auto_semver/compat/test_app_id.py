"""Tests for the deprecated --app-id setup flag."""

import logging

import pytest

from auto_semver.cli.main import _build_parser
from auto_semver.compat.app_id import resolve_client_id

_NOTICE = "auto_semver.compat._notice"


@pytest.mark.unit
def test_setup_parser_keeps_app_id_flag() -> None:
    """The setup command still accepts --app-id."""
    args = _build_parser().parse_args(["setup", "--app-id", "Iv1.old"])
    assert args.app_id == "Iv1.old"
    assert args.client_id is None


@pytest.mark.unit
def test_app_id_resolves_and_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    """--app-id still supplies the client id and warns once."""
    with caplog.at_level(logging.WARNING, logger=_NOTICE):
        first = resolve_client_id(client_id=None, app_id="Iv1.old")
        second = resolve_client_id(client_id=None, app_id="Iv1.old")

    assert first == "Iv1.old"
    assert second == "Iv1.old"
    warnings = [record for record in caplog.records if "--app-id is deprecated" in record.message]
    assert len(warnings) == 1
    assert "Removed in 2.0" in warnings[0].message


@pytest.mark.unit
def test_client_id_wins_without_warning_when_app_id_absent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """--client-id alone is silent."""
    with caplog.at_level(logging.WARNING, logger=_NOTICE):
        resolved = resolve_client_id(client_id="Iv1.new", app_id=None)

    assert resolved == "Iv1.new"
    assert caplog.records == []


@pytest.mark.unit
def test_client_id_preferred_when_both_are_set(caplog: pytest.LogCaptureFixture) -> None:
    """A passed --app-id warns even when --client-id is the value that is used."""
    with caplog.at_level(logging.WARNING, logger=_NOTICE):
        resolved = resolve_client_id(client_id="Iv1.new", app_id="Iv1.old")

    assert resolved == "Iv1.new"
    assert any("--app-id is deprecated" in record.message for record in caplog.records)
