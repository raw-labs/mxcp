import click
import yaml
from pathlib import Path
import os
import sys
import json
import shutil
from mxcp.cli.utils import output_error, configure_logging, get_env_flag, get_env_profile
from mxcp.config.user_config import load_user_config
from mxcp.config.analytics import track_command_with_timing
from typing import Optional

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
    config = {
        "mxcp": "1.0.0",
        "project": project_name,
        "profile": profile_name
    }
    
    with open(target_dir / "mxcp-site.yml", "w") as f:
        yaml.dump(config, f, default_flow_style=False)

def create_hello_world_files(target_dir: Path):
    """Create example hello world endpoint files."""
    # Create endpoints directory if it doesn't exist
    endpoints_dir = target_dir / "endpoints"
    endpoints_dir.mkdir(exist_ok=True)

    # Create hello-world.sql - properly formatted
    hello_world_sql = """SELECT 'Hello, ' || $name || '!' as greeting
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
                    "examples": ["World", "Alice", "Bob"]
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
        yaml.dump(hello_world_yml, f, default_flow_style=False, sort_keys=False)

def detect_python_environment():
    """Detect the current Python environment type and relevant paths."""
    # Check if we're in a virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    
    # Get the virtual environment path if in one
    venv_path = None
    if in_venv:
        venv_path = sys.prefix
    
    # Check for common virtual environment indicators
    is_poetry = os.environ.get('POETRY_ACTIVE') == '1'
    is_conda = os.environ.get('CONDA_DEFAULT_ENV') is not None
    is_pipenv = os.environ.get('PIPENV_ACTIVE') == '1'
    
    # Get mxcp executable path
    mxcp_path = shutil.which('mxcp')
    
    return {
        'in_venv': in_venv,
        'venv_path': venv_path,
        'is_poetry': is_poetry,
        'is_conda': is_conda,
        'is_pipenv': is_pipenv,
        'mxcp_path': mxcp_path,
        'python_path': sys.executable
    }

def generate_claude_config(project_dir: Path, project_name: str):
    """Generate Claude Desktop configuration."""
    env_info = detect_python_environment()
    
    # Create the command based on environment
    if env_info['in_venv']:
        # Use the venv's Python to ensure mxcp is available
        if os.name == 'nt':  # Windows
            activate_path = Path(env_info['venv_path']) / 'Scripts' / 'activate.bat'
            command = "cmd.exe"
            args = ["/c", f"cd /d {project_dir} && {activate_path} && mxcp serve --transport stdio"]
        else:  # Unix-like
            activate_path = Path(env_info['venv_path']) / 'bin' / 'activate'
            command = "bash"
            args = ["-c", f"cd {project_dir} && source {activate_path} && mxcp serve --transport stdio"]
    else:
        # System-wide installation
        command = "mxcp"
        args = ["serve", "--transport", "stdio"]
        
    config = {
        "mcpServers": {
            project_name: {
                "command": command,
                "args": args,
            }
        }
    }
    
    # Add cwd for system-wide installation
    if not env_info['in_venv']:
        config["mcpServers"][project_name]["cwd"] = str(project_dir)
    
    # Add environment variables if needed
    if env_info['in_venv']:
        config["mcpServers"][project_name]["env"] = {
            "PATH": f"{Path(env_info['venv_path']) / 'bin'}:{os.environ.get('PATH', '')}",
            "HOME": str(Path.home())
        }
    
    return config

def show_next_steps(project_dir: Path, project_name: str, bootstrap: bool, config_generated: bool = True):
    """Show helpful next steps after initialization."""
    click.echo("\n" + "="*60)
    click.echo(click.style("✨ MXCP project initialized successfully!", fg='green', bold=True))
    click.echo("="*60 + "\n")
    
    click.echo(click.style("📁 Project Structure:", fg='cyan', bold=True))
    click.echo(f"   {project_dir}/")
    click.echo(f"   ├── mxcp-site.yml       # Project configuration")
    if bootstrap:
        click.echo(f"   └── endpoints/          # Your MCP endpoints")
        click.echo(f"       ├── hello-world.yml # Example tool definition")
        click.echo(f"       └── hello-world.sql # SQL implementation")
    else:
        click.echo(f"   └── endpoints/          # Create your endpoints here")
    
    click.echo(f"\n{click.style('🚀 Next Steps:', fg='cyan', bold=True)}\n")
    
    # Step 1: Test locally
    click.echo(f"{click.style('1. Test your setup locally:', fg='yellow')}")
    click.echo(f"   cd {project_dir}")
    if bootstrap:
        click.echo(f"   mxcp run tool hello_world --param name=World")
    else:
        click.echo(f"   # Create your first endpoint in endpoints/")
        click.echo(f"   # Then run: mxcp run tool <tool_name>")
    
    # Step 2: Start the server
    click.echo(f"\n{click.style('2. Start the MCP server:', fg='yellow')}")
    click.echo(f"   mxcp serve")
    
    # Step 3: Connect to Claude
    click.echo(f"\n{click.style('3. Connect to Claude Desktop:', fg='yellow')}")
    if config_generated:
        click.echo(f"   Add the generated server_config.json to your Claude Desktop config")
    else:
        click.echo(f"   Create a server configuration for Claude Desktop")
        click.echo(f"   Run 'mxcp init .' again to generate server_config.json")
    click.echo(f"   Config location:")
    if sys.platform == "darwin":
        click.echo(f"   ~/Library/Application Support/Claude/claude_desktop_config.json")
    elif sys.platform == "win32":
        click.echo(f"   %APPDATA%\\Claude\\claude_desktop_config.json")
    else:
        click.echo(f"   ~/.config/Claude/claude_desktop_config.json")
    
    # Step 4: Explore more
    click.echo(f"\n{click.style('4. Learn more:', fg='yellow')}")
    click.echo(f"   • List all endpoints:     mxcp list")
    click.echo(f"   • Validate endpoints:     mxcp validate")
    click.echo(f"   • Enable SQL tools:       Edit mxcp-site.yml (sql_tools: enabled: true)")
    click.echo(f"   • Add dbt integration:    Create dbt_project.yml and run dbt models")
    click.echo(f"   • View documentation:     https://mxcp.dev")
    
    if bootstrap:
        click.echo(f"\n{click.style('💡 Try it now:', fg='green')}")
        click.echo(f"   In Claude Desktop, ask: \"Use the hello_world tool to greet Alice\"")
    
    click.echo(f"\n{click.style('📚 Resources:', fg='cyan', bold=True)}")
    click.echo(f"   • Documentation: https://mxcp.dev")
    click.echo(f"   • Examples: https://github.com/raw-labs/mxcp/tree/main/examples")
    click.echo(f"   • Discord: https://discord.gg/XeqRp5Ud")
    click.echo("")

@click.command(name="init")
@click.argument("folder", type=click.Path(file_okay=False, dir_okay=True, writable=True), default=".")
@click.option("--project", help="Project name (defaults to folder name)")
@click.option("--profile", help="Profile name (defaults to 'default')")
@click.option("--bootstrap", is_flag=True, help="Create example hello world endpoint")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@track_command_with_timing("init")
def init(folder: str, project: str, profile: str, bootstrap: bool, debug: bool):
    """Initialize a new MXCP repository.
    
    \b
    This command creates a new MXCP repository by:
    1. Creating a mxcp-site.yml file with project and profile configuration
    2. Optionally creating example endpoint files
    3. Generating a server_config.json for Claude Desktop integration
    
    \b
    Examples:
        mxcp init                   # Initialize in current directory
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
            raise click.ClickException(f"Cannot create a MXCP repository in a directory with an existing db-{profile}.duckdb file")
        
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
        click.echo(f"✓ Created mxcp-site.yml")
        
        # Create example files if requested
        if bootstrap:
            create_hello_world_files(target_dir)
            click.echo("✓ Created example hello world endpoint")
            
        # Initialize DuckDB session to create .duckdb file
        try:
            from mxcp.config.site_config import load_site_config
            from mxcp.engine.duckdb_session import DuckDBSession
            
            site_config = load_site_config(target_dir)
            new_user_config = load_user_config(site_config)
            session = DuckDBSession(new_user_config, site_config)
            session.close()  # Database file is created when session connects in constructor
            click.echo("✓ Initialized DuckDB database")
        except Exception as e:
            click.echo(f"⚠️  Warning: Failed to initialize DuckDB database: {e}")
            
        # Generate Claude Desktop config
        try:
            # Ask if user wants to generate Claude Desktop config
            if click.confirm("\nWould you like to generate a Claude Desktop configuration file?"):
                claude_config = generate_claude_config(target_dir, project)
                config_path = target_dir / "server_config.json"
                
                with open(config_path, 'w') as f:
                    json.dump(claude_config, f, indent=2)
                
                click.echo(f"✓ Generated server_config.json for Claude Desktop")
                
                # Show the config content
                click.echo("\nGenerated configuration:")
                click.echo(json.dumps(claude_config, indent=2))
                config_generated = True
            else:
                click.echo("ℹ️  Skipped Claude Desktop configuration generation")
                config_generated = False
        except Exception as e:
            click.echo(f"⚠️  Warning: Failed to generate Claude config: {e}")
            config_generated = False
            
        # Show next steps
        show_next_steps(target_dir, project, bootstrap, config_generated)
            
    except Exception as e:
        output_error(e, json_output=False, debug=debug) 