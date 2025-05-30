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
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("lsp")
def lsp(profile: Optional[str], port: Optional[int], debug: bool, readonly: bool):
    """Start the MXCP LSP server for language server features.
    
    This command starts an LSP (Language Server Protocol) server that provides
    language features like code completion, hover information, and go-to-definition
    for MXCP endpoints and SQL queries. The server integrates with your DuckDB
    database to provide context-aware suggestions.
    
    Examples:
        mxcp lsp                     # Start LSP server on default port 3000
        mxcp lsp --port 4000         # Start LSP server on port 4000
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
        
        # Run the server synchronously
        server.start()
        
    except KeyboardInterrupt:
        # Server was stopped gracefully
        click.echo("\nLSP server stopped")
    except Exception as e:
        output_error(e, json_output=False, debug=debug) 