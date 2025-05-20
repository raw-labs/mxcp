import click
from raw.endpoints.schema import validate_all_endpoints, validate_endpoint
from raw.config.site_config import load_site_config
from raw.cli.utils import output_result, output_error

@click.command(name="validate")
@click.argument("endpoint", required=False)
@click.option("--profile", default=None)
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed error information")
def validate(endpoint, profile, json_output: bool, debug: bool):
    """Validate one or all endpoints"""
    try:
        config = load_site_config()
        if endpoint:
            result = validate_endpoint(endpoint, config, profile)
        else:
            result = validate_all_endpoints(config, profile)
            
        output_result(result, json_output, debug)
    except Exception as e:
        output_error(e, json_output, debug)