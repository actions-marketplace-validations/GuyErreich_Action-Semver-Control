"""Tests for stateless GitHub App installation token validation helpers."""

from __future__ import annotations

import pytest
from validate_stateless_token import assert_token_shape


def _synthetic_stateless_token(*, length: int = 520) -> str:
    """Build a realistic-length ghs_ JWT-shaped string (not a real secret)."""
    prefix = "ghs_12345_"
    header = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
    payload = "eyJpc3MiOiIxMjM0NSJ9"
    signature = "A" * max(1, length - len(prefix) - len(header) - len(payload) - 2)
    return f"{prefix}{header}.{payload}.{signature}"


class TestAssertTokenShape:
    """Shape assertions for stateless vs stateful installation tokens."""

    def test_stateless_token_accepts_jwt_shape(self) -> None:
        token = _synthetic_stateless_token()
        assert len(token) >= 400
        assert_token_shape(token, "enabled")

    def test_stateless_token_rejects_short_opaque(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            assert_token_shape("ghs_" + "a" * 36, "enabled")

    def test_stateless_token_rejects_wrong_dot_count(self) -> None:
        with pytest.raises(ValueError, match="2 dots"):
            assert_token_shape("ghs_" + "a" * 400, "enabled")

    def test_stateful_token_accepts_opaque(self) -> None:
        assert_token_shape("ghs_" + "A" * 36, "disabled")

    def test_stateful_token_rejects_jwt(self) -> None:
        token = _synthetic_stateless_token()
        with pytest.raises(ValueError, match="must not contain dots"):
            assert_token_shape(token, "disabled")

    def test_rejects_non_ghs_prefix(self) -> None:
        with pytest.raises(ValueError, match="ghs_ prefix"):
            assert_token_shape("ghp_" + "a" * 36, "enabled")
