import os
from pathlib import Path
from typing import Optional

import click
import yaml

from mxcp.cli.utils import configure_logging, get_env_flag, get_env_profile, output_error
from mxcp.config.analytics import track_command_with_timing
from mxcp.config.user_config import load_user_config


def check_existing_mxcp_repo(target_dir: Path) -> bool:
    """Check if there's a mxcp-site.yml in the target directory or any parent directory."""
    for parent in [target_dir] + list(target_dir.parents):
        if (parent / "mxcp-site.yml").exists():
            return True
    return False


def check_existing_duckdb(target_dir: Path, profile: str = "default") -> bool:
    """Check if there's a .duckdb file for the given profile in the target directory."""
    return (target_dir / f"db-{profile}.duckdb").exists()


def check_project_exists_in_user_config(project_name: str) -> bool:
    """Check if the project name already exists in the user config file.

    This function directly reads the config file without modifying it,
    unlike load_user_config which always ensures projects/profiles exist.
    """
    config_path = Path(os.environ.get("MXCP_CONFIG", Path.home() / ".mxcp" / "config.yml"))

    if not config_path.exists():
        return False

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)

        if not config:
            return False

        return project_name in config.get("projects", {})
    except Exception:
        # If we can't read the config, assume project doesn't exist
        return False


def create_mxcp_site_yml(target_dir: Path, project_name: str, profile_name: str):
    """Create the mxcp-site.yml file with the given project and profile names."""
    config = {"mxcp": "1.0.0", "project": project_name, "profile": profile_name}

    with open(target_dir / "mxcp-site.yml", "w") as f:
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
        "mxcp": "1.0.0",
        "tool": {
            "name": "hello_world",
            "description": "A simple hello world tool",
            "enabled": True,
            "parameters": [
                {
                    "name": "name",
                    "type": "string",
                    "description": "Name to greet",
                    "examples": ["World"],
                }
            ],
            "return": {"type": "string", "description": "Greeting message"},
            "source": {"file": "hello-world.sql"},
        },
    }

    with open(endpoints_dir / "hello-world.yml", "w") as f:
        yaml.dump(hello_world_yml, f, default_flow_style=False)


@click.command(name="init")
@click.argument(
    "folder", type=click.Path(file_okay=False, dir_okay=True, writable=True), default="."
)
@click.option("--project", help="Project name (defaults to folder name)")
@click.option("--profile", help="Profile name (defaults to 'default')")
@click.option("--bootstrap", is_flag=True, help="Create example hello world endpoint")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@track_command_with_timing("init")
def init(folder: str, project: str, profile: str, bootstrap: bool, debug: bool):
    """Initialize a new MXCP repository.

    This command creates a new MXCP repository by:
    1. Creating a mxcp-site.yml file with project and profile configuration
    2. Optionally creating example endpoint files

    Examples:
        mxcp init                    # Initialize in current directory
        mxcp init my-project        # Initialize in my-project directory
        mxcp init --project=test    # Initialize with specific project name
        mxcp init --bootstrap       # Initialize with example endpoint
    """
    # Get values from environment variables if not set by flags
    if not profile:
        profile = get_env_profile()

    # Configure logging
    configure_logging(debug)

    try:
        target_dir = Path(folder).resolve()

        # Check if we're trying to create a repo inside another one
        if check_existing_mxcp_repo(target_dir):
            raise click.ClickException("Cannot create a MXCP repository inside another one")

        # Check if .duckdb file already exists for this profile
        if check_existing_duckdb(target_dir, profile):
            raise click.ClickException(
                f"Cannot create a MXCP repository in a directory with an existing db-{profile}.duckdb file"
            )

        # Create target directory if it doesn't exist
        target_dir.mkdir(parents=True, exist_ok=True)

        # Determine project name (default to directory name)
        if not project:
            project = target_dir.name

        # Determine profile name (default to 'default')
        if not profile:
            profile = "default"

        # Check if project exists in user config
        if check_project_exists_in_user_config(project):
            if not click.confirm(f"Project '{project}' already exists in your config. Continue?"):
                return

        # Create mxcp-site.yml
        create_mxcp_site_yml(target_dir, project, profile)
        click.echo(f"Created mxcp-site.yml in {target_dir}")

        # Create example files if requested
        if bootstrap:
            create_hello_world_files(target_dir)
            click.echo("Created example hello world endpoint")

        # Initialize DuckDB session to create .duckdb file
        try:
            from mxcp.config.site_config import load_site_config
            from mxcp.engine.duckdb_session import DuckDBSession

            site_config = load_site_config(target_dir)
            new_user_config = load_user_config(site_config)
            session = DuckDBSession(new_user_config, site_config)
            session.close()  # Database file is created when session connects in constructor
            click.echo("Initialize DuckDB database")
        except Exception as e:
            click.echo(f"Warning: Failed to initialize DuckDB database: {e}")

    except Exception as e:
        output_error(e, json_output=False, debug=False)
