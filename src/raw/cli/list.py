import click
from typing import Dict, List, Tuple, Optional
from raw.endpoints.loader import EndpointLoader
from pathlib import Path
from raw.config.site_config import load_site_config
from raw.cli.utils import output_result, output_error, configure_logging
from raw.config.analytics import track_command_with_timing

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
    
    Examples:
        raw list                    # List all endpoints
        raw list --json-output     # Output in JSON format
        raw list --profile dev     # List endpoints in dev profile
    """
    # Configure logging
    configure_logging(debug)

    try:
        site_config = load_site_config()
        loader = EndpointLoader(site_config)
        endpoints = loader.discover_endpoints()
        
        # Process endpoints into structured data
        results = []
        for path, endpoint in endpoints:
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
                click.echo("No endpoints found")
                return
                
            click.echo(f"\nFound {len(results)} endpoint files:")
            for result in results:
                if result["error"]:
                    click.echo(f"\n[ERROR] {result['error']}")
                else:
                    click.echo(f"\n[{result['kind']}] {result['name']}")
                    click.echo(f"  Path: {result['path']}")
                    
    except Exception as e:
        output_error(e, json_output, debug)
