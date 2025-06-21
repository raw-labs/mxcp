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

# Regular expression to match vault://path/to/secret#key patterns
VAULT_URL_PATTERN = re.compile(r'vault://([^#]+)(?:#(.+))?')

def _resolve_vault_url(vault_url: str, vault_config: Optional[Dict[str, Any]]) -> str:
    """Resolve a vault:// URL to retrieve the secret value.
    
    Args:
        vault_url: The vault:// URL to resolve (e.g., vault://secret/myapp#password)
        vault_config: The vault configuration from user config
        
    Returns:
        The resolved secret value
        
    Raises:
        ValueError: If vault is not configured or URL is invalid
        ImportError: If hvac library is not available
        Exception: If vault connection or secret retrieval fails
    """
    if not vault_config or not vault_config.get('enabled', False):
        raise ValueError(f"Vault URL '{vault_url}' found but Vault is not enabled in configuration")
    
    # Parse the vault URL
    match = VAULT_URL_PATTERN.match(vault_url)
    if not match:
        raise ValueError(f"Invalid vault URL format: '{vault_url}'. Expected format: vault://path/to/secret#key")
    
    secret_path = match.group(1)
    secret_key = match.group(2)
    
    if not secret_key:
        raise ValueError(f"Vault URL '{vault_url}' must specify a key after '#'. Expected format: vault://path/to/secret#key")
    
    try:
        import hvac
    except ImportError:
        raise ImportError("hvac library is required for Vault integration. Install with: pip install hvac")
    
    # Get Vault configuration
    vault_address = vault_config.get('address')
    if not vault_address:
        raise ValueError("Vault address must be configured when using vault:// URLs")
    
    token_env = vault_config.get('token_env', 'VAULT_TOKEN')
    vault_token = os.environ.get(token_env)
    if not vault_token:
        raise ValueError(f"Vault token not found in environment variable '{token_env}'")
    
    # Initialize Vault client
    try:
        client = hvac.Client(url=vault_address, token=vault_token)
        
        if not client.is_authenticated():
            raise ValueError("Failed to authenticate with Vault")
        
        # Read the secret
        # Try KV v2 first, then fall back to KV v1
        try:
            # KV v2 format
            response = client.secrets.kv.v2.read_secret_version(path=secret_path)
            secret_data = response['data']['data']
        except Exception:
            try:
                # KV v1 format
                response = client.secrets.kv.v1.read_secret(path=secret_path)
                secret_data = response['data']
            except Exception as e:
                raise ValueError(f"Failed to read secret from Vault path '{secret_path}': {e}")
        
        if secret_key not in secret_data:
            raise ValueError(f"Key '{secret_key}' not found in Vault secret at path '{secret_path}'")
        
        return secret_data[secret_key]
        
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Error connecting to Vault: {e}")

def _interpolate_values(value: Any, vault_config: Optional[Dict[str, Any]] = None) -> Any:
    """Interpolate environment variables and vault URLs in string values.
    
    Args:
        value: The value to process. Can be a string, dict, list, or other type.
        vault_config: Optional vault configuration for resolving vault:// URLs
        
    Returns:
        The processed value with environment variables and vault URLs interpolated.
        
    Raises:
        ValueError: If an environment variable is referenced but not set, or vault resolution fails.
    """
    if isinstance(value, str):
        # Check for vault:// URLs first
        if value.startswith('vault://'):
            return _resolve_vault_url(value, vault_config)
        
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
        return {k: _interpolate_values(v, vault_config) for k, v in value.items()}
    elif isinstance(value, list):
        return [_interpolate_values(item, vault_config) for item in value]
    else:
        return value

def _apply_defaults(config: dict) -> dict:
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
                            "path": str(Path.home() / ".mxcp" / "oauth.db")
                        }
                    else:
                        # Apply defaults to existing persistence config
                        persistence = auth["persistence"]
                        if "type" not in persistence:
                            persistence["type"] = "sqlite"
                        if "path" not in persistence:
                            persistence["path"] = str(Path.home() / ".mxcp" / "oauth.db")
    
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
            
        # Interpolate environment variables and vault URLs in the config
        vault_config = config.get('vault')
        config = _interpolate_values(config, vault_config)
            
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
            logger.debug(f"Project '{project_name}' and/or profile '{profile_name}' not found in user config at {path}, assuming empty configuration")
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
