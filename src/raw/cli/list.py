import click
from raw.endpoints.loader import EndpointLoader
from pathlib import Path

@click.command(name="list")
def list_endpoints():
    """List available endpoints"""
    loader = EndpointLoader()
    loader.load_site_config()  # Load site config first
    endpoints = loader.discover_endpoints()
    
    for endpoint in endpoints:
        # Determine endpoint type and name
        if "tool" in endpoint:
            kind = "tool"
            name = endpoint["tool"]["name"]
        elif "resource" in endpoint:
            kind = "resource"
            name = endpoint["resource"]["uri"]
        elif "prompt" in endpoint:
            kind = "prompt"
            name = endpoint["prompt"]["name"]
        else:
            kind = "?"
            name = "???"
            
        print(f"[{kind}] {name}")
