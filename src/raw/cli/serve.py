import click
import asyncio
from typing import Dict, Any, Optional
from pydantic import BaseModel
from raw.server.mcp import RAWMCP
from raw.cli.utils import output_error
from raw.config.user_config import load_user_config
from raw.config.site_config import load_site_config

class EndpointRequest(BaseModel):
    params: Dict[str, Any] = {}

@click.command(name="serve")
@click.option("--profile", help="Profile name to use for configuration")
@click.option("--transport", type=click.Choice(["http", "stdio"]), default="http", help="Transport protocol to use (http or stdio)")
@click.option("--port", type=int, default=8000, help="Port number to use for HTTP transport (default: 8000)")
@click.option("--debug", is_flag=True, help="Show detailed error information")
def serve(profile: Optional[str], transport: str, port: int, debug: bool):
    """Start the RAW MCP server to expose endpoints via HTTP or stdio.
    
    This command starts a server that exposes your RAW endpoints as an MCP-compatible
    interface. By default, it runs an HTTP server on port 8000, but can also use stdio
    for integration with other tools.
    
    Examples:
        raw serve                    # Start HTTP server on default port 8000
        raw serve --port 9000       # Start HTTP server on port 9000
        raw serve --transport stdio # Use stdio transport instead of HTTP
        raw serve --profile dev     # Use the 'dev' profile configuration
    """
    try:
        user_config = load_user_config()
        site_config = load_site_config()

        # Create and run MCP server
        server = RAWMCP(user_config, site_config, profile=profile)
        asyncio.run(server.run(transport=transport, port=port))
    except Exception as e:
        output_error(e, json_output=False, debug=debug)