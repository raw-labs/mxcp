import click
from typing import Optional
from mxcp.endpoints.validate import validate_endpoint, validate_all_endpoints
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.cli.utils import output_result, output_error, configure_logging, get_env_flag, get_env_profile
from mxcp.config.analytics import track_command_with_timing
from mxcp.config.execution_engine import create_execution_engine

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
        
        if status == "ok":
            output.append(f"{click.style('✅ Validation passed!', fg='green', bold=True)}")
            output.append(f"\n{click.style('📄 File:', fg='cyan')} {path}")
        else:
            output.append(f"{click.style('❌ Validation failed!', fg='red', bold=True)}")
            output.append(f"\n{click.style('📄 File:', fg='cyan')} {path}")
            if message:
                output.append(f"{click.style('Error:', fg='red')} {message}")
        return "\n".join(output)
    
    # Multiple endpoint validation
    validated = results.get("validated", [])
    if not validated:
        output.append(click.style("ℹ️  No endpoints found to validate", fg='blue'))
        output.append(f"   Create tools in the {click.style('tools/', fg='cyan')} directory, resources in {click.style('resources/', fg='cyan')}, etc.")
        return "\n".join(output)
        
    # Count valid and failed endpoints
    valid_count = sum(1 for r in validated if r.get("status") == "ok")
    failed_count = len(validated) - valid_count
    
    # Header
    output.append(f"\n{click.style('🔍 Validation Results', fg='cyan', bold=True)}")
    output.append(f"   Validated {click.style(str(len(validated)), fg='yellow')} endpoint files")
    
    if valid_count > 0:
        output.append(f"   • {click.style(f'{valid_count} passed', fg='green')}")
    if failed_count > 0:
        output.append(f"   • {click.style(f'{failed_count} failed', fg='red')}")
    
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
        output.append(f"\n{click.style('❌ Failed validation:', fg='red', bold=True)}")
        for path, message in sorted(failed_endpoints):
            output.append(f"  {click.style('✗', fg='red')} {path}")
            if message:
                output.append(f"    {click.style('Error:', fg='red')} {message}")
    
    # Then show valid endpoints
    if valid_endpoints:
        output.append(f"\n{click.style('✅ Passed validation:', fg='green', bold=True)}")
        for path, _ in sorted(valid_endpoints):
            output.append(f"  {click.style('✓', fg='green')} {path}")
    
    # Summary message
    if failed_count == 0:
        output.append(f"\n{click.style('🎉 All endpoints are valid!', fg='green', bold=True)}")
    else:
        output.append(f"\n{click.style('💡 Tip:', fg='yellow')} Fix validation errors to ensure endpoints work correctly")
        
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
    
    \b
    Examples:
        mxcp validate                   # Validate all endpoints
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
        
        # Create a shared ExecutionEngine for all validations
        execution_engine = create_execution_engine(user_config, site_config, profile, readonly=readonly)
        
        try:
            if endpoint:
                result = validate_endpoint(endpoint, site_config, execution_engine)
            else:
                result = validate_all_endpoints(site_config, execution_engine)
            
            if json_output:
                output_result(result, json_output, debug)
            else:
                click.echo(format_validation_results(result))
        finally:
            execution_engine.shutdown()
            
    except Exception as e:
        output_error(e, json_output, debug)