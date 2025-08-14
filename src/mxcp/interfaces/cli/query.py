import asyncio
import json
from pathlib import Path
from typing import Any

import click

from mxcp.interfaces.cli.table_renderer import render_table
from mxcp.interfaces.cli.utils import (
    configure_logging,
    get_env_flag,
    get_env_profile,
    output_error,
    output_result,
)
from mxcp.core.config.analytics import track_command_with_timing
from mxcp.executor.engine import create_execution_engine
from mxcp.core.config.site_config import load_site_config
from mxcp.core.config.user_config import load_user_config
from mxcp.sdk.executor import ExecutionContext


@click.command(name="query")
@click.argument("sql", required=False)
@click.option("--file", type=click.Path(exists=True), help="Path to SQL file")
@click.option(
    "--param",
    "-p",
    multiple=True,
    help="Parameter in format name=value or name=@file.json for complex values",
)
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("query")  # type: ignore[misc]
def query(
    sql: str | None,
    file: str | None,
    param: tuple[str, ...],
    profile: str | None,
    json_output: bool,
    debug: bool,
    readonly: bool,
) -> None:
    """Execute a SQL query directly against the database.

    \b
    The query can be provided either directly as an argument or from a file.
    Parameters can be provided in two ways:
    1. Simple values: --param name=value
    2. Complex values from JSON file: --param name=@file.json

    \b
    Examples:
        mxcp query "SELECT * FROM users WHERE age > 18" --param age=18
        mxcp query --file complex_query.sql --param start_date=@dates.json
        mxcp query "SELECT * FROM sales" --profile production --json-output
        mxcp query "SELECT * FROM users" --readonly
    """
    # Configure logging first
    configure_logging(debug)

    try:
        # Run async implementation
        asyncio.run(_query_async(sql, file, param, profile, json_output, debug, readonly))
    except click.ClickException:
        # Let Click exceptions propagate - they have their own formatting
        raise
    except KeyboardInterrupt:
        # Handle graceful shutdown
        if not json_output:
            click.echo("\nOperation cancelled by user", err=True)
        raise click.Abort() from None
    except Exception as e:
        # Only catch non-Click exceptions
        output_error(e, json_output, debug)


async def _query_async(
    sql: str | None,
    file: str | None,
    param: tuple[str, ...],
    profile: str | None,
    json_output: bool,
    debug: bool,
    readonly: bool,
) -> None:
    """Async implementation of the query command."""
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")

    # Validate input
    if not sql and not file:
        raise click.BadParameter("Either SQL query or --file must be provided")
    if sql and file:
        raise click.BadParameter("Cannot provide both SQL query and --file")

    # Load configs
    site_config = load_site_config()
    user_config = load_user_config(site_config)

    profile_name = profile or site_config["profile"]

    # Parse parameters
    params: dict[str, Any] = {}
    for p in param:
        if "=" not in p:
            raise click.BadParameter(
                f"Parameter must be in format name=value or name=@file.json: {p}"
            )

        key, value = p.split("=", 1)

        # Handle JSON file input
        if value.startswith("@"):
            file_path = Path(value[1:])
            if not file_path.exists():
                raise click.BadParameter(f"JSON file not found: {file_path}")
            try:
                with open(file_path) as f:
                    value = json.load(f)
            except json.JSONDecodeError as e:
                raise click.BadParameter(f"Invalid JSON in file {file_path}: {e}") from e

        params[key] = value

    # Get SQL query
    query_sql = sql
    if file:
        with open(file) as f:
            query_sql = f.read()

    # Ensure we have a query to execute
    if not query_sql:
        raise click.BadParameter("SQL query cannot be empty")

    # Show what we're executing (only in non-JSON mode)
    if not json_output:
        click.echo(f"\n{click.style('🔍 Executing Query', fg='cyan', bold=True)}")
        if file:
            click.echo(f"   • Source: {click.style(file, fg='yellow')}")

        # Show first few lines of query
        query_lines = query_sql.strip().split("\n")
        if len(query_lines) > 5:
            preview = "\n".join(query_lines[:5]) + "\n   ..."
        else:
            preview = query_sql.strip()

        click.echo(f"\n{click.style('📝 SQL:', fg='cyan')}")
        for line in preview.split("\n"):
            click.echo(f"   {line}")

        if params:
            click.echo(f"\n{click.style('📋 Parameters:', fg='cyan')}")
            for key, value in params.items():
                if isinstance(value, dict | list):
                    click.echo(f"   • ${key} = {json.dumps(value)}")
                else:
                    click.echo(f"   • ${key} = {value}")

        if readonly:
            click.echo(f"\n{click.style('🔒 Mode:', fg='yellow')} Read-only")

        click.echo(f"\n{click.style('⏳ Running...', fg='yellow')}")

    # Create execution engine with readonly configuration if specified
    engine = create_execution_engine(user_config, site_config, profile_name, readonly=readonly)

    try:
        # Create execution context
        context = ExecutionContext()

        # Execute query using SDK executor with SQL language
        result = await engine.execute(
            language="sql", source_code=query_sql, params=params, context=context
        )

        if json_output:
            output_result(result, json_output, debug)
        else:
            # Show success and format results
            click.echo(f"\n{click.style('✅ Query executed successfully!', fg='green', bold=True)}")

            if isinstance(result, list) and len(result) > 0:
                # Use shared table renderer
                render_table(result, title="Query Results")
                if len(result) > 100:
                    click.echo(
                        f"{click.style('💡 Tip:', fg='yellow')} Use {click.style('--json-output', fg='cyan')} to export all results"
                    )

            elif isinstance(result, list) and len(result) == 0:
                click.echo(f"\n{click.style('ℹ️  No results returned', fg='blue')}")
            else:
                # Single value or other format
                click.echo(f"\n{click.style('📊 Result:', fg='cyan', bold=True)}")
                click.echo(json.dumps(result, indent=2))

            click.echo()  # Empty line at end

    finally:
        engine.shutdown()
