import click
from raw.endpoints.schema import validate_all_endpoints, validate_endpoint
from raw.config.site_config import load_site_config
from raw.config.user_config import load_user_config
from raw.cli.utils import output_result, output_error

def format_validation_results(results):
    """Format validation results for human-readable output"""
    if isinstance(results, str):
        return results
        
    output = []
    
    # Overall status
    status = results.get("status", "unknown")
    output.append(f"Status: {status.upper()}")
    output.append("")
    
    # Single endpoint validation
    if "path" in results:
        path = results["path"]
        message = results.get("message", "")
        output.append(f"Endpoint: {path}")
        output.append(f"Status: {status.upper()}")
        if message:
            output.append(f"Message: {message}")
        return "\n".join(output)
    
    # Multiple endpoint validation
    validated = results.get("validated", [])
    if not validated:
        output.append("No endpoints found to validate")
        return "\n".join(output)
        
    output.append(f"Validated {len(validated)} endpoints:")
    output.append("")
    
    for result in validated:
        path = result.get("path", "unknown")
        message = result.get("message", "")
        result_status = result.get("status", "unknown")
        
        output.append(f"Endpoint: {path}")
        output.append(f"Status: {result_status.upper()}")
        if message:
            output.append(f"Message: {message}")
        output.append("")
        
    return "\n".join(output)

@click.command(name="validate")
@click.argument("endpoint", required=False)
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed error information")
def validate(endpoint, profile, json_output: bool, debug: bool):
    """Validate one or all endpoints"""
    try:
        site_config = load_site_config()
        user_config = load_user_config(site_config)
        if endpoint:
            result = validate_endpoint(endpoint, user_config, site_config, profile)
        else:
            result = validate_all_endpoints(user_config, site_config, profile)
            
        if json_output:
            output_result(result, json_output, debug)
        else:
            click.echo(format_validation_results(result))
    except Exception as e:
        output_error(e, json_output, debug)