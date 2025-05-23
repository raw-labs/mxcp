import os
import sys
import subprocess
import click
from ..config.site_config import load_site_config, find_repo_root
from ..config.user_config import load_user_config
from ..engine.dbt_runner import configure_dbt

@click.command(name="dbt-config")
@click.option("--profile", help="Override the profile name from raw-site.yml")
@click.option("--dry-run", is_flag=True, help="Show what would be written without making changes")
@click.option("--force", is_flag=True, help="Overwrite existing profile without confirmation")
@click.option("--embed-secrets", is_flag=True, help="Embed secrets directly in profiles.yml")
def dbt_config(profile: str, dry_run: bool, force: bool, embed_secrets: bool):
    """Generate / patch the dbt side-car files (dbt_project.yml + profiles.yml).
    
    Default mode writes env_var() templates, so secrets stay out of YAML.
    Use --embed-secrets to flatten secrets straight into profiles.yml.
    """
    # Load configs
    try:
        repo_root = find_repo_root()
    except FileNotFoundError:
        raise click.ClickException("No raw-site.yml found in current directory or parents")
    
    site_config = load_site_config(repo_root)
    user_config = load_user_config(site_config)
    
    configure_dbt(
        site_config=site_config,
        user_config=user_config,
        profile=profile,
        dry_run=dry_run,
        force=force,
        embed_secrets=embed_secrets
    )

@click.command(name="dbt", context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True
))
@click.pass_context
def dbt_wrapper(ctx):
    """Wrapper that injects secrets as env vars, then delegates to the real dbt CLI.
    
    Example:
        raw dbt run --select my_model
    """
    # Load configs
    try:
        repo_root = find_repo_root()
    except FileNotFoundError:
        raise click.ClickException("No raw-site.yml found in current directory or parents")
    
    site_config = load_site_config(repo_root)
    user_config = load_user_config(site_config)
    
    # Check dbt is enabled
    if not site_config.get("dbt", {}).get("enabled", True):
        raise click.ClickException("dbt integration is disabled in raw-site.yml")
    
    # Get project and profile names
    project = site_config["project"]
    profile = site_config["profile"]
    
    # Get secrets from user config
    project_config = user_config["projects"].get(project)
    if not project_config:
        raise click.ClickException(f"Project '{project}' not found in user config")
    
    profile_config = project_config["profiles"].get(profile)
    if not profile_config:
        raise click.ClickException(f"Profile '{profile}' not found in project '{project}'")
    
    secrets = profile_config.get("secrets", {})
    
    # Prepare environment
    env = os.environ.copy()
    for name, params in secrets.items():
        for key, value in params.items():
            var = f"RAW_SECRET_{name.upper()}_{key.upper()}"
            env[var] = value
    
    # Build dbt command
    cmd = ["dbt"] + ctx.args
    
    # Run dbt
    try:
        subprocess.run(cmd, env=env, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)