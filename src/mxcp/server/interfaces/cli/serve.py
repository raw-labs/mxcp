import signal
from pathlib import Path
from typing import Any

import click

from mxcp.server.core.config.analytics import track_command_with_timing
from mxcp.server.interfaces.cli.utils import (
    configure_logging,
    get_env_flag,
    get_env_profile,
    output_error,
)
from mxcp.server.interfaces.server.mcp import RAWMCP


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
@track_command_with_timing("serve")  # type: ignore[misc]
def serve(
    profile: str | None,
    transport: str | None,
    port: int | None,
    debug: bool,
    sql_tools: str | None,
    readonly: bool,
    stateless: bool,
) -> None:
    """Start the MXCP MCP server to expose endpoints via HTTP or stdio.

    This command starts a server that exposes your MXCP endpoints as an MCP-compatible
    interface. By default, it uses the transport configuration from your user config,
    but can also be overridden with command line options.

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
    """
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")

    # Configure logging
    configure_logging(debug)

    # Convert sql-tools string to boolean
    enable_sql_tools = None
    if sql_tools == "true":
        enable_sql_tools = True
    elif sql_tools == "false":
        enable_sql_tools = False

    try:
        # Create the server - it loads all configs and sets itself up
        server = RAWMCP(
            site_config_path=Path.cwd(),
            profile=profile,
            transport=transport,
            port=port,
            stateless_http=stateless if stateless else None,
            enable_sql_tools=enable_sql_tools,
            readonly=readonly,
            debug=debug,
        )

        # Get config info for display
        config = server.get_config_info()
        endpoint_counts = server.get_endpoint_counts()

        # Show startup banner (except for stdio mode which needs clean output)
        if config["transport"] != "stdio":
            click.echo("\n" + "=" * 60)
            click.echo(click.style("🚀 MXCP Server Starting", fg="green", bold=True).center(70))
            click.echo("=" * 60 + "\n")

            # Show configuration
            click.echo(f"{click.style('📋 Configuration:', fg='cyan', bold=True)}")
            click.echo(f"   • Project: {click.style(config['project'], fg='yellow')}")
            click.echo(f"   • Profile: {click.style(config['profile'], fg='yellow')}")
            click.echo(f"   • Transport: {click.style(config['transport'], fg='yellow')}")

            if config["transport"] in ["streamable-http", "sse"]:
                click.echo(f"   • Host: {click.style(config['host'], fg='yellow')}")
                click.echo(f"   • Port: {click.style(str(config['port']), fg='yellow')}")

            if config["readonly"]:
                click.echo(f"   • Mode: {click.style('Read-only', fg='red')}")
            else:
                click.echo(f"   • Mode: {click.style('Read-write', fg='green')}")

            if config["stateless"]:
                click.echo(f"   • HTTP Mode: {click.style('Stateless', fg='magenta')}")

            if config["sql_tools_enabled"]:
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

            click.echo("\n" + "-" * 60)

            if config["transport"] in ["streamable-http", "sse"]:
                click.echo(f"\n{click.style('✅ Server ready!', fg='green', bold=True)}")
                url = f"http://{config['host']}:{config['port']}"
                click.echo(f"   Listening on {click.style(url, fg='cyan', underline=True)}")
                click.echo(f"\n{click.style('Press Ctrl+C to stop', fg='yellow')}\n")
            else:
                click.echo(f"\n{click.style('✅ Server starting...', fg='green', bold=True)}\n")

        # Set up signal handler for graceful shutdown
        def signal_handler(signum: int, frame: Any) -> None:
            if config["transport"] != "stdio":
                click.echo(f"\n{click.style('🛑 Shutting down gracefully...', fg='yellow')}")
            raise KeyboardInterrupt()

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            # Start the server
            server.run(transport=config["transport"])
        except KeyboardInterrupt:
            # Gracefully shutdown the server
            server.shutdown()
            if config["transport"] != "stdio":
                click.echo(f"{click.style('👋 Server stopped', fg='cyan')}")
            raise
    except KeyboardInterrupt:
        # Server was stopped gracefully
        pass
    except Exception as e:
        output_error(e, json_output=False, debug=debug)
