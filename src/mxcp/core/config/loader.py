"""
Configuration loader for resolver configuration.

This module provides functions to load and validate resolver configuration
from the new config.yaml file structure.
"""

import os
import yaml
import json
import logging
from pathlib import Path
from typing import Optional
from jsonschema import validate, ValidationError

from .types import ResolverConfig

logger = logging.getLogger(__name__)


def load_resolver_config(config_path: Optional[Path] = None) -> ResolverConfig:
    """
    Load resolver configuration from config.yaml file.
    
    Args:
        config_path: Optional path to the config.yaml file.
                    If not provided, looks for:
                    1. MXCP_RESOLVER_CONFIG environment variable
                    2. ~/.mxcp/config.yaml
                    3. ./config.yaml
                    
    Returns:
        ResolverConfig with resolver settings
        
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
            candidates = [
                Path.home() / ".mxcp" / "config.yaml",
                Path.cwd() / "config.yaml"
            ]
            for candidate in candidates:
                if candidate.exists():
                    config_path = candidate
                    break
            
            if config_path is None:
                logger.info("No resolver config file found, using empty configuration")
                return ResolverConfig(vault=None, onepassword=None)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Resolver config file not found at {config_path}")
    
    logger.debug(f"Loading resolver config from: {config_path}")
    
    # Load the YAML file
    try:
        with open(config_path, 'r') as f:
            raw_config = yaml.safe_load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse YAML config file {config_path}: {e}")
    
    if not raw_config:
        logger.info("Empty resolver config file, using empty configuration")
        return ResolverConfig(vault=None, onepassword=None)
    
    # Validate against schema
    schema_path = Path(__file__).parent / "resolver-config-schema.json"
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        validate(instance=raw_config, schema=schema)
    except ValidationError as e:
        raise ValueError(f"Invalid resolver config: {e.message}")
    except Exception as e:
        raise ValueError(f"Failed to validate resolver config: {e}")
    
    # Extract the config section
    config_section = raw_config.get("config", {})
    
    # Build the ResolverConfig
    resolver_config = ResolverConfig(
        vault=config_section.get("vault"),
        onepassword=config_section.get("onepassword")
    )
    
    # Apply defaults
    resolver_config = _apply_defaults(resolver_config)
    
    logger.debug(f"Loaded resolver config: {resolver_config}")
    return resolver_config


def _apply_defaults(config: ResolverConfig) -> ResolverConfig:
    """Apply default values to resolver configuration."""
    # Create a copy to avoid modifying the input
    result = config.copy()
    
    # Apply vault defaults
    vault_config = result.get("vault")
    if vault_config is not None:
        if "token_env" not in vault_config:
            vault_config["token_env"] = "VAULT_TOKEN"
    
    # Apply onepassword defaults
    op_config = result.get("onepassword")
    if op_config is not None:
        if "token_env" not in op_config:
            op_config["token_env"] = "OP_SERVICE_ACCOUNT_TOKEN"
    
    return result 