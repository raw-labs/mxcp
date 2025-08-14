import os
import subprocess
import sys
from typing import Any

import click

from mxcp.server.core.config.site_config import find_repo_root, load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.services.dbt.runner import configure_dbt

from .utils import check_command_available, configure_logging


@click.command(name="dbt-config")
@click.option("--profile", help="Override the profile name from mxcp-site.yml")
@click.option("--dry-run", is_flag=True, help="Show what would be written without making changes")
@click.option("--force", is_flag=True, help="Overwrite existing profile without confirmation")
@click.option("--embed-secrets", is_flag=True, help="Embed secrets directly in profiles.yml")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
def dbt_config(profile: str, dry_run: bool, force: bool, embed_secrets: bool, debug: bool) -> None:
    """Generate / patch the dbt side-car files (dbt_project.yml + profiles.yml).

    Default mode writes env_var() templates, so secrets stay out of YAML.
    Use --embed-secrets to flatten secrets straight into profiles.yml.
    """
    # Configure logging
    configure_logging(debug)

    click.echo(f"\n{click.style('🔧 Configuring dbt integration', fg='cyan', bold=True)}")

    # Load configs
    try:
        repo_root = find_repo_root()
    except FileNotFoundError as e:
        click.echo(
            f"\n{click.style('❌ Error:', fg='red', bold=True)} No mxcp-site.yml found in current directory or parents"
        )
        raise click.ClickException("No mxcp-site.yml found in current directory or parents") from e

    site_config = load_site_config(repo_root)
    user_config = load_user_config(site_config)

    click.echo(f"   • Project: {click.style(site_config['project'], fg='yellow')}")
    click.echo(f"   • Profile: {click.style(profile or site_config['profile'], fg='yellow')}")

    if embed_secrets:
        click.echo(
            f"   • Mode: {click.style('Embed secrets (⚠️  not recommended for production)', fg='red')}"
        )
    else:
        click.echo(f"   • Mode: {click.style('Environment variables (secure)', fg='green')}")

    if dry_run:
        click.echo(
            f"   • {click.style('DRY RUN MODE', fg='magenta', bold=True)} - No files will be modified"
        )

    # Check if dbt CLI is available (warn but don't fail)
    if not check_command_available("dbt"):
        click.echo(
            f"\n{click.style('⚠️  Warning:', fg='yellow')} dbt CLI is not installed or not available in PATH."
        )
        click.echo(f"   Install with: {click.style('pip install dbt-core dbt-duckdb', fg='cyan')}")

    click.echo()  # Empty line for spacing

    configure_dbt(
        site_config=site_config,
        user_config=user_config,
        profile=profile,
        dry_run=dry_run,
        force=force,
        embed_secrets=embed_secrets,
    )

    if not dry_run:
        click.echo(f"\n{click.style('✅ dbt configuration complete!', fg='green', bold=True)}")
        click.echo(f"\n{click.style('📚 Files created/updated:', fg='cyan', bold=True)}")
        click.echo("   • dbt_project.yml - dbt project configuration")
        click.echo("   • profiles.yml - Connection profile for DuckDB")

        click.echo(f"\n{click.style('🚀 Next steps:', fg='yellow', bold=True)}")
        click.echo(f"   1. Run {click.style('dbt deps', fg='cyan')} to install dependencies")
        click.echo(f"   2. Run {click.style('dbt run', fg='cyan')} to execute your models")
        click.echo(f"   3. Or use {click.style('mxcp dbt run', fg='cyan')} to auto-inject secrets")
        click.echo()


@click.command(
    name="dbt", context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.pass_context
def dbt_wrapper(ctx: click.Context, debug: bool) -> None:
    """Wrapper that injects secrets as env vars, then delegates to the real dbt CLI.

    \b
    Example:
        mxcp dbt run --select my_model
    """
    # Configure logging
    configure_logging(debug)

    # Load configs
    try:
        repo_root = find_repo_root()
    except FileNotFoundError as e:
        click.echo(
            f"\n{click.style('❌ Error:', fg='red', bold=True)} No mxcp-site.yml found in current directory or parents"
        )
        raise click.ClickException("No mxcp-site.yml found in current directory or parents") from e

    site_config = load_site_config(repo_root)
    user_config = load_user_config(site_config)

    # Check dbt is enabled
    dbt_config = site_config.get("dbt", {})
    if not dbt_config or not dbt_config.get("enabled", True):
        click.echo(
            f"\n{click.style('❌ Error:', fg='red', bold=True)} dbt integration is disabled in mxcp-site.yml"
        )
        raise click.ClickException("dbt integration is disabled in mxcp-site.yml")

    # Check if dbt CLI is available
    if not check_command_available("dbt"):
        click.echo(
            f"\n{click.style('❌ Error:', fg='red', bold=True)} dbt CLI is not installed or not available in PATH."
        )
        click.echo(f"   Install with: {click.style('pip install dbt-core dbt-duckdb', fg='cyan')}")
        raise click.ClickException(
            "dbt CLI is not installed. Please install dbt-core and dbt-duckdb."
        )

    # Get project and profile names
    project = site_config["project"]
    profile = site_config["profile"]

    # Show what we're doing
    dbt_command = " ".join(ctx.args)
    click.echo(
        f"\n{click.style('🚀 Running dbt with MXCP secret injection', fg='cyan', bold=True)}"
    )
    click.echo(f"   • Project: {click.style(project, fg='yellow')}")
    click.echo(f"   • Profile: {click.style(profile, fg='yellow')}")
    click.echo(f"   • Command: {click.style(f'dbt {dbt_command}', fg='green')}")

    # Get secrets from user config
    project_config: Any = user_config.get("projects", {}).get(project, {})
    profile_config = project_config.get("profiles", {}).get(profile, {})
    secrets = profile_config.get("secrets", [])

    # Prepare environment
    env = os.environ.copy()
    for secret in secrets or []:
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

    # Count secrets injected
    secret_count = len([k for k in env if k.startswith("MXCP_SECRET_")])
    if secret_count > 0:
        click.echo(
            f"   • Secrets: {click.style(f'{secret_count} environment variables injected', fg='green')}"
        )

    click.echo(f"\n{click.style('Delegating to dbt...', fg='yellow')}")
    click.echo("-" * 60 + "\n")

    # Run dbt
    try:
        subprocess.run(cmd, env=env, check=True)
        click.echo("\n" + "-" * 60)
        click.echo(
            f"{click.style('✅ dbt command completed successfully!', fg='green', bold=True)}\n"
        )
    except subprocess.CalledProcessError as e:
        click.echo("\n" + "-" * 60)
        click.echo(
            f"{click.style('❌ dbt command failed with exit code:', fg='red', bold=True)} {e.returncode}\n"
        )
        sys.exit(e.returncode)
