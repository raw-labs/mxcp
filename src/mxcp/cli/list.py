import click
from typing import Dict, List, Tuple, Optional
from mxcp.endpoints.loader import EndpointLoader
from pathlib import Path
from mxcp.config.site_config import load_site_config
from mxcp.cli.utils import output_result, output_error, configure_logging
from mxcp.config.analytics import track_command_with_timing

def parse_endpoint(path: Path, endpoint: dict) -> Tuple[str, str, Optional[str]]:
    """Parse an endpoint dictionary to determine its type, name, and any error.
    
    Returns:
        Tuple of (kind, name, error_message)
    """
    if "tool" in endpoint:
        return "tool", endpoint["tool"]["name"], None
    elif "resource" in endpoint:
        return "resource", endpoint["resource"]["uri"], None
    elif "prompt" in endpoint:
        return "prompt", endpoint["prompt"]["name"], None
    else:
        return "unknown", "unknown", f"Invalid endpoint structure in {path}: missing tool/resource/prompt key"

@click.command(name="list")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@track_command_with_timing("list")
def list_endpoints(profile: str, json_output: bool, debug: bool):
    """List all available endpoints.
    
    This command discovers and lists all endpoints in the current repository.
    Endpoints can be tools, resources, or prompts.
    
    \b
    Examples:
        mxcp list                   # List all endpoints
        mxcp list --json-output     # Output in JSON format
        mxcp list --profile dev     # List endpoints in dev profile
    """
    # Configure logging
    configure_logging(debug)

    try:
        site_config = load_site_config()
        loader = EndpointLoader(site_config)
        endpoints = loader.discover_endpoints()
        
        # Process endpoints into structured data
        results = []
        for path, endpoint, error_msg in endpoints:
            if error_msg is not None:
                results.append({
                    "path": str(path),
                    "kind": "unknown",
                    "name": "unknown",
                    "error": error_msg
                })
            else:
                kind, name, error = parse_endpoint(path, endpoint)
                results.append({
                    "path": str(path),
                    "kind": kind,
                    "name": name,
                    "error": error
                })
        
        if json_output:
            output_result({
                "status": "ok" if all(r["error"] is None for r in results) else "error",
                "endpoints": results
            }, json_output, debug)
        else:
            if not results:
                click.echo(click.style("ℹ️  No endpoints found", fg='blue'))
                click.echo(f"   Create tools in the {click.style('tools/', fg='cyan')} directory, resources in {click.style('resources/', fg='cyan')}, etc.")
                return
                
            # Count valid and failed endpoints
            valid_count = sum(1 for r in results if r["error"] is None)
            failed_count = len(results) - valid_count
            
            # Header with emoji and color
            click.echo(f"\n{click.style('📋 Endpoints Discovery', fg='cyan', bold=True)}")
            click.echo(f"   Found {click.style(str(len(results)), fg='yellow')} endpoint files")
            
            if valid_count > 0:
                click.echo(f"   • {click.style(f'{valid_count} valid', fg='green')}")
            if failed_count > 0:
                click.echo(f"   • {click.style(f'{failed_count} failed', fg='red')}")
            
            # Group by status
            valid_endpoints = []
            failed_endpoints = []
            
            for result in results:
                if result["error"] is None:
                    valid_endpoints.append(result)
                else:
                    failed_endpoints.append(result)
            
            # Show failed endpoints first
            if failed_endpoints:
                click.echo(f"\n{click.style('❌ Failed endpoints:', fg='red', bold=True)}")
                for result in sorted(failed_endpoints, key=lambda r: r["path"]):
                    click.echo(f"  {click.style('✗', fg='red')} {result['path']}")
                    click.echo(f"    {click.style('Error:', fg='red')} {result['error']}")
            
            # Then show valid endpoints grouped by type
            if valid_endpoints:
                # Group by type
                tools = [r for r in valid_endpoints if r["kind"] == "tool"]
                resources = [r for r in valid_endpoints if r["kind"] == "resource"]
                prompts = [r for r in valid_endpoints if r["kind"] == "prompt"]
                
                click.echo(f"\n{click.style('✅ Valid endpoints:', fg='green', bold=True)}")
                
                if tools:
                    click.echo(f"\n  {click.style('🔧 Tools:', fg='yellow')}")
                    for result in sorted(tools, key=lambda r: r["name"]):
                        click.echo(f"    {click.style('✓', fg='green')} {click.style(result['name'], fg='cyan')} ({result['path']})")
                
                if resources:
                    click.echo(f"\n  {click.style('📦 Resources:', fg='yellow')}")
                    for result in sorted(resources, key=lambda r: r["name"]):
                        click.echo(f"    {click.style('✓', fg='green')} {click.style(result['name'], fg='cyan')} ({result['path']})")
                
                if prompts:
                    click.echo(f"\n  {click.style('💬 Prompts:', fg='yellow')}")
                    for result in sorted(prompts, key=lambda r: r["name"]):
                        click.echo(f"    {click.style('✓', fg='green')} {click.style(result['name'], fg='cyan')} ({result['path']})")
            
            # Summary tips
            if failed_count > 0:
                click.echo(f"\n{click.style('💡 Tip:', fg='yellow')} Fix validation errors by checking endpoint YAML syntax")
            
            click.echo()  # Empty line at end
                    
    except Exception as e:
        output_error(e, json_output, debug)
