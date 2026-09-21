# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Configuration models for changelog generation."""

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from jinja2 import Template, TemplateSyntaxError
from pydantic import BaseModel, Field, field_serializer, field_validator

from auto_semver.config._models.commit_group import CommitGroups
from auto_semver.config.constants import DEFAULT_CHANGELOG


@dataclass
class ChangelogTemplateVars:
    """Template variables for changelog rendering.

    This dataclass defines the exact structure of variables that can be passed
    to changelog templates, providing type safety and clear documentation of available
    template variables.

    Attributes:
        version (str): The semantic version being released (e.g., "1.2.3").
        date (str): Formatted date string for the release date.
        messages (list[str]): List of raw commit messages since last version.
        commit_groups (CommitGroups | None): Pre-processed commit groups (optional).
    """

    version: str
    date: str
    messages: list[str]
    commit_groups: CommitGroups | None = None


class ChangelogConfig(BaseModel):
    """
    Defines how the changelog should be generated and formatted.

    Includes file path, overwrite behavior, and Jinja2 templates for
    formatting the changelog entries. The templates support variables such
    as `version`, `date`, and `messages`.

    Attributes:
        file (Path): The relative path to the changelog file to update.
        truncate (bool): If True, overwrites the changelog file instead of prepending.
        template (str): A Jinja2 template for formatting the changelog entry.
        header (str | None): Optional header text placed above the changelog entry.
        footer (str | None): Optional footer text placed below the changelog entry.

    """

    file: Path = Field(
        default_factory=lambda: Path(DEFAULT_CHANGELOG), description="Path to the changelog file."
    )

    truncate: bool = Field(
        default=False, description="If true, overwrite the changelog instead of prepending."
    )

    template: str = Field(
        default=dedent(
            """
        ## [{{version}}] - {{date}}
        {% for msg in messages -%}
        - {{ msg }}
        {%- endfor %}
        """
        ),
        description="Jinja template for changelog entries.",
    )

    header: str | None = Field(default=None, description="Optional header text for the changelog.")
    footer: str | None = Field(default=None, description="Optional footer text for the changelog.")

    @field_serializer("file")
    def serialize_path(self, value: Path) -> str:
        """Serialize Path objects to strings."""
        return str(value)

    @field_validator("template")
    @classmethod
    def validate_template(cls, value: str) -> str:
        """
        Validate that the provided string is a valid Jinja2 template.

        Args:
            value (str): The template string to validate.

        Returns:
            str: The original value if it's a valid Jinja2 template.

        Raises:
            ValueError: If the template contains syntax errors.

        """
        try:
            # Basic syntax validation using Jinja2 Template
            Template(value)
            return value
        except TemplateSyntaxError as err:
            raise ValueError(f"Invalid Jinja2 template: {err}") from err
