import os
import yaml
from pathlib import Path
import json
from jsonschema import validate, ValidationError
from raw.config.types import UserConfig, SiteConfig
import logging

logger = logging.getLogger(__name__)

def _apply_defaults(config: dict) -> dict:
    """Apply default values to the user config"""
    # Create a copy to avoid modifying the input
    config = config.copy()

    # Ensure each profile has at least empty secrets and adapter_configs
    for project in config.get("projects", {}).values():
        for profile in project.get("profiles", {}).values():
            if profile is None:
                profile = {}
            if "secrets" not in profile:
                profile["secrets"] = []
            if "adapter_configs" not in profile:
                profile["adapter_configs"] = {}
    
    return config

def _generate_default_config(site_config: SiteConfig) -> dict:
    """Generate a default user config based on site config"""
    project_name = site_config["project"]
    profile_name = site_config["profile"]
    
    logger.debug(f"Generating default config for project: {project_name}, profile: {profile_name}")
    logger.debug(f"Site config: {site_config}")
    
    config = {
        "raw": "1.0.0",
        "projects": {
            project_name: {
                "default": profile_name,
                "profiles": {
                    profile_name: {
                        "secrets": [],
                        "adapter_configs": {}
                    }
                }
            }
        }
    }
    logger.debug(f"Generated default config: {config}")
    return config

def load_user_config(site_config: SiteConfig) -> UserConfig:
    """Load the user configuration from ~/.raw/config.yml or RAW_CONFIG env var.
    
    If the config file doesn't exist and RAW_CONFIG is not set, generates a default config
    based on the site config.
    
    Args:
        site_config: The site configuration loaded from raw-site.yml
        
    Returns:
        The validated user configuration
    """
    path = Path(os.environ.get("RAW_CONFIG", Path.home() / ".raw" / "config.yml"))
    logger.debug(f"Looking for user config at: {path}")
    
    if not path.exists():
        # If RAW_CONFIG is not set, generate a default config based on site config
        if "RAW_CONFIG" not in os.environ:
            logger.warning(f"RAW user config not found at {path}, generating default config based on site config")
            config = _generate_default_config(site_config)
        else:
            raise FileNotFoundError(f"RAW user config not found at {path}")
    else:
        with open(path) as f:
            config = yaml.safe_load(f)
            logger.debug(f"Loaded user config from file: {config}")
    
    # Apply defaults before validation
    config = _apply_defaults(config)
    logger.debug(f"Config after applying defaults: {config}")
    
    # Load and apply JSON Schema validation
    schema_path = Path(__file__).parent / "schemas" / "raw-config-schema-1.0.0.json"
    with open(schema_path) as schema_file:
        schema = json.load(schema_file)

    try:
        validate(instance=config, schema=schema)
    except ValidationError as e:
        raise ValueError(f"User config validation error: {e.message}")
    return config
