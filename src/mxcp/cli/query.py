import click
import json
from typing import Dict, Any, Optional
from pathlib import Path
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.cli.utils import output_result, output_error, configure_logging, get_env_flag, get_env_profile
from mxcp.cli.table_renderer import render_table
from mxcp.engine.duckdb_session import DuckDBSession
from mxcp.config.analytics import track_command_with_timing

@click.command(name="query")
@click.argument("sql", required=False)
@click.option("--file", type=click.Path(exists=True), help="Path to SQL file")
@click.option("--param", "-p", multiple=True, help="Parameter in format name=value or name=@file.json for complex values")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("query")
def query(sql: Optional[str], file: Optional[str], param: tuple[str, ...], profile: Optional[str], json_output: bool, debug: bool, readonly: bool):
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
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")
        
    # Configure logging
    configure_logging(debug)

    try:
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
        params: Dict[str, Any] = {}
        for p in param:
            if "=" not in p:
                error_msg = f"Parameter must be in format name=value or name=@file.json: {p}"
                if json_output:
                    output_error(click.BadParameter(error_msg), json_output, debug)
                else:
                    raise click.BadParameter(error_msg)
                    
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
                    raise click.BadParameter(f"Invalid JSON in file {file_path}: {e}")
            
            params[key] = value

        # Get SQL query
        query_sql = sql
        if file:
            with open(file) as f:
                query_sql = f.read()

        # Show what we're executing (only in non-JSON mode)
        if not json_output:
            click.echo(f"\n{click.style('🔍 Executing Query', fg='cyan', bold=True)}")
            if file:
                click.echo(f"   • Source: {click.style(file, fg='yellow')}")
            
            # Show first few lines of query
            query_lines = query_sql.strip().split('\n')
            if len(query_lines) > 5:
                preview = '\n'.join(query_lines[:5]) + '\n   ...'
            else:
                preview = query_sql.strip()
            
            click.echo(f"\n{click.style('📝 SQL:', fg='cyan')}")
            for line in preview.split('\n'):
                click.echo(f"   {line}")
                
            if params:
                click.echo(f"\n{click.style('📋 Parameters:', fg='cyan')}")
                for key, value in params.items():
                    if isinstance(value, (dict, list)):
                        click.echo(f"   • ${key} = {json.dumps(value)}")
                    else:
                        click.echo(f"   • ${key} = {value}")
                        
            if readonly:
                click.echo(f"\n{click.style('🔒 Mode:', fg='yellow')} Read-only")
            
            click.echo(f"\n{click.style('⏳ Running...', fg='yellow')}")

        # Execute query
        session = DuckDBSession(user_config, site_config, readonly=readonly)
        try:
            # Execute query and convert to DataFrame to preserve column names
            result = session.execute_query_to_dict(query_sql, params)
            
            if json_output:
                output_result(result, json_output, debug)
            else:
                # Show success and format results
                click.echo(f"\n{click.style('✅ Query executed successfully!', fg='green', bold=True)}")
                
                if isinstance(result, list) and len(result) > 0:
                    # Use shared table renderer
                    render_table(result, title="Query Results")
                    if len(result) > 100:
                        click.echo(f"{click.style('💡 Tip:', fg='yellow')} Use {click.style('--json-output', fg='cyan')} to export all results")
                        
                elif isinstance(result, list) and len(result) == 0:
                    click.echo(f"\n{click.style('ℹ️  No results returned', fg='blue')}")
                else:
                    # Single value or other format
                    click.echo(f"\n{click.style('📊 Result:', fg='cyan', bold=True)}")
                    click.echo(json.dumps(result, indent=2))
                    
                click.echo()  # Empty line at end
                
        finally:
            session.close()
            
    except Exception as e:
        if json_output:
            output_error(e, json_output, debug)
        else:
            click.echo(f"\n{click.style('❌ Query failed:', fg='red', bold=True)} {str(e)}")
            if debug:
                import traceback
                click.echo(f"\n{click.style('🔍 Stack trace:', fg='yellow')}")
                click.echo(traceback.format_exc())
            click.get_current_context().exit(1) 
