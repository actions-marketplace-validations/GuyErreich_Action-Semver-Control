# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
GitHub-specific PRBuilder implementation.

Handles GitHub pull request generation with specific templates and configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from auto_semver.config.constants import PR_HIDDEN_MARKER
from auto_semver.core.pr.builder import BasePRTemplateVariables, PRBuilder

if TYPE_CHECKING:
    from auto_semver.config import CommitGroup


@dataclass
class GitHubPRTemplateVariables(BasePRTemplateVariables):
    """GitHub-specific template variables for PR builder."""

    groups: list[CommitGroup] | None = None
    feature_count: int = 0
    fix_count: int = 0


class GitHubPRBuilder(PRBuilder[GitHubPRTemplateVariables]):
    """GitHub-specific implementation of PRBuilder.

    Instantiate with data and templates, then access title, body, labels properties directly.
    """

    def __init__(
        self,
        data: GitHubPRTemplateVariables,
        title_template: str = "Release {{ version }}",
        body_template: str = "Release notes for {{ version }}",
        labels_template: str = "",
    ) -> None:
        """Initialize GitHub PR builder with data, templates, and auto-render content.

        Args:
            data: GitHub PR template variables
            title_template: Jinja2 template for PR title
            body_template: Jinja2 template for PR body
            labels_template: Jinja2 template for PR labels (comma-separated)
        """
        # TODO: make this part of the base class if other builders need it
        self.title_template = title_template
        self.body_template = body_template
        self.labels_template = labels_template
        super().__init__(data)

    def _register_template_variables(self) -> None:
        """Register GitHub-specific template variables with actual data.

        Registers all fields from GitHubPRTemplateVariables using the actual instance data.
        This is called once during __init__ to make variables available for all template renders.
        """
        # Register the actual data values as template variables
        for var_name, value in self._data.__dict__.items():
            self._engine.register_variable(var_name, value)

    def _build_title(self) -> str:
        """Build the PR title using the title template and instance data."""
        result: str = self._engine.render_template(self.title_template, self._data.__dict__)
        return result

    def _build_body(self) -> str:
        """Build the PR body using the body template and instance data.

        Automatically prepends the hidden marker for finalization detection.
        """
        rendered: str = self._engine.render_template(self.body_template, self._data.__dict__)
        return f"{PR_HIDDEN_MARKER}\n{rendered}"

    def _build_labels(self) -> list[str]:
        """Build the PR labels using the labels template and instance data."""
        if not self.labels_template:
            return []
        labels_str: str = self._engine.render_template(self.labels_template, self._data.__dict__)
        return [label.strip() for label in labels_str.split(",") if label.strip()]
