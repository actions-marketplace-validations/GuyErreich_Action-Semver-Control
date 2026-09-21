# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Abstract PRBuilder for provider-agnostic pull request content generation.

Defines the interface for building PR title, body, and labels from templates and data.
Provider-specific builders should inherit from this class and implement the build methods.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from auto_semver.templates.engine import get_template_engine

if TYPE_CHECKING:
    from auto_semver.config import CommitGroups

logger = logging.getLogger(__name__)


# Base template variables for PR builders
@dataclass
class BasePRTemplateVariables:
    """Base template variables for PR builders."""

    version: str
    previous_version: str
    commit_groups: CommitGroups
    breaking_changes: list[str]
    author: str
    repository: str
    date: str
    branch: str
    base_branch: str
    labels: list[str] | None = None


class PRBuilder[T: BasePRTemplateVariables](ABC):
    """Abstract base class for building pull request content (title, body, labels) from templates and data.

    Instantiate with data, and title, body, labels properties are automatically rendered and ready to use.
    """

    def __init__(self, data: T) -> None:
        """Initialize the PR builder with data and auto-render all content.

        Args:
            data: Template variables data for rendering PR content
        """
        self._engine = get_template_engine()
        self._data = data

        # Template functions are registered once on the engine (templates.utils).
        self._register_template_variables()

        # Auto-render and store as properties
        self.title: str = self._build_title()
        self.body: str = self._build_body()
        self.labels: list[str] = self._build_labels()
        logger.info(
            "Rendered PR title=%r labels=%d",
            self.title,
            len(self.labels),
        )

    @abstractmethod
    def _register_template_variables(self) -> None:
        """Register template variables specific to this PR builder type.

        Should be called once during __init__ to register variables with the template engine.
        """
        pass

    @abstractmethod
    def _build_title(self) -> str:
        """Build the PR title from template and self._data."""
        pass

    @abstractmethod
    def _build_body(self) -> str:
        """Build the PR body from template and self._data."""
        pass

    @abstractmethod
    def _build_labels(self) -> list[str]:
        """Build the PR labels from template and self._data."""
        pass
