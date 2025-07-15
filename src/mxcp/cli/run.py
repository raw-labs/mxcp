import click
import json
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from mxcp.endpoints.loader import EndpointLoader
from mxcp.endpoints.executor import get_endpoint_source_code
from mxcp.config.user_config import load_user_config, UserConfig
from mxcp.config.site_config import load_site_config, get_active_profile, find_repo_root, SiteConfig
from mxcp.config.execution_engine import create_execution_engine
from mxcp.cli.utils import output_result, output_error, configure_logging, get_env_flag, get_env_profile
from mxcp.cli.table_renderer import format_result_for_display
from mxcp.config.analytics import track_command_with_timing
from mxcp.sdk.auth.providers import UserContext
from mxcp.sdk.executor import ExecutionContext

async def _execute_endpoint_sdk(
    endpoint_type: str, 
    name: str, 
    params: Dict[str, Any], 
    user_config: UserConfig, 
    site_config: SiteConfig, 
    profile_name: str,
    readonly: bool,
    skip_output_validation: bool,
    user_context: Optional[UserContext]
) -> Any:
    """Execute endpoint using SDK executor system."""
    
    # Find repository root
    repo_root = find_repo_root()
    if not repo_root:
        raise ValueError("Could not find repository root (no mxcp-site.yml found)")
    
    # Load the endpoint using EndpointLoader
    loader = EndpointLoader(site_config)
    endpoint_result = loader.load_endpoint(endpoint_type, name)
    
    if not endpoint_result:
        raise ValueError(f"Endpoint '{name}' not found in {endpoint_type}s")
    
    endpoint_file_path, endpoint_definition = endpoint_result
    
    # endpoint_definition is the raw dict containing the full endpoint structure
    # Extract the type-specific data
    if endpoint_type not in endpoint_definition:
        raise ValueError(f"No {endpoint_type} definition found in endpoint")
    
    endpoint_dict = endpoint_definition[endpoint_type]
    
    # Get source code and determine language (cast to dict for function signature)
    source_code = get_endpoint_source_code(dict(endpoint_definition), endpoint_type, endpoint_file_path, repo_root)
    
    # Determine language based on endpoint definition or file extension
    language = endpoint_dict.get("language")
    if not language:
        # Infer from source: if it's a file ending in .py, it's python; otherwise SQL
        if source_code.strip().endswith('.py') or '.py:' in source_code:
            language = "python"
        else:
            language = "sql"
    
    # Create execution engine
    engine = create_execution_engine(user_config, site_config, profile_name, readonly=readonly)
    
    try:
        # Create execution context
        execution_context = ExecutionContext(user_context=user_context)
        
        # Get validation schemas if not skipping validation
        input_schema = None
        output_schema = None
        if not skip_output_validation:
            input_schema = endpoint_dict.get("parameters")
            output_schema = endpoint_dict.get("return_type")
        
        # Execute using the SDK engine
        result = await engine.execute(
            language=language,
            source_code=source_code,
            params=params,
            context=execution_context,
            input_schema=input_schema,
            output_schema=output_schema
        )
        
        return result
        
    finally:
        # Shutdown the engine
        engine.shutdown()

@click.command(name="run")
@click.argument("endpoint_type", type=click.Choice(["tool", "resource", "prompt"]))
@click.argument("name")
@click.option("--param", "-p", multiple=True, help="Parameter in format name=value or name=@file.json for complex values")
@click.option("--user-context", "-u", help="User context as JSON string or @file.json")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--skip-output-validation", is_flag=True, help="Skip output validation against the return type definition")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("run")
def run_endpoint(endpoint_type: str, name: str, param: tuple[str, ...], user_context: Optional[str], profile: Optional[str], json_output: bool, debug: bool, skip_output_validation: bool, readonly: bool):
    """Run an endpoint (tool, resource, or prompt).
    
    \b
    Parameters can be provided in two ways:
    1. Simple values: --param name=value
    2. Complex values from JSON file: --param name=@file.json
    
    \b
    User context can be provided for policy enforcement:
    --user-context '{"user_id": "123", "role": "admin", "permissions": ["read", "write"]}'
    --user-context @user_context.json
    
    \b
    Examples:
        mxcp run tool my_tool --param name=value
        mxcp run tool my_tool --param complex=@data.json
        mxcp run tool my_tool --readonly
        mxcp run tool my_tool --user-context '{"role": "admin"}'
    """
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")
        
    # Configure logging
    configure_logging(debug)

    try:
        # Show what we're running (only in non-JSON mode)
        if not json_output:
            click.echo(f"\n{click.style('🚀 Running', fg='cyan', bold=True)} {click.style(endpoint_type, fg='yellow')} {click.style(name, fg='green', bold=True)}")
            if param:
                click.echo(f"{click.style('📋 Parameters:', fg='cyan')}")
                for p in param:
                    if "=" in p:
                        key, value = p.split("=", 1)
                        if value.startswith("@"):
                            click.echo(f"   • {key} = <from file: {value[1:]}>")
                        else:
                            # Truncate long values
                            display_value = value if len(value) <= 50 else value[:47] + "..."
                            click.echo(f"   • {key} = {display_value}")
            if readonly:
                click.echo(f"{click.style('🔒 Mode:', fg='yellow')} Read-only")
            click.echo()  # Empty line for spacing

        # Load configs
        site_config = load_site_config()
        user_config = load_user_config(site_config)
        
        profile_name = profile or site_config["profile"]
        
        # Parse user context if provided
        user_context_obj = None
        if user_context:
            if user_context.startswith("@"):
                # Load from file
                file_path = Path(user_context[1:])
                if not file_path.exists():
                    raise click.BadParameter(f"User context file not found: {file_path}")
                try:
                    with open(file_path) as f:
                        context_data = json.load(f)
                except json.JSONDecodeError as e:
                    raise click.BadParameter(f"Invalid JSON in user context file {file_path}: {e}")
            else:
                # Parse as JSON string
                try:
                    context_data = json.loads(user_context)
                except json.JSONDecodeError as e:
                    raise click.BadParameter(f"Invalid JSON in user context: {e}")
            
            # Create UserContext object from the data
            user_context_obj = UserContext(
                provider="cli",  # Special provider for CLI usage
                user_id=context_data.get("user_id", "cli_user"),
                username=context_data.get("username", "cli_user"),
                email=context_data.get("email"),
                name=context_data.get("name"),
                avatar_url=context_data.get("avatar_url"),
                raw_profile=context_data  # Store full context for policy access
            )
        
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
            
        # Execute endpoint using SDK executor system
        result = asyncio.run(_execute_endpoint_sdk(
            endpoint_type, name, params, user_config, site_config, profile_name, 
            readonly, skip_output_validation, user_context_obj
        ))
        
        # Output result
        if json_output:
            output_result(result, json_output, debug)
        else:
            # Add success indicator
            click.echo(f"{click.style('✅ Success!', fg='green', bold=True)}")
            
            # Use the table renderer for nice formatting
            format_result_for_display(result)
                
            # Add execution time if available in debug mode
            if debug:
                click.echo(f"\n{click.style('⏱️  Execution completed', fg='cyan')}")
            
    except Exception as e:
        if json_output:
            output_error(e, json_output, debug)
        else:
            click.echo(f"\n{click.style('❌ Error:', fg='red', bold=True)} {str(e)}")
            if debug:
                import traceback
                click.echo(f"\n{click.style('🔍 Stack trace:', fg='yellow')}")
                click.echo(traceback.format_exc())
            click.get_current_context().exit(1)
