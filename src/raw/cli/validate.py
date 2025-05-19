import click
from raw.endpoints.schema import validate_all_endpoints, validate_endpoint
from raw.config.site_config import load_site_config
from raw.config.user_config import load_user_config

@click.command(name="validate")
@click.argument("endpoint", required=False)
@click.option("--profile", default=None)
@click.option("--json-output", is_flag=True, help="Output in JSON format")
def validate(endpoint, profile, json_output: bool):
    """Validate one or all endpoints"""
    config = load_site_config()
    user = load_user_config()
    if endpoint:
        result = validate_endpoint(endpoint, config, user, profile)
    else:
        result = validate_all_endpoints(config, user, profile)
    print(result if json_output else str(result))