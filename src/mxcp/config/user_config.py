import os
import yaml
from pathlib import Path
import json
from jsonschema import validate, ValidationError
from mxcp.config.types import UserConfig, SiteConfig
import logging

logger = logging.getLogger(__name__)

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
    
    Args:
        site_config: The site configuration loaded from mxcp-site.yml
        generate_default: Whether to generate a default config if the file doesn't exist
        
    Returns:
        The validated user configuration
        
    Raises:
        FileNotFoundError: If the config file doesn't exist and generate_default is False
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
        raise ValueError(f"User config validation error: {e.message}")
    return config
