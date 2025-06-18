import signal
from typing import Any, Dict, Optional

import click
from pydantic import BaseModel

from mxcp.cli.utils import configure_logging, get_env_flag, get_env_profile, output_error
from mxcp.config.analytics import track_command_with_timing
from mxcp.config.site_config import load_site_config
from mxcp.config.user_config import load_user_config
from mxcp.server.mcp import RAWMCP


class EndpointRequest(BaseModel):
    params: Dict[str, Any] = {}


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
    "--no-sql-tools",
    is_flag=True,
    help="Disable built-in SQL querying and schema exploration tools (enabled by default in site config)",
)
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@click.option(
    "--stateless", is_flag=True, help="Enable stateless HTTP mode (for serverless deployments)"
)
@track_command_with_timing("serve")
def serve(
    profile: Optional[str],
    transport: Optional[str],
    port: Optional[int],
    debug: bool,
    no_sql_tools: bool,
    readonly: bool,
    stateless: bool,
):
    """Start the MXCP MCP server to expose endpoints via HTTP or stdio.

    This command starts a server that exposes your MXCP endpoints as an MCP-compatible
    interface. By default, it uses the transport configuration from your user config,
    but can also be overridden with command line options.

    Examples:
        mxcp serve                   # Use transport settings from user config
        mxcp serve --port 9000       # Override port from user config
        mxcp serve --transport stdio # Override transport from user config
        mxcp serve --profile dev     # Use the 'dev' profile configuration
        mxcp serve --no-sql-tools    # Disable built-in SQL querying and schema exploration tools
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

    try:
        site_config = load_site_config()
        user_config = load_user_config(site_config)

        # Get transport settings from user config, with CLI overrides
        transport_config = user_config.get("transport", {})
        final_transport = transport or transport_config.get("provider", "streamable-http")

        # Get host and port from user config if not specified via CLI
        http_config = transport_config.get("http", {})
        if port is None:
            final_port = http_config.get("port", 8000)
        else:
            final_port = port

        # Get host from user config (defaults to localhost)
        final_host = http_config.get("host", "localhost")

        # Get stateless setting from user config, with CLI override
        # CLI flag takes precedence over config setting
        config_stateless = http_config.get("stateless", False)
        final_stateless = stateless if stateless else config_stateless

        # Set up signal handler for graceful shutdown
        def signal_handler(signum, frame):
            raise KeyboardInterrupt()

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Pass None for enable_sql_tools when --no-sql-tools is not specified
        server = RAWMCP(
            user_config,
            site_config,
            profile=profile,
            host=final_host,
            port=final_port,
            enable_sql_tools=None if not no_sql_tools else False,
            readonly=readonly,
            stateless_http=final_stateless,
        )
        try:
            server.run(transport=final_transport)
        except KeyboardInterrupt:
            # Gracefully shutdown the server
            server.shutdown()
            raise
    except KeyboardInterrupt:
        # Server was stopped gracefully
        pass
    except Exception as e:
        output_error(e, json_output=False, debug=debug)
