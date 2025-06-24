from typing import Dict, Any
from mxcp.config.types import SiteConfig, UserConfig
import logging

logger = logging.getLogger(__name__)

def _get_profile_config(user_config: UserConfig, project: str, profile: str) -> Dict[str, Any]:
    """Get the current profile's config from user config"""
    logger.debug(f"Getting profile config for project: {project}, profile: {profile}")
    logger.debug(f"User config: {user_config}")
    
    project_config = user_config["projects"].get(project)
    if not project_config:
        raise ValueError(f"Project '{project}' not found in user config")
    
    logger.debug(f"Project config: {project_config}")
    profile_config = project_config["profiles"].get(profile)
    if not profile_config:
        raise ValueError(f"Profile '{profile}' not found in project '{project}'")
    
    logger.debug(f"Profile config: {profile_config}")
    return profile_config

def inject_secrets(con, site_config: SiteConfig, user_config: UserConfig, profile: str):
    """Inject secrets into DuckDB session"""
    logger.debug(f"Injecting secrets for profile: {profile}")
    logger.debug(f"Site config: {site_config}")
    logger.debug(f"User config: {user_config}")
    
    # Get profile config
    profile_config = _get_profile_config(user_config, site_config["project"], profile)
    secrets = profile_config.get("secrets", [])
    logger.debug(f"Found secrets: {secrets}")
    
    # Get list of required secrets from site config
    required_secrets = set(site_config.get("secrets", []))
    logger.debug(f"Required secrets: {required_secrets}")
    
    # Check if all required secrets are defined
    defined_secrets = {s["name"] for s in secrets}
    missing_secrets = required_secrets - defined_secrets
    if missing_secrets:
        raise ValueError(f"Missing required secrets: {', '.join(missing_secrets)}")
    
    # Create secrets in DuckDB
    for secret in secrets:
        if secret["name"] not in required_secrets:
            continue  # Skip secrets not required by this repo
        
        # Build CREATE TEMPORARY SECRET statement
        params = []
        for key, value in secret["parameters"].items():
            # Handle special case for nested dictionaries (e.g., HTTP headers)
            if isinstance(value, dict):
                # Convert dict to DuckDB MAP syntax
                map_items = [f"'{k}': '{v}'" for k, v in value.items()]
                params.append(f"{key} MAP {{{', '.join(map_items)}}}")
            else:
                params.append(f"{key} '{value}'")
        
        create_secret_sql = f"""
        CREATE TEMPORARY SECRET {secret['name']} (
            TYPE {secret['type']},
            {', '.join(params)}
        )
        """
        
        try:
            logger.debug(f"Creating secret with SQL: {create_secret_sql}")
            con.execute(create_secret_sql)
        except Exception as e:
            # Log the error but continue - this allows MXCP to support any secret type
            # while DuckDB only creates the ones it understands
            logger.debug(f"Could not create secret '{secret['name']}' in DuckDB: {e}")
            logger.debug("This secret will still be accessible via config.get_secret() in Python endpoints")