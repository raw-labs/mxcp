import asyncio
import json
from pathlib import Path
from typing import Any

import click

from mxcp.sdk.auth import UserContext
from mxcp.server.core.config.analytics import track_command_with_timing
from mxcp.server.core.config.site_config import load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.interfaces.cli.table_renderer import format_result_for_display
from mxcp.server.interfaces.cli.utils import (
    configure_logging,
    get_env_flag,
    get_env_profile,
    output_error,
    output_result,
)
from mxcp.server.services.endpoints import execute_endpoint


@click.command(name="run")
@click.argument("endpoint_type", type=click.Choice(["tool", "resource", "prompt"]))
@click.argument("name")
@click.option(
    "--param",
    "-p",
    multiple=True,
    help="Parameter in format name=value or name=@file.json for complex values",
)
@click.option("--user-context", "-u", help="User context as JSON string or @file.json")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option(
    "--skip-output-validation",
    is_flag=True,
    help="Skip output validation against the return type definition",
)
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("run")  # type: ignore[misc]
def run_endpoint(
    endpoint_type: str,
    name: str,
    param: tuple[str, ...],
    user_context: str | None,
    profile: str | None,
    json_output: bool,
    debug: bool,
    skip_output_validation: bool,
    readonly: bool,
) -> None:
    """Run an endpoint (tool, resource, or prompt).

    \b
    Parameters can be provided in two ways:
    1. Simple values: --param name=value
    2. Complex values from JSON file: --param name=@file.json

    \b
    User context can be provided for policy enforcement:
    --user-context '{"user_id": "123", "role": "admin", "permissions": ["read", "write"]}'
    --user-context @user_context.json

    \b
    Examples:
        mxcp run tool my_tool --param name=value
        mxcp run tool my_tool --param complex=@data.json
        mxcp run tool my_tool --readonly
        mxcp run tool my_tool --user-context '{"role": "admin"}'
    """
    # Configure logging first
    configure_logging(debug)

    try:
        # Run async implementation
        asyncio.run(
            _run_endpoint_impl(
                endpoint_type=endpoint_type,
                name=name,
                param=param,
                user_context=user_context,
                profile=profile,
                json_output=json_output,
                debug=debug,
                skip_output_validation=skip_output_validation,
                readonly=readonly,
            )
        )
    except click.ClickException:
        # Let Click exceptions propagate - they have their own formatting
        raise
    except KeyboardInterrupt:
        # Handle graceful shutdown
        if not json_output:
            click.echo("\nOperation cancelled by user", err=True)
        raise click.Abort() from None
    except Exception as e:
        # Only catch non-Click exceptions
        output_error(e, json_output, debug)


async def _run_endpoint_impl(
    *,
    endpoint_type: str,
    name: str,
    param: tuple[str, ...],
    user_context: str | None,
    profile: str | None,
    json_output: bool,
    debug: bool,
    skip_output_validation: bool,
    readonly: bool,
) -> None:
    """Async implementation of the run command."""
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")

    # Show what we're running (only in non-JSON mode)
    if not json_output:
        click.echo(
            f"\n{click.style('🚀 Running', fg='cyan', bold=True)} {click.style(endpoint_type, fg='yellow')} {click.style(name, fg='green', bold=True)}"
        )
        if param:
            click.echo(f"{click.style('📋 Parameters:', fg='cyan')}")
            for p in param:
                if "=" in p:
                    key, value = p.split("=", 1)
                    if value.startswith("@"):
                        click.echo(f"   • {key} = <from file: {value[1:]}>")
                    else:
                        # Truncate long values
                        display_value = value if len(value) <= 50 else value[:47] + "..."
                        click.echo(f"   • {key} = {display_value}")
        if readonly:
            click.echo(f"{click.style('🔒 Mode:', fg='yellow')} Read-only")
        click.echo()  # Empty line for spacing

    # Load configs
    site_config = load_site_config()
    user_config = load_user_config(site_config)

    profile_name = profile or site_config["profile"]

    # Parse user context if provided
    user_context_obj = None
    if user_context:
        if user_context.startswith("@"):
            # Load from file
            file_path = Path(user_context[1:])
            if not file_path.exists():
                raise click.BadParameter(f"User context file not found: {file_path}")
            try:
                with open(file_path) as f:
                    context_data = json.load(f)
            except json.JSONDecodeError as e:
                raise click.BadParameter(
                    f"Invalid JSON in user context file {file_path}: {e}"
                ) from e
        else:
            # Parse as JSON string
            try:
                context_data = json.loads(user_context)
            except json.JSONDecodeError as e:
                raise click.BadParameter(f"Invalid JSON in user context: {e}") from e

        # Create UserContext object from the data
        user_context_obj = UserContext(
            provider="cli",  # Special provider for CLI usage
            user_id=context_data.get("user_id", "cli_user"),
            username=context_data.get("username", "cli_user"),
            email=context_data.get("email"),
            name=context_data.get("name"),
            avatar_url=context_data.get("avatar_url"),
            raw_profile=context_data,  # Store full context for policy access
        )

    # Parse parameters
    params: dict[str, Any] = {}
    for p in param:
        if "=" not in p:
            raise click.BadParameter(
                f"Parameter must be in format name=value or name=@file.json: {p}"
            )

        key, value = p.split("=", 1)

        # Handle JSON file input
        if value.startswith("@"):
            file_path = Path(value[1:])
            if not file_path.exists():
                raise click.BadParameter(f"JSON file not found: {file_path}")
            try:
                with open(file_path) as f:
                    value = json.load(f)
            except json.JSONDecodeError as e:
                raise click.BadParameter(f"Invalid JSON in file {file_path}: {e}") from e

        params[key] = value

    # Execute endpoint using SDK executor system
    result = await execute_endpoint(
        endpoint_type,
        name,
        params,
        user_config,
        site_config,
        profile_name,
        readonly,
        skip_output_validation,
        user_context_obj,
    )

    # Output result
    if json_output:
        output_result(result, json_output, debug)
    else:
        # Add success indicator
        click.echo(f"{click.style('✅ Success!', fg='green', bold=True)}")

        # Use the table renderer for nice formatting
        format_result_for_display(result)

        # Add execution time if available in debug mode
        if debug:
            click.echo(f"\n{click.style('⏱️  Execution completed', fg='cyan')}")
