# Copyright (c) 2025-2026 Guy Erreich
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Configuration management for auto-semver-bump.

This module provides a class for loading and validating configuration
settings from a YAML file. It ensures that required keys are present
and provides methods to access various configuration options.

Typical usage::
    config = Config()
    version_files = config.get_files_to_update()
    start_version = config.get_start_version()
    suffix = config.get_suffix("main")
    label = config.get_pr_labels()
    changelog_file = config.get_changelog_file()
    should_truncate_changelog = config.should_truncate_changelog()
    changelog_template = config.get_changelog_template()
    changelog_header = config.get_changelog_header()
    changelog_footer = config.get_changelog_footer()
"""

import logging
import os
from pathlib import Path
from typing import cast

import yaml
from pydantic import ValidationError

from auto_semver.config._models.changelog import ChangelogConfig
from auto_semver.config._models.commit_group import CommitGroupConfig
from auto_semver.config._models.config import ConfigData
from auto_semver.config._models.promotion import PromotionRule
from auto_semver.config._models.pull_request import PullRequestConfig
from auto_semver.config.constants import CONFIG_FILE
from auto_semver.core.semver import Version

# Union type for all possible ConfigData attribute return types
type ConfigValue = (
    Version
    | dict[str, str]
    | list[PromotionRule]
    | list[str]
    | list[CommitGroupConfig]
    | PullRequestConfig
    | ChangelogConfig
)

logger = logging.getLogger(__package__)


class Config:
    """
    Configuration management class for auto-semver-bump.

    This class loads configuration settings from a YAML file and provides
    methods to access various configuration options. It ensures that
    required keys are present and provides default values for optional
    settings.
    """

    def __init__(self, path: Path = Path(CONFIG_FILE)) -> None:
        """
        Initialize the configuration manager.

        Args:
            path (Path): Path to the configuration file. Defaults to 'auto_semver_config.yml'.

        Raises:
            RuntimeError: If the configuration file is invalid or missing required keys.
            KeyError: If a required key is missing in the configuration file.

        """
        self.path = path
        self.data = self._load_and_parse()

    def _load_and_parse(self) -> ConfigData:
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"Configuration file '{self.path}' not found.")

        try:
            with open(self.path, encoding="utf-8") as f:
                raw_config = yaml.safe_load(f) or {}
            return ConfigData(**raw_config)
        except yaml.YAMLError as err:
            logger.error(f"Error parsing YAML configuration: {err}")
            raise
        except ValidationError as e:
            logger.error("Configuration validation failed.")
            for error in e.errors():
                loc = " -> ".join(str(i) for i in error["loc"])
                msg = error["msg"]
                typ = error["type"]
                logger.error(f"Missing or invalid config field: {loc} | {msg} [{typ}]")
            raise

    def __getattr__(self, item: str) -> ConfigValue:
        """Use for returning the named property in data."""
        return cast("ConfigValue", getattr(self.data, item))

    @staticmethod
    def generate_config_file(*, config_data: ConfigData, path: Path = Path(CONFIG_FILE)) -> None:
        """
        Generate a YAML configuration file from a ConfigData object.

        Args:
            config_data (ConfigData): The configuration data to write to file.
            path (Path): Path where the configuration file should be written.
                Defaults to 'auto_semver_config.yml'.

        Raises:
            OSError: If there is an error writing the configuration file.
            yaml.YAMLError: If there is an error dumping the configuration to YAML.

        """
        # Convert ConfigData to dict, excluding None values
        # The field serializers will handle complex object conversion
        config_dict = config_data.model_dump(exclude_none=True)

        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump(config_dict, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Configuration file generated at '{path}'")
        except (OSError, yaml.YAMLError) as err:
            logger.error(f"Error generating configuration file: {err}")
            raise
