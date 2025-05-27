import os
import yaml
from pathlib import Path
import json
from jsonschema import validate, ValidationError
from mxcp.config.types import UserConfig, SiteConfig
import logging
from typing import Dict, Any, Optional
import re

logger = logging.getLogger(__name__)

# Regular expression to match ${ENV_VAR} patterns
ENV_VAR_PATTERN = re.compile(r'\${([A-Za-z0-9_]+)}')

def _interpolate_env_vars(value: Any) -> Any:
    """Interpolate environment variables in string values.
    
    Args:
        value: The value to process. Can be a string, dict, list, or other type.
        
    Returns:
        The processed value with environment variables interpolated.
        
    Raises:
        ValueError: If an environment variable is referenced but not set.
    """
    if isinstance(value, str):
        # Find all environment variable references
        matches = ENV_VAR_PATTERN.findall(value)
        if not matches:
            return value
            
        # Replace each reference with the environment variable value
        result = value
        for env_var in matches:
            if env_var not in os.environ:
                raise ValueError(f"Environment variable {env_var} is not set")
            result = result.replace(f"${{{env_var}}}", os.environ[env_var])
        return result
    elif isinstance(value, dict):
        return {k: _interpolate_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_interpolate_env_vars(item) for item in value]
    else:
        return value

def _apply_defaults(config: dict) -> dict:
    """Apply default values to the user config"""
    # Create a copy to avoid modifying the input
    config = config.copy()

    # Ensure each profile has at least empty secrets and plugin config
    for project in config.get("projects", {}).values():
        for profile in project.get("profiles", {}).values():
            if profile is None:
                profile = {}
            if "secrets" not in profile:
                profile["secrets"] = []
            if "plugin" not in profile:
                profile["plugin"] = {"config": {}}
            elif "config" not in profile["plugin"]:
                profile["plugin"]["config"] = {}
    
    return config

def _generate_default_config(site_config: SiteConfig) -> dict:
    """Generate a default user config based on site config"""
    project_name = site_config["project"]
    profile_name = site_config["profile"]
    
    logger.debug(f"Generating default config for project: {project_name}, profile: {profile_name}")
    logger.debug(f"Site config: {site_config}")
    
    config = {
        "mxcp": "1.0.0",
        "projects": {
            project_name: {
                "profiles": {
                    profile_name: {
                        "secrets": [],
                        "plugin": {
                            "config": {}
                        }
                    }
                }
            }
        }
    }
    logger.debug(f"Generated default config: {config}")
    return config

def load_user_config(site_config: SiteConfig, generate_default: bool = True) -> UserConfig:
    """Load the user configuration from ~/.mxcp/config.yml or MXCP_CONFIG env var.
    
    If the config file doesn't exist and MXCP_CONFIG is not set, generates a default config
    based on the site config if generate_default is True.
    
    The configuration supports environment variable interpolation using ${ENV_VAR} syntax.
    For example:
        database: ${DB_NAME}
        password: ${DB_PASSWORD}
    
    Args:
        site_config: The site configuration loaded from mxcp-site.yml
        generate_default: Whether to generate a default config if the file doesn't exist
        
    Returns:
        The validated user configuration
        
    Raises:
        FileNotFoundError: If the config file doesn't exist and generate_default is False
        ValueError: If an environment variable is referenced but not set
    """
    path = Path(os.environ.get("MXCP_CONFIG", Path.home() / ".mxcp" / "config.yml"))
    logger.debug(f"Looking for user config at: {path}")
    
    if not path.exists():
        # If MXCP_CONFIG is not set, generate a default config based on site config
        if "MXCP_CONFIG" not in os.environ and generate_default:
            logger.warning(f"MXCP user config not found at {path}, assuming empty configuration")
            config = _generate_default_config(site_config)
        else:
            raise FileNotFoundError(f"MXCP user config not found at {path}")
    else:
        with open(path) as f:
            config = yaml.safe_load(f)
            logger.debug(f"Loaded user config from file: {config}")
            
        # Interpolate environment variables in the config
        config = _interpolate_env_vars(config)
            
        # Ensure project and profile exist in config
        project_name = site_config["project"]
        profile_name = site_config["profile"]
        
        if "projects" not in config:
            config["projects"] = {}
            
        if project_name not in config["projects"]:
            config["projects"][project_name] = {"profiles": {}}
            
        if "profiles" not in config["projects"][project_name]:
            config["projects"][project_name]["profiles"] = {}
            
        if profile_name not in config["projects"][project_name]["profiles"]:
            logger.warning(f"Project '{project_name}' and/or profile '{profile_name}' not found in user config at {path}, assuming empty configuration")
            config["projects"][project_name]["profiles"][profile_name] = {
                "secrets": [],
                "plugin": {
                    "config": {}
                }
            }
    
    # Apply defaults before validation
    config = _apply_defaults(config)
    logger.debug(f"Config after applying defaults: {config}")
    
    # Load and apply JSON Schema validation
    schema_path = Path(__file__).parent / "schemas" / "mxcp-config-schema-1.0.0.json"
    with open(schema_path) as schema_file:
        schema = json.load(schema_file)
    
    try:
        validate(instance=config, schema=schema)
    except ValidationError as e:
        raise ValueError(f"Invalid user config: {e.message}")
    
    return config
