import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
import click
from ..config.site_config import find_repo_root
from ..config.types import SiteConfig, UserConfig
import time

def _get_dbt_profiles_dir() -> Path:
    """Get the dbt profiles directory path."""
    return Path.home() / ".dbt"

def _get_dbt_profiles_path() -> Path:
    """Get the path to dbt profiles.yml."""
    return _get_dbt_profiles_dir() / "profiles.yml"

def _get_dbt_project_path() -> Path:
    """Get the path to dbt_project.yml in the current directory."""
    return Path.cwd() / "dbt_project.yml"

def _load_profiles() -> Dict[str, Any]:
    """Load existing dbt profiles or return empty dict."""
    profiles_path = _get_dbt_profiles_path()
    if profiles_path.exists():
        with open(profiles_path) as f:
            return yaml.safe_load(f) or {}
    return {}

def _load_dbt_project() -> Dict[str, Any]:
    """Load existing dbt_project.yml or return empty dict."""
    project_path = _get_dbt_project_path()
    if project_path.exists():
        with open(project_path) as f:
            return yaml.safe_load(f) or {}
    return {}

def _save_profiles(profiles: Dict[str, Any]) -> None:
    """Save dbt profiles atomically."""
    profiles_path = _get_dbt_profiles_path()
    profiles_dir = profiles_path.parent
    profiles_dir.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file first
    temp_path = profiles_path.with_suffix(".yml.tmp")
    with open(temp_path, "w") as f:
        yaml.safe_dump(profiles, f, default_flow_style=False)
    
    # Atomic rename
    temp_path.rename(profiles_path)

def _save_dbt_project(project_config: Dict[str, Any]) -> None:
    """Save dbt_project.yml atomically."""
    project_path = _get_dbt_project_path()
    
    # Write to temp file first
    temp_path = project_path.with_suffix(".yml.tmp")
    with open(temp_path, "w") as f:
        yaml.safe_dump(project_config, f, default_flow_style=False)
    
    # Atomic rename
    temp_path.rename(project_path)

def _map_secret_to_dbt_format(secret: Dict[str, Any], embed_secrets: bool) -> Dict[str, Any]:
    """Map a RAW secret to dbt's expected format based on its type.
    
    Args:
        secret: The secret configuration from RAW config
        embed_secrets: Whether to embed actual values or use env vars
        
    Returns:
        Secret configuration in dbt's expected format, or None if type not supported
    """
    if secret["type"] != "http":
        return None
        
    secret_name = secret["name"]
    parameters = secret["parameters"]
    
    # Handle both formats:
    # 1. Single header: { "BEARER_TOKEN": "value" }
    # 2. Multiple headers: { "EXTRA_HTTP_HEADERS": { "Header": "value" } }
    
    headers = {}
    if "BEARER_TOKEN" in parameters:
        if embed_secrets:
            headers["Authorization"] = f"Bearer {parameters['BEARER_TOKEN']}"
        else:
            env_var = f"RAW_SECRET_{secret_name.upper()}_BEARER_TOKEN"
            headers["Authorization"] = f"Bearer {{{{ env_var('{env_var}') }}}}"
    elif "EXTRA_HTTP_HEADERS" in parameters:
        headers = {}
        for key, value in parameters["EXTRA_HTTP_HEADERS"].items():
            if embed_secrets:
                headers[key] = value
            else:
                env_var = f"RAW_SECRET_{secret_name.upper()}_HEADERS_{key.upper()}"
                headers[key] = f"{{{{ env_var('{env_var}') }}}}"
    
    if not headers:
        return None
        
    # Convert headers to dbt's expected format
    headers_str = ", ".join(f"'{k}': '{v}'" for k, v in headers.items())
    return {
        "name": secret_name,
        "type": "http",
        "scope": parameters.get("scope", ""),  # Optional scope
        "extra_http_headers": f"map {{ {headers_str} }}"
    }

def _build_profile_block(
    project: str,
    profile: str,
    duckdb_path: str,
    secrets: Optional[Dict[str, Any]] = None,
    embed_secrets: bool = False
) -> Dict[str, Any]:
    """Build a dbt profile block with DuckDB configuration.
    
    Args:
        project: RAW project name
        profile: RAW profile name
        duckdb_path: Path to DuckDB file
        secrets: Optional secrets to include
        embed_secrets: Whether to embed secrets directly or use env vars
    
    Returns:
        Profile block for profiles.yml
    """
    # Create dbt profile name as <project>_<profile>
    dbt_profile = f"{project}_{profile}"
    
    # Build the minimal required configuration
    block = {
        dbt_profile: {
            "target": profile,  # Use RAW profile name as target
            "outputs": {
                profile: {  # Use RAW profile name as output key
                    "type": "duckdb",
                    "path": duckdb_path,
                    "extensions": ["httpfs"]
                }
            }
        }
    }
    
    if secrets:
        # Initialize secrets array in the output
        block[dbt_profile]["outputs"][profile]["secrets"] = []
        
        for secret in secrets:
            if not isinstance(secret, dict) or "name" not in secret or "type" not in secret or "parameters" not in secret:
                continue
            
            try:
                # Map the secret to dbt's expected format
                dbt_secret = _map_secret_to_dbt_format(secret, embed_secrets)
                if dbt_secret:  # Only add if mapping was successful
                    block[dbt_profile]["outputs"][profile]["secrets"].append(dbt_secret)
            except Exception as e:
                click.echo(f"Warning: Failed to process secret '{secret.get('name', 'unknown')}': {e}", err=True)
                continue
    
    return block

def _build_dbt_project(
    project: str,
    profile: str,
    models_path: Optional[str] = None
) -> Dict[str, Any]:
    """Build dbt_project.yml configuration.
    
    Args:
        project: RAW project name
        profile: RAW profile name
        models_path: Optional custom models path
    
    Returns:
        dbt_project.yml configuration
    """
    # Create dbt profile name as <project>_<profile>
    dbt_profile = f"{project}_{profile}"
    
    # Build the minimal required configuration
    return {
        "name": project,
        "profile": dbt_profile,  # Use combined profile name
        "version": "1.0.0",
        "config-version": 2,
        "model-paths": [models_path or "models"],
        "analysis-paths": ["analyses"],
        "test-paths": ["tests"],
        "seed-paths": ["seeds"],
        "macro-paths": ["macros"],
        "snapshot-paths": ["snapshots"],
        "target-path": "target",
        "clean-targets": ["target", "dbt_packages"]
    }

def _merge_profile_blocks(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Merge new profile block into existing one, preserving user configuration.
    
    Args:
        existing: Existing profile configuration
        new: New profile configuration to merge in
    
    Returns:
        Merged profile configuration
    """
    result = existing.copy()
    
    for profile_name, profile_config in new.items():
        if profile_name not in result:
            result[profile_name] = profile_config
            continue
            
        # Merge outputs
        if "outputs" in profile_config:
            if "outputs" not in result[profile_name]:
                result[profile_name]["outputs"] = {}
            
            for output_name, output_config in profile_config["outputs"].items():
                if output_name not in result[profile_name]["outputs"]:
                    result[profile_name]["outputs"][output_name] = {}
                
                # Update only the keys we need
                for key, value in output_config.items():
                    result[profile_name]["outputs"][output_name][key] = value
        
        # Update target if specified
        if "target" in profile_config:
            result[profile_name]["target"] = profile_config["target"]
    
    return result

def _merge_dbt_project(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Merge new dbt project config into existing one, preserving user configuration.
    
    Args:
        existing: Existing dbt project configuration
        new: New dbt project configuration to merge in
    
    Returns:
        Merged dbt project configuration
    """
    result = existing.copy()
    
    # Update only the keys we need
    for key, value in new.items():
        result[key] = value
    
    return result

def configure_dbt(
    site_config: SiteConfig,
    user_config: UserConfig,
    profile: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
    embed_secrets: bool = False
) -> None:
    """Configure dbt profiles and project for the current project.
    
    Args:
        site_config: The site configuration loaded from raw-site.yml
        user_config: The user configuration loaded from ~/.raw/config.yml
        profile: Optional profile name override
        dry_run: If True, only print changes without writing
        force: If True, overwrite existing profile without confirmation
        embed_secrets: If True, embed secrets directly in profiles.yml
    """
    # 1. Check dbt is enabled
    if not site_config.get("dbt", {}).get("enabled", True):
        raise click.ClickException("dbt integration is disabled in raw-site.yml")
    
    # 2. Handle embed_secrets requirement
    if embed_secrets and not force:
        raise click.ClickException("--embed-secrets requires --force to be set")
    
    if embed_secrets and not dry_run:
        click.echo("WARNING: Embedding secrets directly in profiles.yml")
        click.echo("This will write sensitive values to disk!")
        for i in range(5, 0, -1):
            click.echo(f"Continuing in {i}...", nl=False)
            time.sleep(1)
            click.echo("\r", nl=False)
        click.echo("\nContinuing...")
    
    # 3. Get project and profile names
    project = site_config["project"]
    profile_name = profile or site_config["profile"]
    
    # Create dbt profile name as <project>_<profile>
    dbt_profile = f"{project}_{profile_name}"
    
    # 4. Get DuckDB path using the same convention as the rest of the codebase
    repo_root = find_repo_root()
    duckdb_path = site_config["profiles"][profile_name]["duckdb"]["path"]
    if not os.path.isabs(duckdb_path):
        # If path is not absolute, it should be relative to repo root
        duckdb_path = str(repo_root / duckdb_path)
    
    # 5. Get secrets from user config
    project_config = user_config["projects"].get(project)
    if not project_config:
        raise click.ClickException(f"Project '{project}' not found in user config")
    
    profile_config = project_config["profiles"].get(profile_name)
    if not profile_config:
        raise click.ClickException(f"Profile '{profile_name}' not found in project '{project}'")
    
    secrets = profile_config.get("secrets", [])
    
    # 6. Load existing profiles and project config
    profiles = _load_profiles()
    dbt_project = _load_dbt_project()
    
    # 7. Build new profile block
    new_profile_block = _build_profile_block(
        project=project,
        profile=profile_name,
        duckdb_path=duckdb_path,
        secrets=secrets,
        embed_secrets=embed_secrets
    )
    
    # 8. Build new dbt project config
    new_dbt_project = _build_dbt_project(
        project=project,
        profile=profile_name,
        models_path=site_config.get("dbt", {}).get("models")
    )
    
    # 9. Check for existing profile
    if dbt_profile in profiles:
        if not force:
            raise click.ClickException(f"Profile '{dbt_profile}' already exists. Use --force to update configuration.")
    
    # 10. Merge configurations
    merged_profiles = _merge_profile_blocks(profiles, new_profile_block)
    merged_dbt_project = _merge_dbt_project(dbt_project, new_dbt_project)
    
    # 11. Handle dry run
    if dry_run:
        click.echo("Would write the following to profiles.yml:")
        click.echo(yaml.dump(merged_profiles))
        click.echo("\nWould write the following to dbt_project.yml:")
        click.echo(yaml.dump(merged_dbt_project))
        return
    
    # 12. Write files
    _save_profiles(merged_profiles)
    _save_dbt_project(merged_dbt_project)
    
    # 13. Log success
    mode = "embedded secrets" if embed_secrets else "env_var mode"
    click.echo(f"profiles.yml and dbt_project.yml updated ({mode})")

def run_stale_models():
    print("Stub: run stale dbt models")