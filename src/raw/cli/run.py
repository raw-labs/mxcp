import click
import json
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from raw.endpoints.runner import run_endpoint as execute_endpoint
from raw.endpoints.executor import EndpointType
from raw.config.user_config import load_user_config
from raw.config.site_config import load_site_config, get_active_profile
from raw.cli.utils import output_result, output_error, configure_logging
from raw.config.analytics import track_command_with_timing

@click.command(name="run")
@click.argument("endpoint_type", type=click.Choice([t.value for t in EndpointType]))
@click.argument("name")
@click.option("--param", "-p", multiple=True, help="Parameter in format name=value or name=@file.json for complex values")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--skip-output-validation", is_flag=True, help="Skip output validation against the return type definition")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("run")
def run_endpoint(endpoint_type: str, name: str, param: tuple[str, ...], profile: Optional[str], json_output: bool, debug: bool, skip_output_validation: bool, readonly: bool):
    """Run an endpoint (tool, resource, or prompt).
    
    Parameters can be provided in two ways:
    1. Simple values: --param name=value
    2. Complex values from JSON file: --param name=@file.json
    
    Examples:
        raw run tool my_tool --param name=value
        raw run tool my_tool --param complex=@data.json
        raw run tool my_tool --readonly
    """
    # Configure logging
    configure_logging(debug)

    try:
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
            
        # Execute endpoint
        result = asyncio.run(execute_endpoint(endpoint_type, name, params, user_config, site_config, profile_name, validate_output=not skip_output_validation, readonly=readonly))
        
        # Output result
        output_result(result, json_output, debug)
            
    except Exception as e:
        output_error(e, json_output, debug)
