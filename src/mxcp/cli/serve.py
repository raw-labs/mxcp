import click
import signal
from typing import Dict, Any, Optional
from pydantic import BaseModel
from mxcp.server.mcp import RAWMCP
from mxcp.cli.utils import output_error, configure_logging, get_env_flag, get_env_profile
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.config.analytics import track_command_with_timing

class EndpointRequest(BaseModel):
    params: Dict[str, Any] = {}

@click.command(name="serve")
@click.option("--profile", help="Profile name to use")
@click.option("--transport", type=click.Choice(["streamable-http", "sse", "stdio"]), help="Transport protocol to use (defaults to user config setting)")
@click.option("--port", type=int, help="Port number to use for HTTP transport (defaults to user config setting)")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--sql-tools", type=click.Choice(['true', 'false']), help="Enable or disable built-in SQL querying and schema exploration tools")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@click.option("--stateless", is_flag=True, help="Enable stateless HTTP mode (for serverless deployments)")
@track_command_with_timing("serve")
def serve(profile: Optional[str], transport: Optional[str], port: Optional[int], debug: bool, sql_tools: Optional[str], readonly: bool, stateless: bool):
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

        # Determine SQL tools setting for server
        if sql_tools == 'true':
            enable_sql_tools_param = True
        elif sql_tools == 'false':
            enable_sql_tools_param = False
        else:
            enable_sql_tools_param = None  # Use site config default

        # For display purposes, calculate what will actually be used
        site_sql_tools_enabled = site_config.get("sql_tools", {}).get("enabled", False)
        final_sql_tools_enabled = (
            enable_sql_tools_param if enable_sql_tools_param is not None 
            else site_sql_tools_enabled
        )

        # Show startup banner (except for stdio mode which needs clean output)
        if final_transport != "stdio":
            click.echo("\n" + "="*60)
            click.echo(click.style("🚀 MXCP Server Starting", fg='green', bold=True).center(70))
            click.echo("="*60 + "\n")
            
            # Show configuration
            click.echo(f"{click.style('📋 Configuration:', fg='cyan', bold=True)}")
            click.echo(f"   • Project: {click.style(site_config['project'], fg='yellow')}")
            click.echo(f"   • Profile: {click.style(profile or site_config['profile'], fg='yellow')}")
            click.echo(f"   • Transport: {click.style(final_transport, fg='yellow')}")
            
            if final_transport in ["streamable-http", "sse"]:
                click.echo(f"   • Host: {click.style(final_host, fg='yellow')}")
                click.echo(f"   • Port: {click.style(str(final_port), fg='yellow')}")
                
            if readonly:
                click.echo(f"   • Mode: {click.style('Read-only', fg='red')}")
            else:
                click.echo(f"   • Mode: {click.style('Read-write', fg='green')}")
                
            if final_stateless:
                click.echo(f"   • HTTP Mode: {click.style('Stateless', fg='magenta')}")
                
            if final_sql_tools_enabled:
                click.echo(f"   • SQL Tools: {click.style('Enabled', fg='green')}")
            else:
                click.echo(f"   • SQL Tools: {click.style('Disabled', fg='red')}")
            
            # Count endpoints
            from mxcp.endpoints.loader import EndpointLoader
            loader = EndpointLoader(site_config)
            endpoints = loader.discover_endpoints()
            valid_endpoints = [e for e in endpoints if e[2] is None]
            tool_count = sum(1 for e in valid_endpoints if "tool" in e[1])
            resource_count = sum(1 for e in valid_endpoints if "resource" in e[1])
            prompt_count = sum(1 for e in valid_endpoints if "prompt" in e[1])
            
            click.echo(f"\n{click.style('📊 Endpoints:', fg='cyan', bold=True)}")
            if tool_count > 0:
                click.echo(f"   • Tools: {click.style(str(tool_count), fg='green')}")
            if resource_count > 0:
                click.echo(f"   • Resources: {click.style(str(resource_count), fg='green')}")
            if prompt_count > 0:
                click.echo(f"   • Prompts: {click.style(str(prompt_count), fg='green')}")
            
            if not valid_endpoints:
                click.echo(f"   {click.style('⚠️  No endpoints found!', fg='yellow')}")
                click.echo(f"   Create tools in the 'tools/' directory, resources in 'resources/', etc.")
            
            click.echo("\n" + "-"*60)
            
            if final_transport in ["streamable-http", "sse"]:
                click.echo(f"\n{click.style('✅ Server ready!', fg='green', bold=True)}")
                click.echo(f"   Listening on {click.style(f'http://{final_host}:{final_port}', fg='cyan', underline=True)}")
                click.echo(f"\n{click.style('Press Ctrl+C to stop', fg='yellow')}\n")
            else:
                click.echo(f"\n{click.style('✅ Server starting...', fg='green', bold=True)}\n")

        # Set up signal handler for graceful shutdown
        def signal_handler(signum, frame):
            if final_transport != "stdio":
                click.echo(f"\n{click.style('🛑 Shutting down gracefully...', fg='yellow')}")
            raise KeyboardInterrupt()

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Pass the determined sql_tools value to the server
        server = RAWMCP(
            user_config, 
            site_config, 
            profile=profile, 
            host=final_host,
            port=final_port, 
            enable_sql_tools=enable_sql_tools_param,
            readonly=readonly,
            stateless_http=final_stateless
        )
        try:
            server.run(transport=final_transport)
        except KeyboardInterrupt:
            # Gracefully shutdown the server
            server.shutdown()
            if final_transport != "stdio":
                click.echo(f"{click.style('👋 Server stopped', fg='cyan')}")
            raise
    except KeyboardInterrupt:
        # Server was stopped gracefully
        pass
    except Exception as e:
        output_error(e, json_output=False, debug=debug)
