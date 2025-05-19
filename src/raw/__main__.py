import click
from raw.cli.list import list_endpoints
from raw.cli.run import run_endpoint
from raw.cli.validate import validate
from raw.cli.test import test
from raw.cli.serve import serve

@click.group()
def cli():
    """RAW CLI"""
    pass

cli.add_command(list_endpoints)
cli.add_command(run_endpoint)
cli.add_command(validate)
cli.add_command(test)
cli.add_command(serve)
