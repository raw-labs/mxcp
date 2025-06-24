import click
from mxcp.cli.list import list_endpoints
from mxcp.cli.run import run_endpoint
from mxcp.cli.validate import validate
from mxcp.cli.test import test
from mxcp.cli.serve import serve
from mxcp.cli.init import init
from mxcp.cli.query import query
from mxcp.cli.dbt import dbt_config, dbt_wrapper
from mxcp.config.analytics import initialize_analytics, track_base_command
from mxcp.cli.drift_snapshot import drift_snapshot
from mxcp.cli.drift_check import drift_check
from mxcp.cli.log import log
from mxcp.cli.lint import lint
from mxcp.cli.evals import evals
from mxcp.cli.agent_help import agent_help

@click.group()
def cli():
    """MXCP CLI"""
    initialize_analytics()
    # Track when user runs just 'mxcp' without any command
    track_base_command()

cli.add_command(list_endpoints)
cli.add_command(run_endpoint)
cli.add_command(validate)
cli.add_command(test)
cli.add_command(lint)
cli.add_command(evals)
cli.add_command(serve)
cli.add_command(init)
cli.add_command(query)
cli.add_command(dbt_config)
cli.add_command(dbt_wrapper)
cli.add_command(drift_snapshot)
cli.add_command(drift_check)
cli.add_command(log)
cli.add_command(agent_help)
