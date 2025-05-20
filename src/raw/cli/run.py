import click
import json
from typing import Dict, Any, Optional
from raw.endpoints.runner import run_endpoint as execute_endpoint
from raw.endpoints.executor import EndpointType
from raw.config.user_config import load_user_config
from raw.config.site_config import load_site_config, get_active_profile
from raw.cli.utils import output_result, output_error

@click.command(name="run")
@click.argument("endpoint_type", type=click.Choice([t.value for t in EndpointType]))
@click.argument("name")
@click.option("--param", "-p", multiple=True, help="Parameter in format name=value")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed error information")
def run_endpoint(endpoint_type: str, name: str, param: tuple[str, ...], profile: Optional[str], json_output: bool, debug: bool):
    """Run an endpoint (tool, resource, or prompt)"""
    try:
        # Load configs
        site_config = load_site_config()
        user_config = load_user_config(site_config)
        
        # Get active profile
        active_profile = get_active_profile(user_config, site_config, profile)
        
        # Parse parameters
        params: Dict[str, Any] = {}
        for p in param:
            if "=" not in p:
                error_msg = f"Parameter must be in format name=value: {p}"
                if json_output:
                    output_error(click.BadParameter(error_msg), json_output, debug)
                else:
                    raise click.BadParameter(error_msg)
            key, value = p.split("=", 1)
            params[key] = value
            
        # Execute endpoint
        result = execute_endpoint(endpoint_type, name, params, user_config, site_config, active_profile)
        
        # Output result
        output_result(result, json_output, debug)
            
    except Exception as e:
        output_error(e, json_output, debug)
