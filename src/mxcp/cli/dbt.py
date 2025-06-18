import os
import subprocess
import sys

import click

from ..config.site_config import find_repo_root, load_site_config
from ..config.user_config import load_user_config
from ..engine.dbt_runner import configure_dbt
from .utils import check_command_available, configure_logging


@click.command(name="dbt-config")
@click.option("--profile", help="Override the profile name from mxcp-site.yml")
@click.option("--dry-run", is_flag=True, help="Show what would be written without making changes")
@click.option("--force", is_flag=True, help="Overwrite existing profile without confirmation")
@click.option("--embed-secrets", is_flag=True, help="Embed secrets directly in profiles.yml")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
def dbt_config(profile: str, dry_run: bool, force: bool, embed_secrets: bool, debug: bool):
    """Generate / patch the dbt side-car files (dbt_project.yml + profiles.yml).

    Default mode writes env_var() templates, so secrets stay out of YAML.
    Use --embed-secrets to flatten secrets straight into profiles.yml.
    """
    # Configure logging
    configure_logging(debug)

    # Load configs
    try:
        repo_root = find_repo_root()
    except FileNotFoundError:
        raise click.ClickException("No mxcp-site.yml found in current directory or parents")

    site_config = load_site_config(repo_root)
    user_config = load_user_config(site_config)

    # Check if dbt CLI is available (warn but don't fail)
    if not check_command_available("dbt"):
        click.echo(
            "Warning: dbt CLI is not installed or not available in PATH. "
            "You may want to install dbt-core and dbt-duckdb: pip install dbt-core dbt-duckdb",
            err=True,
        )

    configure_dbt(
        site_config=site_config,
        user_config=user_config,
        profile=profile,
        dry_run=dry_run,
        force=force,
        embed_secrets=embed_secrets,
    )


@click.command(
    name="dbt", context_settings=dict(ignore_unknown_options=True, allow_extra_args=True)
)
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.pass_context
def dbt_wrapper(ctx, debug: bool):
    """Wrapper that injects secrets as env vars, then delegates to the real dbt CLI.

    Example:
        mxcp dbt run --select my_model
    """
    # Configure logging
    configure_logging(debug)

    # Load configs
    try:
        repo_root = find_repo_root()
    except FileNotFoundError:
        raise click.ClickException("No mxcp-site.yml found in current directory or parents")

    site_config = load_site_config(repo_root)
    user_config = load_user_config(site_config)

    # Check dbt is enabled
    if not site_config.get("dbt", {}).get("enabled", True):
        raise click.ClickException("dbt integration is disabled in mxcp-site.yml")

    # Check if dbt CLI is available
    if not check_command_available("dbt"):
        raise click.ClickException(
            "dbt CLI is not installed or not available in PATH. "
            "Please install dbt-core and dbt-duckdb: pip install dbt-core dbt-duckdb"
        )

    # Get project and profile names
    project = site_config["project"]
    profile = site_config["profile"]

    # Get secrets from user config
    project_config = user_config.get("projects", {}).get(project, {})
    profile_config = project_config.get("profiles", {}).get(profile, {})
    secrets = profile_config.get("secrets", [])

    # Prepare environment
    env = os.environ.copy()
    for secret in secrets:
        if not isinstance(secret, dict) or "name" not in secret or "parameters" not in secret:
            continue

        secret_name = secret["name"]
        parameters = secret["parameters"]

        # Handle both string and object parameters
        for param_name, param_value in parameters.items():
            if isinstance(param_value, dict):
                # For map-like parameters (e.g., HTTP headers)
                for key, value in param_value.items():
                    var = f"MXCP_SECRET_{secret_name.upper()}_{param_name.upper()}_{key.upper()}"
                    env[var] = str(value)
            else:
                # For simple string parameters
                var = f"MXCP_SECRET_{secret_name.upper()}_{param_name.upper()}"
                env[var] = str(param_value)

    # Build dbt command
    cmd = ["dbt"] + ctx.args

    # Run dbt
    try:
        subprocess.run(cmd, env=env, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
