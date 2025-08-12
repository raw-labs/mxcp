import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, cast

import yaml
from jsonschema import ValidationError, validate

from mxcp.config._types import SiteConfig, UserConfig
from mxcp.config.migration import check_and_migrate_legacy_version
from mxcp.config.references import interpolate_all

logger = logging.getLogger(__name__)

__all__ = ["load_user_config", "generate_user_config_from_site"]


def _apply_defaults(config: Dict[str, Any]) -> UserConfig:
    """Apply default values to the user config"""
    # Create a copy to avoid modifying the input
    config = config.copy()

    # Apply transport defaults
    if "transport" not in config:
        config["transport"] = {}

    transport = config["transport"]
    if "provider" not in transport:
        transport["provider"] = "streamable-http"

    if "http" not in transport:
        transport["http"] = {}

    http_config = transport["http"]
    if "port" not in http_config:
        http_config["port"] = 8000
    if "host" not in http_config:
        http_config["host"] = "localhost"
    if "stateless" not in http_config:
        http_config["stateless"] = False

    # Ensure each profile has at least empty secrets, plugin, and auth config
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
            if "auth" not in profile:
                profile["auth"] = {"provider": "none"}
            elif profile["auth"] is None:
                profile["auth"] = {"provider": "none"}
            else:
                # Ensure persistence defaults are set if auth is enabled and provider is not 'none'
                auth = profile["auth"]
                if auth.get("provider", "none") != "none":
                    if "persistence" not in auth:
                        # Add default persistence configuration
                        auth["persistence"] = {
                            "type": "sqlite",
                            "path": str(Path.home() / ".mxcp" / "oauth.db"),
                        }
                    else:
                        # Apply defaults to existing persistence config
                        persistence = auth["persistence"]
                        if "type" not in persistence:
                            persistence["type"] = "sqlite"
                        if "path" not in persistence:
                            persistence["path"] = str(Path.home() / ".mxcp" / "oauth.db")

    return cast(UserConfig, config)


def _generate_default_config(site_config: SiteConfig) -> UserConfig:
    """Generate a default user config based on site config"""
    project_name = site_config["project"]
    profile_name = site_config["profile"]

    logger.debug(f"Generating default config for project: {project_name}, profile: {profile_name}")
    logger.debug(f"Site config: {site_config}")

    config = {
        "mxcp": 1,
        "projects": {
            project_name: {"profiles": {profile_name: {"secrets": [], "plugin": {"config": {}}}}}
        },
    }
    logger.debug(f"Generated default config: {config}")
    return cast(UserConfig, config)


def load_user_config(
    site_config: SiteConfig, generate_default: bool = True, resolve_refs: bool = True
) -> UserConfig:
    """Load the user configuration from ~/.mxcp/config.yml or MXCP_CONFIG env var.

    If the config file doesn't exist and MXCP_CONFIG is not set, generates a default config
    based on the site config if generate_default is True.

    The configuration supports multiple ways to inject values:

    1. Environment variable interpolation using ${ENV_VAR} syntax:
        database: ${DB_NAME}
        password: ${DB_PASSWORD}

    2. Vault integration using vault:// URLs:
        password: vault://secret/db#password

    3. 1Password integration using op:// URLs:
        password: op://vault/item/field
        totp: op://vault/item/field?attribute=otp

    4. File path references using file:// URLs:
        api_key: file:///path/to/api_key.txt
        ssl_cert: file://certs/server.crt

    Args:
        site_config: The site configuration loaded from mxcp-site.yml
        generate_default: Whether to generate a default config if the file doesn't exist
        resolve_refs: Whether to resolve external references (vault://, op://, file://, ${ENV_VAR}).
                     Set to False to get the raw template configuration.

    Returns:
        The validated user configuration (with resolved values if resolve_refs=True)

    Raises:
        FileNotFoundError: If the config file doesn't exist and generate_default is False
        ValueError: If an environment variable is referenced but not set, or URL resolution fails
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

        # Check for legacy version format and provide migration guidance (stops execution)
        check_and_migrate_legacy_version(config, "user", str(path))

        # Interpolate environment variables and vault URLs in the config if requested
        if resolve_refs:
            vault_config = config.get("vault")
            op_config = config.get("onepassword")
            config = interpolate_all(config, vault_config, op_config)

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
            logger.debug(
                f"Project '{project_name}' and/or profile '{profile_name}' not found in user config at {path}, assuming empty configuration"
            )
            config["projects"][project_name]["profiles"][profile_name] = {
                "secrets": [],
                "plugin": {"config": {}},
            }

    # Apply defaults before validation
    validated_config = _apply_defaults(cast(Dict[str, Any], config))
    logger.debug(f"Config after applying defaults: {validated_config}")

    # Load and apply JSON Schema validation
    schema_path = Path(__file__).parent / "config_schemas" / "mxcp-config-schema-1.json"
    with open(schema_path) as schema_file:
        schema = json.load(schema_file)

    try:
        validate(instance=validated_config, schema=schema)
    except ValidationError as e:
        raise ValueError(f"Invalid user config: {e.message}")

    return validated_config
