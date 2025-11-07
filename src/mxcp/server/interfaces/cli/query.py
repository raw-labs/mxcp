import asyncio
import json
from pathlib import Path
from typing import Any

import click

from mxcp.sdk.executor import ExecutionContext
from mxcp.server.core.config.analytics import track_command_with_timing
from mxcp.server.core.config.site_config import find_repo_root, load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.executor.engine import create_runtime_environment
from mxcp.server.interfaces.cli.table_renderer import render_table
from mxcp.server.interfaces.cli.utils import (
    configure_logging_from_config,
    get_env_flag,
    output_error,
    output_result,
    resolve_profile,
)


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
    try:
        # Load site config
        try:
            repo_root = find_repo_root()
        except FileNotFoundError as e:
            click.echo(
                f"\n{click.style('❌ Error:', fg='red', bold=True)} "
                "No mxcp-site.yml found in current directory or parents"
            )
            raise click.ClickException(
                "No mxcp-site.yml found in current directory or parents"
            ) from e

        site_config = load_site_config(repo_root)

        # Resolve profile
        active_profile = resolve_profile(profile, site_config)

        # Load user config with active profile
        user_config = load_user_config(site_config, active_profile=active_profile)

        # Configure logging
        configure_logging_from_config(
            site_config=site_config,
            user_config=user_config,
            debug=debug,
        )

        # Run async implementation
        asyncio.run(_query_async(sql, file, param, active_profile, json_output, debug, readonly))
    except click.ClickException:
        # Let Click exceptions propagate - they have their own formatting
        raise
    except KeyboardInterrupt:
        # Handle graceful shutdown
        if not json_output:
            click.echo("\nOperation cancelled by user", err=True)
        raise click.Abort() from None
    except Exception as e:
        output_error(e, json_output, debug)


async def _query_async(
    sql: str | None,
    file: str | None,
    param: tuple[str, ...],
    profile: str,
    json_output: bool,
    debug: bool,
    readonly: bool,
) -> None:
    """Async implementation of the query command."""
    # Get readonly flag from environment if not set
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

    # Create runtime environment with readonly configuration if specified
    runtime_env = create_runtime_environment(
        user_config, site_config, profile, readonly=readonly
    )
    engine = runtime_env.execution_engine

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
        runtime_env.shutdown()
