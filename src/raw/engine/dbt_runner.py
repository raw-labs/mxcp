import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
import click
from ..config.site_config import find_repo_root
from ..config.types import SiteConfig, UserConfig

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
    
    block = {
        dbt_profile: {  # Use combined name as top-level key
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
        if embed_secrets:
            # Use actual secret values from user config
            block[dbt_profile]["outputs"][profile]["secrets"] = secrets
        else:
            # Use env_var() placeholders
            block[dbt_profile]["outputs"][profile]["secrets"] = {
                name: {
                    key: f"{{{{ env_var('RAW_SECRET_{name.upper()}_{key.upper()}') }}}}"
                    for key in params
                }
                for name, params in secrets.items()
            }
    
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
    
    # 2. Get project and profile names
    project = site_config["project"]
    profile_name = profile or site_config["profile"]
    
    # Create dbt profile name as <project>_<profile>
    dbt_profile = f"{project}_{profile_name}"
    
    # 3. Get DuckDB path using the same convention as the rest of the codebase
    repo_root = find_repo_root()
    duckdb_path = site_config["profiles"][profile_name]["duckdb"]["path"]
    if not os.path.isabs(duckdb_path):
        # If path is not absolute, it should be relative to repo root
        duckdb_path = str(repo_root / duckdb_path)
    
    # 4. Get secrets from user config
    project_config = user_config["projects"].get(project)
    if not project_config:
        raise click.ClickException(f"Project '{project}' not found in user config")
    
    profile_config = project_config["profiles"].get(profile_name)
    if not profile_config:
        raise click.ClickException(f"Profile '{profile_name}' not found in project '{project}'")
    
    secrets = profile_config.get("secrets", {})
    
    # 5. Load existing profiles and project config
    profiles = _load_profiles()
    dbt_project = _load_dbt_project()
    
    # 6. Build new profile block
    new_profile_block = _build_profile_block(
        project=project,
        profile=profile_name,
        duckdb_path=duckdb_path,
        secrets=secrets,
        embed_secrets=embed_secrets
    )
    
    # 7. Build new dbt project config
    new_dbt_project = _build_dbt_project(
        project=project,
        profile=profile_name,
        models_path=site_config.get("dbt", {}).get("models")
    )
    
    # 8. Check for existing profile
    if dbt_profile in profiles:
        if profiles[dbt_profile] != new_profile_block[dbt_profile]:
            if not force:
                raise click.ClickException(
                    f"Profile '{dbt_profile}' already exists and differs. Use --force to overwrite."
                )
            if not dry_run:
                click.echo(f"Overwriting existing profile '{dbt_profile}'")
    
    # 9. Check for existing dbt_project.yml
    if dbt_project:
        if dbt_project != new_dbt_project:
            if not force:
                raise click.ClickException(
                    "dbt_project.yml already exists and differs. Use --force to overwrite."
                )
            if not dry_run:
                click.echo("Overwriting existing dbt_project.yml")
    
    # 10. Handle dry run
    if dry_run:
        click.echo("Would write the following to profiles.yml:")
        click.echo(yaml.dump(profiles))
        click.echo("\nWould write the following to dbt_project.yml:")
        click.echo(yaml.dump(new_dbt_project))
        return
    
    # 11. Write files
    profiles.update(new_profile_block)
    _save_profiles(profiles)
    _save_dbt_project(new_dbt_project)
    
    # 12. Log success
    mode = "embedded secrets" if embed_secrets else "env_var mode"
    click.echo(f"profiles.yml and dbt_project.yml updated ({mode})")

def run_stale_models():
    print("Stub: run stale dbt models")