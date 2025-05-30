import os
import yaml
import json
from jsonschema import validate, ValidationError
from pathlib import Path
from mxcp.config.types import SiteConfig, UserConfig
from typing import Optional, Dict, Any

def find_repo_root() -> Path:
    """Find the repository root by looking for mxcp-site.yml.
    
    Returns:
        Path to the repository root
        
    Raises:
        FileNotFoundError: If mxcp-site.yml is not found in current directory or any parent
    """
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / "mxcp-site.yml").exists():
            return parent
    raise FileNotFoundError("mxcp-site.yml not found in current directory or any parent directory")

def _apply_defaults(config: dict, repo_root: Path) -> dict:
    """Apply default values to the config"""
    # Create a copy to avoid modifying the input
    config = config.copy()
    
    # Apply defaults for optional sections
    if "dbt" not in config:
        config["dbt"] = {"enabled": True}
    elif "enabled" not in config["dbt"]:
        config["dbt"]["enabled"] = True
        
    # Initialize profiles section if not present
    if "profiles" not in config:
        config["profiles"] = {}
        
    # Get the current profile
    profile = config.get("profile", "default")
    
    # Initialize profile config if not present
    if profile not in config["profiles"]:
        config["profiles"][profile] = {}
        
    # Initialize duckdb config for the profile if not present
    if "duckdb" not in config["profiles"][profile]:
        config["profiles"][profile]["duckdb"] = {}
        
    # Set default DuckDB path for the profile if not specified
    if "path" not in config["profiles"][profile]["duckdb"]:
        config["profiles"][profile]["duckdb"]["path"] = str(repo_root / f"db-{profile}.duckdb")
        
    # Initialize drift config for the profile if not present
    if "drift" not in config["profiles"][profile]:
        config["profiles"][profile]["drift"] = {}
        
    # Set default drift manifest path for the profile if not specified
    if "path" not in config["profiles"][profile]["drift"]:
        config["profiles"][profile]["drift"]["path"] = str(repo_root / f"drift-{profile}.json")

    # Initialize audit config for the profile if not present
    if "audit" not in config["profiles"][profile]:
        config["profiles"][profile]["audit"] = {}
        
    # Set default audit enabled state for the profile if not specified
    if "enabled" not in config["profiles"][profile]["audit"]:
        config["profiles"][profile]["audit"]["enabled"] = False
        
    # Set default audit log path for the profile if not specified
    if "path" not in config["profiles"][profile]["audit"]:
        config["profiles"][profile]["audit"]["path"] = str(repo_root / f"logs-{profile}.duckdb")

    # Initialize extensions section if not present
    if "extensions" not in config:
        config["extensions"] = []
        
    return config

def load_site_config(repo_path: Optional[Path] = None) -> SiteConfig:
    """Load and validate the mxcp-site.yml configuration from the repository.
    
    Args:
        repo_path: Optional path to the repository root. If not provided, uses current directory.
        
    Returns:
        The validated site configuration
    """
    if repo_path is None:
        repo_path = Path.cwd()
    
    config_path = repo_path / "mxcp-site.yml"
    if not config_path.exists():
        raise FileNotFoundError(f"mxcp-site.yml not found at {config_path}")
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    # Load and apply JSON Schema validation
    schema_path = Path(__file__).parent / "schemas" / "mxcp-site-schema-1.0.0.json"
    with open(schema_path) as schema_file:
        schema = json.load(schema_file)
    
    try:
        validate(instance=config, schema=schema)
    except ValidationError as e:
        raise ValueError(f"Site config validation error: {e.message}")
    
    # Apply defaults (e.g., duckdb.path)
    config = _apply_defaults(config, repo_path)
    return config

def get_active_profile(user_config: UserConfig, site_config: SiteConfig, profile: Optional[str] = None) -> Dict[str, Any]:
    """Get the active profile from the user config based on site configuration.
    
    Args:
        user_config: The user configuration loaded from ~/.mxcp/config.yml
        site_config: The site configuration loaded from mxcp-site.yml
        profile: Optional profile name to override the default profile
        
    Returns:
        The active profile configuration
    """
    project_name = site_config["project"]
    profile_name = profile or site_config["profile"]
    
    if project_name not in user_config["projects"]:
        raise ValueError(f"Project '{project_name}' not found in user config")
    
    project = user_config["projects"][project_name]
    if profile_name not in project["profiles"]:
        raise ValueError(f"Profile '{profile_name}' not found in project '{project_name}'")
    
    return project["profiles"][profile_name]
