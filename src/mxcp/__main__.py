import click

from mxcp.core.config.analytics import initialize_analytics, track_base_command
from mxcp.interfaces.cli.dbt import dbt_config, dbt_wrapper
from mxcp.interfaces.cli.drift_check import drift_check
from mxcp.interfaces.cli.drift_snapshot import drift_snapshot
from mxcp.interfaces.cli.evals import evals
from mxcp.interfaces.cli.init import init
from mxcp.interfaces.cli.lint import lint
from mxcp.interfaces.cli.list import list_endpoints
from mxcp.interfaces.cli.log import log
from mxcp.interfaces.cli.log_cleanup import log_cleanup
from mxcp.interfaces.cli.query import query
from mxcp.interfaces.cli.run import run_endpoint
from mxcp.interfaces.cli.serve import serve
from mxcp.interfaces.cli.test import test
from mxcp.interfaces.cli.validate import validate


@click.group()
def cli() -> None:
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
cli.add_command(log_cleanup)
