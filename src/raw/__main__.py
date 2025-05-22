import click
from raw.cli.list import list_endpoints
from raw.cli.run import run_endpoint
from raw.cli.validate import validate
from raw.cli.test import test
from raw.cli.serve import serve
from raw.cli.init import init
from raw.cli.query import query
from raw.config.analytics import initialize_analytics

@click.group()
def cli():
    """RAW CLI"""
    initialize_analytics()

cli.add_command(list_endpoints)
cli.add_command(run_endpoint)
cli.add_command(validate)
cli.add_command(test)
cli.add_command(serve)
cli.add_command(init)
cli.add_command(query)
