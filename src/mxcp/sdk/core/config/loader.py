"""Configuration loader for resolver configuration.

This module provides functions to load and validate resolver configuration
from the new config.yaml file structure.
"""

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import OnePasswordConfigModel, ResolverConfigModel, VaultConfigModel

logger = logging.getLogger(__name__)


def load_resolver_config(config_path: Path | None = None) -> ResolverConfigModel:
    """Load resolver configuration from config.yaml file.

    Args:
        config_path: Optional path to the config.yaml file.
                    If not provided, looks for:
                    1. MXCP_RESOLVER_CONFIG environment variable
                    2. ~/.mxcp/config.yaml
                    3. ./config.yaml

    Returns:
        ResolverConfigModel with resolver settings

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    # Determine config file path
    if config_path is None:
        # Check environment variable first
        env_path = os.environ.get("MXCP_RESOLVER_CONFIG")
        if env_path:
            config_path = Path(env_path)
        else:
            # Try default locations
            candidates = [Path.home() / ".mxcp" / "config.yaml", Path.cwd() / "config.yaml"]
            for candidate in candidates:
                if candidate.exists():
                    config_path = candidate
                    break

            if config_path is None:
                logger.info("No resolver config file found, using empty configuration")
                return ResolverConfigModel()

    if not config_path.exists():
        raise FileNotFoundError(f"Resolver config file not found at {config_path}")

    logger.debug(f"Loading resolver config from: {config_path}")

    # Load the YAML file
    try:
        with open(config_path) as f:
            raw_config = yaml.safe_load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse YAML config file {config_path}: {e}") from e

    if not raw_config:
        logger.info("Empty resolver config file, using empty configuration")
        return ResolverConfigModel()

    # Extract the config section
    config_section = raw_config.get("config", {})

    # Build the ResolverConfig using Pydantic validation
    try:
        resolver_config = _build_resolver_config(config_section)
    except ValidationError as e:
        raise ValueError(f"Invalid resolver config: {e}") from e

    # Apply defaults
    resolver_config = _apply_defaults(resolver_config)

    logger.debug(f"Loaded resolver config: {resolver_config}")
    return resolver_config


def _build_resolver_config(config_section: dict[str, Any]) -> ResolverConfigModel:
    """Build a ResolverConfigModel from a config dictionary.

    Args:
        config_section: The 'config' section from the YAML file

    Returns:
        Validated ResolverConfigModel
    """
    vault_config = None
    onepassword_config = None

    if "vault" in config_section:
        vault_config = VaultConfigModel.model_validate(config_section["vault"])

    if "onepassword" in config_section:
        onepassword_config = OnePasswordConfigModel.model_validate(config_section["onepassword"])

    return ResolverConfigModel(vault=vault_config, onepassword=onepassword_config)


def _apply_defaults(config: ResolverConfigModel) -> ResolverConfigModel:
    """Apply default values to resolver configuration.

    Since Pydantic models are frozen, we create new instances with defaults applied.
    """
    vault_config = config.vault
    onepassword_config = config.onepassword

    # Apply vault defaults
    if vault_config is not None and vault_config.token_env is None:
        vault_config = VaultConfigModel(
            enabled=vault_config.enabled,
            address=vault_config.address,
            token_env="VAULT_TOKEN",
        )

    # Apply onepassword defaults
    if onepassword_config is not None and onepassword_config.token_env is None:
        onepassword_config = OnePasswordConfigModel(
            enabled=onepassword_config.enabled,
            token_env="OP_SERVICE_ACCOUNT_TOKEN",
        )

    return ResolverConfigModel(vault=vault_config, onepassword=onepassword_config)
