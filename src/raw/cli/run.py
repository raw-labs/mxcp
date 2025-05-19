import click
from typing import Dict, Any, Optional
from raw.endpoints.runner import run_endpoint as execute_endpoint
from raw.endpoints.executor import EndpointType
from raw.config.user_config import load_user_config
from raw.config.site_config import load_site_config, get_active_profile

@click.command(name="run")
@click.argument("endpoint_type", type=click.Choice([t.value for t in EndpointType]))
@click.argument("name")
@click.option("--param", "-p", multiple=True, help="Parameter in format name=value")
@click.option("--profile", help="Profile name to use")
def run_endpoint(endpoint_type: str, name: str, param: tuple[str, ...], profile: Optional[str]):
    """Run an endpoint (tool, resource, or prompt)"""
    try:
        # Load configs
        user_config = load_user_config()
        site_config = load_site_config()
        
        # Get active profile
        active_profile = get_active_profile(user_config, site_config)
        
        # Parse parameters
        params: Dict[str, Any] = {}
        for p in param:
            if "=" not in p:
                raise click.BadParameter(f"Parameter must be in format name=value: {p}")
            key, value = p.split("=", 1)
            params[key] = value
            
        # Execute endpoint
        result = execute_endpoint(endpoint_type, name, params, user_config, "cli", active_profile)
        
        # Output result
        if isinstance(result, list):
            for row in result:
                click.echo(row)
        else:
            click.echo(result)
            
    except Exception as e:
        click.echo(f"Error executing endpoint: {e}", err=True)
        raise click.Abort()
