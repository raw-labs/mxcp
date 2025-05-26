import click
import signal
from typing import Dict, Any, Optional
from pydantic import BaseModel
from mxcp.server.mcp import RAWMCP
from mxcp.cli.utils import output_error, configure_logging, get_env_flag, get_env_profile
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.config.analytics import track_event

class EndpointRequest(BaseModel):
    params: Dict[str, Any] = {}

@click.command(name="serve")
@click.option("--profile", help="Profile name to use")
@click.option("--transport", type=click.Choice(["streamable-http", "sse", "stdio"]), default="streamable-http", help="Transport protocol to use (streamable-http, sse, or stdio)")
@click.option("--port", type=int, default=8000, help="Port number to use for HTTP transport (default: 8000)")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--no-sql-tools", is_flag=True, help="Disable built-in SQL querying and schema exploration tools (enabled by default in site config)")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
def serve(profile: Optional[str], transport: str, port: int, debug: bool, no_sql_tools: bool, readonly: bool):
    """Start the MXCP MCP server to expose endpoints via HTTP or stdio.
    
    This command starts a server that exposes your MXCP endpoints as an MCP-compatible
    interface. By default, it runs an HTTP server on port 8000, but can also use stdio
    for integration with other tools.
    
    Examples:
        mxcp serve                   # Start HTTP server on default port 8000
        mxcp serve --port 9000       # Start HTTP server on port 9000
        mxcp serve --transport stdio # Use stdio transport instead of HTTP
        mxcp serve --profile dev     # Use the 'dev' profile configuration
        mxcp serve --no-sql-tools    # Disable built-in SQL querying and schema exploration tools
        mxcp serve --readonly        # Open database connection in read-only mode
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

        # Track server start
        track_event("server_started", {
            "transport": transport,
            "port": port if transport != "stdio" else None,
            "sql_tools_enabled": not no_sql_tools,
            "readonly": readonly
        })

        # Set up signal handler for graceful shutdown
        def signal_handler(signum, frame):
            track_event("server_stopped", {
                "transport": transport,
                "port": port if transport != "stdio" else None,
                "signal": signal.Signals(signum).name,
                "sql_tools_enabled": not no_sql_tools,
                "readonly": readonly
            })
            raise KeyboardInterrupt()

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Pass None for enable_sql_tools when --no-sql-tools is not specified
        server = RAWMCP(
            user_config, 
            site_config, 
            profile=profile, 
            port=port, 
            enable_sql_tools=None if not no_sql_tools else False,
            readonly=readonly
        )
        server.run(transport=transport)
    except KeyboardInterrupt:
        # Server was stopped gracefully
        pass
    except Exception as e:
        # Track server start failure
        track_event("server_start_failed", {
            "transport": transport,
            "port": port if transport != "stdio" else None,
            "error": str(e),
            "sql_tools_enabled": not no_sql_tools,
            "readonly": readonly
        })
        output_error(e, json_output=False, debug=debug)
