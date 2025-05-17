import click
from raw.config.site_config import load_site_config
from raw.config.user_config import load_user_config
from raw.engine.duckdb_session import start_session
from raw.server.server import run_server

@click.command(name="serve")
@click.option("--profile", default=None)
def serve(profile):
    """Start the local HTTP server"""
    config = load_site_config()
    user = load_user_config()
    session = start_session(config, user, profile)
    run_server(session)