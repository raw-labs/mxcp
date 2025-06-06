import click
from typing import Optional
from mxcp.endpoints.schema import validate_endpoint, validate_all_endpoints
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.cli.utils import output_result, output_error, configure_logging, get_env_flag, get_env_profile
from mxcp.config.analytics import track_command_with_timing
from mxcp.engine.duckdb_session import DuckDBSession

def format_validation_results(results):
    """Format validation results for human-readable output"""
    if isinstance(results, str):
        return results
        
    output = []
    
    # Overall status
    status = results.get("status", "unknown")
    
    # Single endpoint validation
    if "path" in results:
        path = results["path"]
        message = results.get("message", "")
        output.append(f"File: {path}")
        output.append(f"Status: {status.upper()}")
        if message:
            output.append(f"Error: {message}")
        return "\n".join(output)
    
    # Multiple endpoint validation
    validated = results.get("validated", [])
    if not validated:
        output.append("No endpoints found to validate")
        return "\n".join(output)
        
    # Count valid and failed endpoints
    valid_count = sum(1 for r in validated if r.get("status") == "ok")
    failed_count = len(validated) - valid_count
    
    output.append(f"Found {len(validated)} endpoint files ({valid_count} valid, {failed_count} failed):")
    output.append("")
    
    # Group by status
    valid_endpoints = []
    failed_endpoints = []
    
    for result in validated:
        path = result.get("path", "unknown")
        message = result.get("message", "")
        result_status = result.get("status", "unknown")
        
        if result_status == "ok":
            valid_endpoints.append((path, message))
        else:
            failed_endpoints.append((path, message))
    
    # Show failed endpoints first
    if failed_endpoints:
        output.append("Failed endpoints:")
        for path, message in failed_endpoints:
            output.append(f"  ✗ {path}")
            if message:
                output.append(f"    Error: {message}")
        output.append("")
    
    # Then show valid endpoints
    if valid_endpoints:
        output.append("Valid endpoints:")
        for path, _ in valid_endpoints:
            output.append(f"  ✓ {path}")
        
    return "\n".join(output)

@click.command(name="validate")
@click.argument("endpoint", required=False)
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("validate")
def validate(endpoint: Optional[str], profile: Optional[str], json_output: bool, debug: bool, readonly: bool):
    """Validate one or all endpoints.
    
    This command validates the schema and configuration of endpoints.
    If no endpoint is specified, all endpoints are validated.
    
    Examples:
        mxcp validate                    # Validate all endpoints
        mxcp validate my_endpoint       # Validate specific endpoint
        mxcp validate --json-output     # Output results in JSON format
        mxcp validate --readonly        # Open database connection in read-only mode
    """
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")
        
    # Configure logging
    configure_logging(debug)

    try:
        site_config = load_site_config()
        user_config = load_user_config(site_config)
        
        # Create a shared DuckDB session for all validations
        # Connection will be established on-demand when needed
        session = DuckDBSession(user_config, site_config, profile, readonly=readonly)
        
        try:
            if endpoint:
                result = validate_endpoint(endpoint, user_config, site_config, profile, session)
            else:
                result = validate_all_endpoints(user_config, site_config, profile, session)
            
            if json_output:
                output_result(result, json_output, debug)
            else:
                click.echo(format_validation_results(result))
        finally:
            session.close()
            
    except Exception as e:
        output_error(e, json_output, debug)