import click
from raw.cli.list import list_endpoints
from raw.cli.run import run_endpoint
from raw.cli.validate import validate
from raw.cli.test import test
from raw.cli.serve import serve
from raw.cli.init import init
from raw.cli.query import query
from raw.cli.dbt import dbt_config, dbt_wrapper
from raw.config.analytics import initialize_analytics, track_base_command

@click.group()
def cli():
    """RAW CLI"""
    initialize_analytics()
    # Track when user runs just 'raw' without any command
    track_base_command()

cli.add_command(list_endpoints)
cli.add_command(run_endpoint)
cli.add_command(validate)
cli.add_command(test)
cli.add_command(serve)
cli.add_command(init)
cli.add_command(query)
cli.add_command(dbt_config)
cli.add_command(dbt_wrapper)
