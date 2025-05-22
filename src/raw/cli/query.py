import click
import json
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from raw.config.user_config import load_user_config
from raw.config.site_config import load_site_config
from raw.cli.utils import output_result, output_error
from raw.engine.duckdb_session import DuckDBSession
from raw.config.analytics import track_command_with_timing

@click.command(name="query")
@click.argument("sql", required=False)
@click.option("--file", type=click.Path(exists=True), help="Path to SQL file")
@click.option("--param", "-p", multiple=True, help="Parameter in format name=value or name=@file.json for complex values")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed error information")
@track_command_with_timing("query")
def query(sql: Optional[str], file: Optional[str], param: tuple[str, ...], profile: Optional[str], json_output: bool, debug: bool):
    """Execute a SQL query directly against the database.
    
    The query can be provided either directly as an argument or from a file.
    Parameters can be provided in two ways:
    1. Simple values: --param name=value
    2. Complex values from JSON file: --param name=@file.json
    
    Examples:
        raw query "SELECT * FROM users WHERE age > 18" --param age=18
        raw query --file complex_query.sql --param start_date=@dates.json
        raw query "SELECT * FROM sales" --profile production --json-output
    """
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

        # Execute query
        session = DuckDBSession(user_config, site_config)
        conn = session.connect()
        try:
            # Execute query and convert to DataFrame to preserve column names
            result = conn.execute(query_sql, params).fetchdf().to_dict("records")
            output_result(result, json_output, debug)
        finally:
            session.close()
            
    except Exception as e:
        output_error(e, json_output, debug) 