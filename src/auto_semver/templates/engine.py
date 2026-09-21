# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""
Centralized Jinja2 template engine for auto-semver.

This module provides a pluggable template engine that allows other modules
to register their own domain-specific functions and variables.

Built-in functions available in all templates:
    - format_date
    - format_commit
    - title_case
    - list_join
    - truncate_text
    - pluralize

Note: Do not re-register these built-in functions in your PRBuilder or extensions.

Example usage:

    from auto_semver.templates.engine import get_template_engine

    # Get the global engine instance
    engine = get_template_engine()

    # Register domain-specific functions
    def group_commits(messages, groups):
        # Domain logic here
        return grouped_data

    engine.register_function('group_commits', group_commits)

    # Use in templates
    template = "Groups: {% for group in group_commits(messages, config) %}..."
    result = engine.render_template(template, {'messages': [...], 'config': [...]})
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from jinja2 import DictLoader, Template, TemplateSyntaxError, nodes
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

from auto_semver.templates.utils import get_pr_template_functions

if TYPE_CHECKING:
    from auto_semver.templates.types import (
        FunctionDict,
        TemplateFunction,
        TemplateValue,
        TemplateVariables,
    )

# Use a module-level logger for template engine warnings
logger = logging.getLogger(__name__)


class TemplateEngine:
    """
    Centralized template engine with pluggable custom functions and filters.

    This engine provides:
    - Core Jinja2 functionality
    - Built-in utility functions and filters
    - Plugin system for domain-specific extensions
    - Template validation and analysis
    """

    def __init__(self) -> None:
        """Initialize the template engine with core functions and filters."""
        # Sandboxed environment — consumer-controlled templates must not escape
        self.env = SandboxedEnvironment(loader=DictLoader({}))

        # Storage for registered functions and filters
        self._custom_functions: FunctionDict = {}

        # Register core built-in functions and filters
        self._register_builtin_functions()

        # Apply all registered functions and filters to the environment
        self._update_environment()

    def _register_builtin_functions(self) -> None:
        """Register core built-in functions."""
        self._custom_functions.update(
            {
                "format_date": self._format_date,
                "format_commit": self._format_commit,
                "title_case": self._title_case,
                "list_join": self._list_join,
                "truncate_text": self._truncate_text,
                "pluralize": self._pluralize,
            }
        )
        # PR/changelog helpers live in templates.utils — single registration site
        self._custom_functions.update(get_pr_template_functions())

    def _update_environment(self) -> None:
        """Update the Jinja2 environment with all registered functions and variables."""
        self.env.globals.update(self._custom_functions)
        self.env.globals.update(getattr(self, "_custom_variables", {}))

    def register_variable(self, name: str, value: TemplateValue) -> None:
        """Register a custom variable for use in templates."""
        if not hasattr(self, "_custom_variables"):
            self._custom_variables = {}
        if name in self.env.globals:
            logger.warning(
                f"TemplateEngine: '{name}' is already registered as a "
                f"function or variable. Skipping registration."
            )
            return
        self._custom_variables[name] = value
        self.env.globals[name] = value

    def register_variables(self, variables: TemplateVariables) -> None:
        """Register multiple variables for use in templates."""
        if not hasattr(self, "_custom_variables"):
            self._custom_variables = {}
        for name, value in variables.items():
            if name in self.env.globals:
                logger.warning(
                    f"TemplateEngine: '{name}' is already registered as a "
                    f"function or variable. Skipping registration."
                )
                continue
            self._custom_variables[name] = value
            self.env.globals[name] = value

    def register_function(self, name: str, func: TemplateFunction) -> None:
        """
        Register a custom function for use in templates.

        Args:
            name: Name to use in templates (e.g., 'group_commits')
            func: Function to register
        """
        if name in self.env.globals:
            logger.warning(
                f"TemplateEngine: '{name}' is already registered as a "
                f"function or variable. Skipping registration."
            )
            return
        self._custom_functions[name] = func
        self.env.globals[name] = func

    def register_functions(self, functions: FunctionDict) -> None:
        """
        Register multiple custom functions at once.

        Args:
            functions: Dictionary mapping function names to functions
        """
        for name, func in functions.items():
            self.register_function(name, func)

    def unregister_function(self, name: str) -> bool:
        """
        Unregister a custom function.

        Args:
            name: Name of the function to remove

        Returns:
            True if function was removed, False if it didn't exist
        """
        if name in self._custom_functions:
            del self._custom_functions[name]
            if name in self.env.globals:
                del self.env.globals[name]
            return True
        return False

    def list_functions(self) -> list[str]:
        """Get list of all registered function names."""
        return list(self._custom_functions.keys())

    def _store_template(self, name: str, template_str: str) -> None:
        """
        Store a template in the loader for caching.

        Args:
            name: Template name for retrieval
            template_str: The Jinja2 template string
        """
        loader = self.env.loader
        if not isinstance(loader, DictLoader):
            raise RuntimeError("Loader must be DictLoader for template caching")

        # Fast path: template already exists, do nothing
        if name in loader.mapping:
            return

        # Create new loader with updated mapping
        updated_mapping = dict(loader.mapping)
        updated_mapping[name] = template_str
        self.env.loader = DictLoader(updated_mapping)

    def get_template(self, name: str) -> Template:
        """
        Get a cached template by name.

        Args:
            name: Template name

        Returns:
            Compiled Jinja2 template

        Raises:
            TemplateNotFound: If template doesn't exist
        """
        return self.env.get_template(name)

    def has_template(self, name: str) -> bool:
        """
        Check if a template exists by name.

        Args:
            name: Template name

        Returns:
            True if template exists, False otherwise
        """
        loader = self.env.loader
        if not isinstance(loader, DictLoader):
            return False
        return name in loader.mapping

    def get_template_names(self) -> list[str]:
        """
        Get list of all cached template names.

        Returns:
            List of template names
        """
        loader = self.env.loader
        if not isinstance(loader, DictLoader):
            return []
        return list(loader.mapping.keys())

    def render_by_name(self, name: str, variables: TemplateVariables) -> str:
        """
        Render a previously cached template by name.

        Args:
            name: Template name
            variables: Dictionary of variables to use in rendering

        Returns:
            Rendered template string

        Raises:
            TemplateNotFound: If template doesn't exist
            Exception: If rendering fails
        """
        template = self.get_template(name)
        return template.render(**variables)

    def register_template(self, name: str, template_str: str) -> None:
        """
        Register a template with a given name for later use.

        Args:
            name: Template name for retrieval
            template_str: The Jinja2 template string

        Raises:
            TemplateSyntaxError: If template has syntax errors
        """
        # Validate the template first
        self.validate_template(template_str)
        # Store it if validation passes
        self._store_template(name, template_str)

    def _format_date(self, date_value: str | datetime, format_string: str = "%Y-%m-%d") -> str:
        """
        Format a date value using the specified format string.

        Args:
            date_value: The date to format (can be string, datetime, or date)
            format_string: The format pattern to use

        Returns:
            Formatted date string
        """
        # Handle string dates with ISO format parsing
        if isinstance(date_value, str):
            try:
                # Try parsing ISO format first
                parsed_date = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
                return parsed_date.strftime(format_string)
            except ValueError:
                # Return the string as-is if parsing fails
                return date_value

        # Handle datetime/date objects
        if hasattr(date_value, "strftime"):
            return str(date_value.strftime(format_string))

        # Fallback for any other type
        return str(date_value)

    def _format_commit(self, commit_msg: str, max_length: int = 72) -> str:
        """Format commit message with proper truncation (alias for truncate_text)."""
        return self._truncate_text(commit_msg, max_length, "...")

    def _title_case(self, text: str) -> str:
        """Convert text to title case."""
        return text.title()

    def _list_join(self, items: list[str | int | float], separator: str = ", ") -> str:
        """Join list items with separator."""
        return separator.join(str(item) for item in items)

    def _truncate_text(self, text: str, max_length: int = 50, suffix: str = "...") -> str:
        """Truncate text to a maximum length with optional suffix."""
        if len(text) <= max_length:
            return text
        return f"{text[: max_length - len(suffix)]}{suffix}"

    def _pluralize(self, count: int, singular: str, plural: str | None = None) -> str:
        """Return singular or plural form based on count."""
        if count == 1:
            return singular
        return plural if plural is not None else f"{singular}s"

    def render_template(
        self, template_str: str, variables: TemplateVariables, name: str | None = None
    ) -> str:
        """
        Render a template string with the given variables.

        Args:
            template_str: The Jinja2 template string
            variables: Dictionary of variables to use in rendering
            name: Optional template name for caching/retrieval (defaults to hash-based name)

        Returns:
            Rendered template string

        Raises:
            TemplateSyntaxError: If template has syntax errors
            Exception: If rendering fails
        """
        try:
            # Use provided name or generate a hash-based one
            template_name = name or f"template_{hash(template_str) & 0x7FFFFFFF}"

            # Store the template for easy retrieval later
            self._store_template(template_name, template_str)

            template = self.env.get_template(template_name)
            return template.render(**variables)
        except TemplateSyntaxError as e:
            raise TemplateSyntaxError(f"Template syntax error: {e}", lineno=1) from e
        except SecurityError:
            raise
        except Exception as e:
            raise Exception(f"Template rendering failed: {e}") from e

    def validate_template(self, template_str: str) -> None:
        """
        Validate that a template string is syntactically correct.

        Args:
            template_str: The template string to validate

        Raises:
            TemplateSyntaxError: If template has syntax errors
        """
        # Just try to parse the template - let the error bubble up
        self.env.from_string(template_str)

    def extract_template_variables(self, template_str: str) -> list[str]:
        """
        Extract all variable names from a template string.

        This parses the template and finds all {{ variable }} references.

        Args:
            template_str: The template string to analyze

        Returns:
            List of unique variable names found in the template

        Raises:
            TemplateSyntaxError: If template has syntax errors
        """
        variables = set()

        # Parse the template to get the AST - this will raise TemplateSyntaxError if invalid
        ast = self.env.parse(template_str)

        # Walk the AST to find variable references
        for node in ast.find_all(nodes.Name):
            variables.add(node.name)

        return sorted(list(variables))

    def match_template_pattern(
        self,
        template_str: str,
        text: str,
    ) -> dict[str, str] | None:
        """
        Match text against a template pattern and extract variable values.

        This method is not implemented as it requires reverse-engineering templates.
        For proper template matching, use dedicated parsing logic or structured data.

        Args:
            template_str: The template pattern to match against
            text: The text to extract variables from

        Returns:
            None - this method is not supported

        Raises:
            NotImplementedError: This functionality is not supported
        """
        raise NotImplementedError(
            "Template pattern matching is not supported. "
            "Use structured data or dedicated parsing instead of reverse-engineering templates."
        )

    def get_static_prefix(self, template_str: str) -> str | None:
        """
        Get the static prefix of a template (the part before the first variable).

        This method uses Jinja2's AST parsing to find the static text that appears
        before any template variables or expressions.

        Args:
            template_str: The template string to analyze

        Returns:
            str | None: The static prefix if found, None if template starts with a variable

        Raises:
            TemplateSyntaxError: If template has syntax errors
        """
        try:
            # Parse the template to get the AST
            ast = self.env.parse(template_str)

            # Check if the first node is a simple text node
            if ast.body and len(ast.body) > 0:
                node = ast.body[0]

                # Handle Output node which wraps content (Jinja2 AST structure)
                if isinstance(node, nodes.Output):
                    if node.nodes:
                        node = node.nodes[0]

                # If the node is TemplateData (static text), return it
                if hasattr(node, "data"):
                    static_text = node.data
                    return static_text if static_text and static_text.strip() else None

            # If no static prefix found or template starts with a variable
            return None

        except Exception:
            # If AST parsing fails for any reason, return None
            return None

    def compare_templates(self, template1_str: str, template2_str: str) -> bool:
        """
        Compare two template strings for structural equality.

        This uses Jinja2's AST parsing to compare templates, so templates
        with the same structure but different whitespace will be considered equal.

        Args:
            template1_str: First template string to compare
            template2_str: Second template string to compare

        Returns:
            True if templates have the same structure, False otherwise

        Raises:
            TemplateSyntaxError: If either template has syntax errors
        """
        ast1 = self.env.parse(template1_str)
        ast2 = self.env.parse(template2_str)
        return ast1 == ast2

    def get_template_with_source(
        self, template_str: str, name: str = "template"
    ) -> tuple[Template, str]:
        """
        Create a template that retains its source for later retrieval.

        This uses a DictLoader to store the template so we can get the source back later.

        Args:
            template_str: The template string
            name: Name to give the template (defaults to "template")

        Returns:
            Tuple of (template_object, template_name) where template_name can be used
            to retrieve the original source later

        Raises:
            TemplateSyntaxError: If template has syntax errors
        """
        # Create a temporary sandboxed environment with DictLoader
        loader = DictLoader({name: template_str})
        temp_env = SandboxedEnvironment(loader=loader)

        # Copy our custom functions to the temporary environment
        temp_env.globals.update(self.env.globals)
        temp_env.filters.update(self.env.filters)

        template = temp_env.get_template(name)
        return template, name

    def get_template_source(self, template: Template) -> str:
        """
        Get the original source of a template.

        Args:
            template: Template object created with get_template_with_source

        Returns:
            The original template source string

        Raises:
            ValueError: If template was not created with a loader or has no name
        """
        if not template.environment.loader:
            raise ValueError("Template was not created with a loader - cannot retrieve source")
        if template.name is None:
            raise ValueError("Template has no name - cannot retrieve source")
        source, _, _ = template.environment.loader.get_source(template.environment, template.name)
        return str(source)

    def has_required_variables(
        self,
        template_str: str,
        variables: TemplateVariables,
    ) -> bool:
        """
        Check if all required variables for a template are provided.

        Args:
            template_str: The template string to check
            variables: Dictionary of available variables

        Returns:
            True if all required variables are present, False otherwise
        """
        required_vars = set(self.extract_template_variables(template_str))
        provided_vars = set(variables.keys())

        return required_vars.issubset(provided_vars)


# Module-level template engine storage
class _TemplateEngineHolder:
    """Private holder class to avoid global statement."""

    instance: TemplateEngine | None = None


_holder = _TemplateEngineHolder()


def get_template_engine() -> TemplateEngine:
    """Get or create the global template engine instance.

    This function creates a singleton template engine with default configuration.
    Subsequent calls will return the same instance.

    Returns:
        Configured TemplateEngine instance
    """
    if _holder.instance is None:
        _holder.instance = TemplateEngine()

    return _holder.instance


def reset_template_engine() -> None:
    """Reset the global template engine instance.

    This forces the next call to get_template_engine() to create a new instance.
    Useful for testing or when configuration needs to change.
    """
    _holder.instance = None
