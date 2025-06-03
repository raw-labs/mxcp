import click
import signal
from typing import Optional
from mxcp.lsp.server import MXCPLSPServer
from mxcp.cli.utils import output_error, configure_logging, get_env_flag, get_env_profile
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.config.analytics import track_command_with_timing


@click.command(name="lsp")
@click.option("--profile", help="Profile name to use")
@click.option("--port", type=int, help="Port number for LSP server (defaults to 3000)")
@click.option("--host", default="localhost", help="Host to bind to when using TCP mode (defaults to localhost)")
@click.option("--tcp", is_flag=True, help="Use TCP instead of stdio for LSP communication")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("lsp")
def lsp(profile: Optional[str], port: Optional[int], host: str, tcp: bool, debug: bool, readonly: bool):
    """Start the MXCP LSP server for language server features.
    
    This command starts an LSP (Language Server Protocol) server that provides
    language features like code completion, hover information, and go-to-definition
    for MXCP endpoints and SQL queries. The server integrates with your DuckDB
    database to provide context-aware suggestions.
    
    By default, the server uses stdio for communication (suitable for IDE integration).
    Use --tcp flag for testing or when stdio communication is not suitable.
    
    Examples:
        mxcp lsp                     # Start LSP server using stdio
        mxcp lsp --tcp               # Start LSP server using TCP on localhost:3000
        mxcp lsp --tcp --port 4000   # Start LSP server using TCP on localhost:4000
        mxcp lsp --tcp --host 0.0.0.0 --port 4000  # Bind to all interfaces
        mxcp lsp --profile dev       # Use the 'dev' profile configuration
        mxcp lsp --readonly          # Open database connection in read-only mode
        mxcp lsp --debug             # Start with detailed debug logging
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

        # Get port with default fallback
        final_port = port or 3000
        
        # Set up signal handler for graceful shutdown
        def signal_handler(signum, frame):
            raise KeyboardInterrupt()

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Create and start the LSP server
        server = MXCPLSPServer(
            user_config=user_config,
            site_config=site_config,
            profile=profile,
            readonly=readonly,
            port=final_port
        )
        
        # Run the server (TCP or stdio mode)
        if tcp:
            click.echo(f"Starting MXCP LSP server on {host}:{final_port}")
            server.start(host=host, use_tcp=True)
        else:
            server.start(host=host, use_tcp=False)
        
    except KeyboardInterrupt:
        # Server was stopped gracefully
        click.echo("\nLSP server stopped")
    except Exception as e:
        output_error(e, json_output=False, debug=debug) 