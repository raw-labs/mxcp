
import click
from raw.cli.list import list_endpoints
from raw.cli.run import run_endpoint

@click.group()
def cli():
    """RAW CLI"""
    pass

cli.add_command(list_endpoints)
cli.add_command(run_endpoint)
