# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Package-manager lockfile sync configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from auto_semver.lock_sync.registry import default_registry, ensure_builtins_registered


class LockSyncConfig(BaseModel):
    """Controls post-bump sync of language package lockfiles.

    A missing host ``uv`` or ``npm`` patches only the project version. There is
    no skip/fail switch for that case. Older configs may still contain
    ``on_missing``; that key is ignored.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(
        default=True,
        description="When true, sync known lockfiles after version-file rewrites",
    )
    ecosystems: list[str] | None = Field(
        default=None,
        description=(
            "Allow-list of ecosystems to sync (registered strategy names). "
            "Omit to auto-detect every known lockfile present at the repo root."
        ),
    )

    @field_validator("ecosystems", mode="before")
    @classmethod
    def validate_ecosystems(cls, value: object) -> object:
        """Reject unknown ecosystem names early with a clear message."""
        if value is None:
            return value
        if not isinstance(value, list):
            raise ValueError("ecosystems must be a list of ecosystem names")
        ensure_builtins_registered()
        known = default_registry.names()
        unknown = [item for item in value if item not in known]
        if unknown:
            raise ValueError(f"Unknown lock_sync ecosystems: {unknown}. Supported: {sorted(known)}")
        return value
