import json

import click

from mxcp.sdk.core.analytics import track_command_with_timing
from mxcp.server.core.config.site_config import find_repo_root, load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.interfaces.cli.utils import (
    configure_logging_from_config,
    get_env_flag,
    output_error,
    resolve_profile,
    run_async_cli,
)
from mxcp.server.interfaces.server.mcp import RAWMCP
from mxcp.server.services.endpoints.models import EndpointErrorModel


def _format_endpoint_errors(skipped_endpoints: list[EndpointErrorModel]) -> str:
    """Format endpoint errors for human-readable display.

    Args:
        skipped_endpoints: List of EndpointErrorModel instances

    Returns:
        Formatted string for terminal display
    """
    output = []
    output.append(f"\n{click.style('❌ Server startup failed!', fg='red', bold=True)}")
    output.append(
        f"   Found {click.style(str(len(skipped_endpoints)), fg='red')} endpoint(s) with errors\n"
    )

    output.append(f"{click.style('Failed endpoints:', fg='red', bold=True)}")

    sorted_endpoints = sorted(skipped_endpoints, key=lambda x: x.path)
    for i, skipped in enumerate(sorted_endpoints):
        output.append(f"  {click.style('✗', fg='red')} {skipped.path}")
        error_msg = skipped.error
        if error_msg:
            lines = error_msg.split("\n")
            first_line = lines[0]
            output.append(f"    {click.style('Error:', fg='red')} {first_line}")
            for line in lines[1:]:
                if line.strip():
                    output.append(f"    {line}")
        if i < len(sorted_endpoints) - 1:
            output.append("")

    output.append(
        f"\n{click.style('💡 Tip:', fg='yellow')} "
        "Fix validation errors or use --ignore-errors to start anyway"
    )
    output.append("")

    return "\n".join(output)


def _format_endpoint_errors_json(skipped_endpoints: list[EndpointErrorModel]) -> str:
    """Format endpoint errors for JSON output.

    Args:
        skipped_endpoints: List of EndpointErrorModel instances

    Returns:
        JSON string with error information
    """
    return json.dumps(
        {
            "status": "error",
            "message": f"Found {len(skipped_endpoints)} endpoint(s) with errors",
            "failed_endpoints": [e.model_dump() for e in skipped_endpoints],
        },
        indent=2,
    )


@click.command(name="serve")
@click.option("--profile", help="Profile name to use")
@click.option(
    "--transport",
    type=click.Choice(["streamable-http", "sse", "stdio"]),
    help="Transport protocol to use (defaults to user config setting)",
)
@click.option(
    "--port",
    type=int,
    help="Port number to use for HTTP transport (defaults to user config setting)",
)
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option(
    "--sql-tools",
    type=click.Choice(["true", "false"]),
    help="Enable or disable built-in SQL querying and schema exploration tools",
)
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@click.option(
    "--stateless", is_flag=True, help="Enable stateless HTTP mode (for serverless deployments)"
)
@click.option(
    "--ignore-errors",
    is_flag=True,
    help="Start server even if some endpoints have validation errors",
)
@click.option(
    "--json-output",
    is_flag=True,
    help="Output startup errors in JSON format (only used when startup fails)",
)
@track_command_with_timing("serve")  # type: ignore[misc]
def serve(
    profile: str | None,
    transport: str | None,
    port: int | None,
    debug: bool,
    sql_tools: str | None,
    readonly: bool,
    stateless: bool,
    ignore_errors: bool,
    json_output: bool,
) -> None:
    """Start the MXCP MCP server to expose endpoints via HTTP or stdio.

    This command starts a server that exposes your MXCP endpoints as an MCP-compatible
    interface. By default, it uses the transport configuration from your user config,
    but can also be overridden with command line options.

    By default, the server will fail to start if any endpoints have validation errors.
    Use --ignore-errors to start the server anyway, skipping invalid endpoints.

    \b
    Examples:
        mxcp serve                   # Use transport settings from user config
        mxcp serve --port 9000       # Override port from user config
        mxcp serve --transport stdio # Override transport from user config
        mxcp serve --profile dev     # Use the 'dev' profile configuration
        mxcp serve --sql-tools true  # Enable built-in SQL querying and schema exploration tools
        mxcp serve --sql-tools false # Disable built-in SQL querying and schema exploration tools
        mxcp serve --readonly        # Open database connection in read-only mode
        mxcp serve --stateless       # Enable stateless HTTP mode
        mxcp serve --ignore-errors   # Start even if some endpoints have errors
    """
    # Get readonly flag from environment if not set by flag
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")

    # Convert sql-tools string to boolean
    enable_sql_tools = None
    if sql_tools == "true":
        enable_sql_tools = True
    elif sql_tools == "false":
        enable_sql_tools = False

    try:
        # Load site config
        try:
            repo_root = find_repo_root()
        except FileNotFoundError as e:
            click.echo(
                f"\n{click.style('❌ Error:', fg='red', bold=True)} "
                "No mxcp-site.yml found in current directory or parents"
            )
            raise click.ClickException(
                "No mxcp-site.yml found in current directory or parents"
            ) from e

        site_config = load_site_config(repo_root)

        # Resolve profile
        active_profile = resolve_profile(profile, site_config)

        # Load user config with active profile
        user_config = load_user_config(site_config, active_profile=active_profile)

        # Determine effective transport (CLI flag > user config > default)
        effective_transport = transport or user_config.transport.provider or "streamable-http"

        # Configure logging ONCE with all settings
        configure_logging_from_config(
            user_config=user_config,
            debug=debug,
            transport=effective_transport,
        )

        # Create the server
        server = RAWMCP(
            site_config_path=repo_root,
            profile=active_profile,
            transport=transport,
            port=port,
            stateless_http=stateless if stateless else None,
            enable_sql_tools=enable_sql_tools,
            readonly=readonly,
            debug=debug,
        )

        # Check for endpoint loading errors (YAML parsing, schema errors)
        all_errors = list(server.skipped_endpoints)

        # Also validate endpoints (SQL syntax, etc.)
        validation_errors = server.validate_all_endpoints()
        all_errors.extend(validation_errors)

        # Fail startup if there are any endpoint errors (unless --ignore-errors)
        if all_errors and not ignore_errors:
            if json_output:
                click.echo(_format_endpoint_errors_json(all_errors))
            else:
                click.echo(_format_endpoint_errors(all_errors))
            raise click.Abort()

        # If ignoring errors, add validation errors to skipped list for tracking
        # and remove failed endpoints from the valid list
        if validation_errors:
            server.skipped_endpoints.extend(validation_errors)
            failed_paths = {e.path for e in validation_errors}
            server.endpoints = [
                (path, endpoint)
                for path, endpoint in server.endpoints
                if str(path) not in failed_paths
            ]

        # Get endpoint counts for display
        endpoint_counts = server.get_endpoint_counts()

        # Show startup banner (except for stdio mode which needs clean output)
        if server.transport != "stdio":
            click.echo("\n" + "=" * 60)
            click.echo(click.style("🚀 MXCP Server Starting", fg="green", bold=True).center(70))
            click.echo("=" * 60 + "\n")

            # Show configuration
            click.echo(f"{click.style('📋 Configuration:', fg='cyan', bold=True)}")
            click.echo(f"   • Project: {click.style(server.site_config.project, fg='yellow')}")
            click.echo(f"   • Profile: {click.style(server.profile_name, fg='yellow')}")
            click.echo(f"   • Transport: {click.style(server.transport, fg='yellow')}")

            if server.transport in ["streamable-http", "sse"]:
                click.echo(f"   • Host: {click.style(server.host, fg='yellow')}")
                click.echo(f"   • Port: {click.style(str(server.port), fg='yellow')}")

            if server.readonly:
                click.echo(f"   • Mode: {click.style('Read-only', fg='red')}")
            else:
                click.echo(f"   • Mode: {click.style('Read-write', fg='green')}")

            if server.stateless_http:
                click.echo(f"   • HTTP Mode: {click.style('Stateless', fg='magenta')}")

            if server.enable_sql_tools:
                click.echo(f"   • SQL Tools: {click.style('Enabled', fg='green')}")
            else:
                click.echo(f"   • SQL Tools: {click.style('Disabled', fg='red')}")

            # Show endpoint counts
            click.echo(f"\n{click.style('📊 Endpoints:', fg='cyan', bold=True)}")
            if endpoint_counts["tools"] > 0:
                click.echo(f"   • Tools: {click.style(str(endpoint_counts['tools']), fg='green')}")
            if endpoint_counts["resources"] > 0:
                click.echo(
                    f"   • Resources: {click.style(str(endpoint_counts['resources']), fg='green')}"
                )
            if endpoint_counts["prompts"] > 0:
                click.echo(
                    f"   • Prompts: {click.style(str(endpoint_counts['prompts']), fg='green')}"
                )

            if endpoint_counts["total"] == 0:
                click.echo(f"   {click.style('⚠️  No endpoints found!', fg='yellow')}")
                click.echo(
                    "   Create tools in the 'tools/' directory, resources in 'resources/', etc."
                )

            # Show warning if there are skipped endpoints (when using --ignore-errors)
            if server.skipped_endpoints:
                click.echo(
                    f"\n{click.style('⚠️  Skipped endpoints:', fg='yellow', bold=True)} "
                    f"{click.style(str(len(server.skipped_endpoints)), fg='yellow')}"
                )
                click.echo("   Use 'mxcp validate' to see details")

            click.echo("\n" + "-" * 60)

            if server.transport in ["streamable-http", "sse"]:
                click.echo(f"\n{click.style('✅ Server ready!', fg='green', bold=True)}")
                url = f"http://{server.host}:{server.port}"
                click.echo(f"   Listening on {click.style(url, fg='cyan', underline=True)}")
                click.echo(f"\n{click.style('Press Ctrl+C to stop', fg='yellow')}\n")
            else:
                click.echo(f"\n{click.style('✅ Server starting...', fg='green', bold=True)}\n")

        async def _run_server_lifecycle() -> None:
            """Run the MCP server and ensure shutdown happens in the same event loop."""
            try:
                await server.run(transport=server.transport)
            finally:
                await server.shutdown()

        try:
            # Start the server and ensure shutdown runs inside the same event loop
            run_async_cli(_run_server_lifecycle())
        finally:
            if server.transport != "stdio":
                click.echo(f"{click.style('👋 Server stopped', fg='cyan')}")
    except click.ClickException:
        # Let Click exceptions propagate - they have their own formatting
        raise
    except KeyboardInterrupt:
        # Server was stopped gracefully
        pass
    except Exception as e:
        output_error(e, json_output=False, debug=debug)
