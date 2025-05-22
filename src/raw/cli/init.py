import click
import yaml
from pathlib import Path
import os
from raw.cli.utils import output_error
from raw.config.user_config import load_user_config

def check_existing_raw_repo(target_dir: Path) -> bool:
    """Check if there's a raw-site.yml in the target directory or any parent directory."""
    for parent in [target_dir] + list(target_dir.parents):
        if (parent / "raw-site.yml").exists():
            return True
    return False

def check_project_exists(user_config: dict, project_name: str) -> bool:
    """Check if the project name already exists in the user config."""
    return project_name in user_config.get("projects", {})

def create_raw_site_yml(target_dir: Path, project_name: str, profile_name: str):
    """Create the raw-site.yml file with the given project and profile names."""
    config = {
        "raw": "1.0.0",
        "project": project_name,
        "profile": profile_name
    }
    
    with open(target_dir / "raw-site.yml", "w") as f:
        yaml.dump(config, f, default_flow_style=False)

def create_hello_world_files(target_dir: Path):
    """Create example hello world endpoint files."""
    # Create endpoints directory if it doesn't exist
    endpoints_dir = target_dir / "endpoints"
    endpoints_dir.mkdir(exist_ok=True)

    # Create hello-world.sql
    hello_world_sql = """
    SELECT 'Hello, ' || $name || '!' as greeting
    """
    
    with open(endpoints_dir / "hello-world.sql", "w") as f:
        f.write(hello_world_sql)
    
    # Create hello-world.yml
    hello_world_yml = {
        "raw": "1.0.0",
        "tool": {
            "name": "hello_world",
            "description": "A simple hello world tool",
            "enabled": True,
            "parameters": [
                {
                    "name": "name",
                    "type": "string",
                    "description": "Name to greet",
                    "examples": ["World"]
                }
            ],
            "return": {
                "type": "string",
                "description": "Greeting message"
            },
            "source": {
                "file": "hello-world.sql"
            }
        }
    }
    
    with open(endpoints_dir / "hello-world.yml", "w") as f:
        yaml.dump(hello_world_yml, f, default_flow_style=False)

    

@click.command(name="init")
@click.argument("folder", type=click.Path(file_okay=False, dir_okay=True, writable=True), default=".")
@click.option("--project", help="Project name (defaults to folder name)")
@click.option("--profile", help="Profile name (defaults to 'default')")
@click.option("--bootstrap", is_flag=True, help="Create example hello world endpoint")
def init(folder: str, project: str, profile: str, bootstrap: bool):
    """Initialize a new RAW repository in the specified folder.

    This command creates a new RAW repository by:
    1. Creating a raw-site.yml file with project and profile configuration
    2. Optionally creating example endpoint files

    Examples:
        raw init                    # Initialize in current directory
        raw init my-project        # Initialize in my-project directory
        raw init --project=test    # Initialize with specific project name
        raw init --bootstrap       # Initialize with example endpoint
    """
    try:
        target_dir = Path(folder).resolve()
        
        # Check if we're trying to create a repo inside another one
        if check_existing_raw_repo(target_dir):
            raise click.ClickException("Cannot create a RAW repository inside another one")
        
        # Create target directory if it doesn't exist
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine project name (default to directory name)
        if not project:
            project = target_dir.name
        
        # Determine profile name (default to 'default')
        if not profile:
            profile = "default"
            
        # Check if project exists in user config
        try:
            user_config = load_user_config({"project": project, "profile": profile}, generate_default=False)
            if check_project_exists(user_config, project):
                if not click.confirm(f"Project '{project}' already exists in your config. Continue?"):
                    return
        except FileNotFoundError:
            # No user config yet, that's fine
            pass
            
        # Create raw-site.yml
        create_raw_site_yml(target_dir, project, profile)
        click.echo(f"Created raw-site.yml in {target_dir}")
        
        # Create example files if requested
        if bootstrap:
            create_hello_world_files(target_dir)
            click.echo("Created example hello world endpoint")
            
    except Exception as e:
        output_error(e, json_output=False, debug=False) 