# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: MIT
"""Template system type definitions.

This module contains reusable type definitions for the template system.
The types are designed to work with Jinja2's natural object handling.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

# Type aliases for template system
type TemplateValue = str | int | float | bool | datetime | object | None
type TemplateVariables = dict[str, TemplateValue]
type DateLike = str | datetime
type TemplateFunction = Callable[..., TemplateValue]
type TemplateFilter = Callable[..., TemplateValue]
type FunctionDict = dict[str, TemplateFunction]
type FilterDict = dict[str, TemplateFilter]
