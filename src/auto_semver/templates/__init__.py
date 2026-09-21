# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Templates package public API.

Expose the primary engine class, helper functions, and common type aliases at the
package level so consumers can import from ``auto_semver.templates`` directly.
"""

from auto_semver.templates.engine import (
    TemplateEngine,
    get_template_engine,
    reset_template_engine,
)
from auto_semver.templates.types import (
    TemplateFunction,
    TemplateVariables,
)

__all__ = [
    "TemplateEngine",
    "TemplateFunction",
    "TemplateVariables",
    "get_template_engine",
    "reset_template_engine",
]
