from typing import Dict, Any
from raw.config.types import SiteConfig, UserConfig

def _get_profile_config(user_config: UserConfig, project: str, profile: str) -> Dict[str, Any]:
    """Get the current profile's config from user config"""
    project_config = user_config["projects"].get(project)
    if not project_config:
        raise ValueError(f"Project '{project}' not found in user config")
        
    profile_config = project_config["profiles"].get(profile)
    if not profile_config:
        raise ValueError(f"Profile '{profile}' not found in project '{project}'")
        
    return profile_config

def inject_secrets(con, site_config: SiteConfig, user_config: UserConfig, profile: str):
    """Inject secrets into DuckDB session"""
    # Get profile config
    profile_config = _get_profile_config(user_config, site_config["project"], profile)
    secrets = profile_config.get("secrets", [])
    
    # Get list of required secrets from site config
    required_secrets = set(site_config.get("secrets", []))
    
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
            # Handle special case for HTTP headers
            if isinstance(value, dict):
                value = str(value)  # Convert dict to string representation
            params.append(f"{key} '{value}'")
            
        create_secret_sql = f"""
        CREATE TEMPORARY SECRET {secret['name']} (
            TYPE {secret['type']},
            {', '.join(params)}
        )
        """
        con.execute(create_secret_sql)