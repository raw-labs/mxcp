import click
import json
from typing import Dict, List, Tuple, Optional
from raw.endpoints.loader import EndpointLoader
from pathlib import Path
from raw.config.site_config import load_site_config

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
@click.option("--json-output", is_flag=True, help="Output in JSON format")
def list_endpoints(json_output: bool):
    """List available endpoints"""
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
        # JSON output
        print(json.dumps({
            "status": "ok" if all(r["error"] is None for r in results) else "error",
            "endpoints": results
        }, indent=2))
    else:
        # Human-friendly output
        if not results:
            print("No endpoints found")
            return
            
        print(f"\nFound {len(results)} endpoint files:")
        for result in results:
            if result["error"]:
                print(f"\n[ERROR] {result['error']}")
            else:
                print(f"\n[{result['kind']}] {result['name']}")
                print(f"  Path: {result['path']}")
