import click
import yaml
from pathlib import Path
import os
import sys
import json
import shutil
import platform
import base64
from mxcp.cli.utils import output_error, configure_logging, get_env_flag, get_env_profile
from mxcp.config.user_config import load_user_config
from mxcp.config.analytics import track_command_with_timing
from typing import Optional, Dict, List

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
        "mxcp": 1,
        "project": project_name,
        "profile": profile_name
    }
    
    with open(target_dir / "mxcp-site.yml", "w") as f:
        yaml.dump(config, f, default_flow_style=False)

def create_hello_world_files(target_dir: Path):
    """Create example hello world endpoint files and directory structure."""
    # Create all directories for the new structure
    directories = [
        "tools",
        "resources", 
        "prompts",
        "evals",
        "python",
        "plugins",
        "sql",
        "drift",
        "audit",
        "data"
    ]
    
    for directory in directories:
        dir_path = target_dir / directory
        dir_path.mkdir(exist_ok=True)
        
        # Create .gitkeep files for empty directories
        if directory in ["resources", "prompts", "evals", "python", "plugins", "drift", "audit", "data"]:
            gitkeep_file = dir_path / ".gitkeep"
            gitkeep_file.touch()

    # Create hello-world.sql in the sql directory
    hello_world_sql = """SELECT 'Hello, ' || $name || '!' as greeting
"""
    
    with open(target_dir / "sql" / "hello-world.sql", "w") as f:
        f.write(hello_world_sql)
    
    # Create hello-world.yml in the tools directory
    hello_world_yml = {
        "mxcp": 1,
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
                "file": "../sql/hello-world.sql"
            }
        }
    }
    
    with open(target_dir / "tools" / "hello-world.yml", "w") as f:
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

def detect_cursor_installation() -> Optional[Dict[str, str]]:
    """Detect Cursor IDE installation and return relevant paths."""
    system = platform.system().lower()
    cursor_info = {}
    
    # Common Cursor executable names
    cursor_executables = ["cursor", "cursor.exe"] if system == "windows" else ["cursor"]
    
    # Check if Cursor is in PATH
    cursor_path = None
    for executable in cursor_executables:
        cursor_path = shutil.which(executable)
        if cursor_path:
            break
    
    if cursor_path:
        cursor_info["executable"] = cursor_path
    
    # Determine config directory based on OS
    home = Path.home()
    if system == "windows":
        cursor_config_dir = home / "AppData" / "Roaming" / "Cursor" / "User"
    elif system == "darwin":  # macOS
        cursor_config_dir = home / "Library" / "Application Support" / "Cursor" / "User"
    else:  # Linux and other Unix-like
        cursor_config_dir = home / ".config" / "Cursor" / "User"
    
    if cursor_config_dir.exists():
        cursor_info["config_dir"] = str(cursor_config_dir)
        cursor_info["global_mcp_config"] = str(home / ".cursor" / "mcp.json")
    
    return cursor_info if cursor_info else None

def generate_cursor_config(project_dir: Path, project_name: str) -> Dict:
    """Generate Cursor MCP configuration (same format as Claude Desktop)."""
    return generate_claude_config(project_dir, project_name)

def generate_cursor_deeplink(config: Dict, project_name: str) -> str:
    """Generate Cursor deeplink for one-click installation."""
    # Extract just the server config for the deeplink (no mcpServers wrapper)
    server_config = config["mcpServers"][project_name]
    
    # Base64 encode the configuration
    config_json = json.dumps(server_config)
    encoded_config = base64.b64encode(config_json.encode()).decode()
    
    # Generate the deeplink using the correct cursor:// protocol
    deeplink = f"cursor://anysphere.cursor-deeplink/mcp/install?name={project_name}&config={encoded_config}"
    
    return deeplink

def install_cursor_config(config: Dict, project_name: str, install_type: str = "project", project_dir: Optional[Path] = None) -> bool:
    """Install Cursor MCP configuration.
    
    Args:
        config: The MCP configuration to install
        project_name: Name of the project
        install_type: Either "project" or "global"
        project_dir: Project directory (required for project install)
    
    Returns:
        True if installation was successful, False otherwise
    """
    try:
        if install_type == "project":
            if not project_dir:
                return False
            cursor_dir = project_dir / ".cursor"
            cursor_dir.mkdir(exist_ok=True)
            config_path = cursor_dir / "mcp.json"
        else:  # global
            cursor_dir = Path.home() / ".cursor"
            cursor_dir.mkdir(exist_ok=True)
            config_path = cursor_dir / "mcp.json"
        
        # If config file exists, merge with existing configuration
        existing_config = {}
        if config_path.exists():
            try:
                with open(config_path) as f:
                    existing_config = json.load(f)
            except (json.JSONDecodeError, Exception):
                # If we can't read existing config, start fresh
                existing_config = {}
        
        # Merge configurations
        if "mcpServers" not in existing_config:
            existing_config["mcpServers"] = {}
        
        existing_config["mcpServers"][project_name] = config["mcpServers"][project_name]
        
        # Write updated configuration
        with open(config_path, 'w') as f:
            json.dump(existing_config, f, indent=2)
        
        return True
    except Exception:
        return False

def show_cursor_next_steps(project_name: str, install_type: str):
    """Show Cursor-specific next steps."""
    click.echo(f"\n{click.style('📝 Cursor IDE Manual Setup:', fg='cyan', bold=True)}")
    
    click.echo(f"   📋 To install manually:")
    click.echo(f"   1. Open Cursor IDE")
    click.echo(f"   2. Go to Settings > Features > Model Context Protocol")
    click.echo(f"   3. Add the configuration shown above, or")
    click.echo(f"   4. Use the one-click install link provided above")
    
    click.echo(f"\n   🚀 After installation:")
    click.echo(f"   • Restart Cursor IDE")
    click.echo(f"   • Open the Agent/Chat")
    click.echo(f"   • The '{project_name}' MCP server will be automatically available")
    click.echo(f"   • Try asking: \"List the available tools from {project_name}\"")

def show_next_steps(project_dir: Path, project_name: str, bootstrap: bool, config_generated: bool = True, cursor_configured: bool = False, cursor_install_type: str = None):
    """Show helpful next steps after initialization."""
    click.echo("\n" + "="*60)
    click.echo(click.style("✨ MXCP project initialized successfully!", fg='green', bold=True))
    click.echo("="*60 + "\n")
    
    click.echo(click.style("📁 Project Structure:", fg='cyan', bold=True))
    click.echo(f"   {project_dir}/")
    click.echo(f"   ├── mxcp-site.yml       # Project configuration")
    if bootstrap:
        click.echo(f"   ├── tools/              # Tool definitions")
        click.echo(f"   │   └── hello-world.yml # Example tool definition")
        click.echo(f"   ├── sql/                # SQL implementations")
        click.echo(f"   │   └── hello-world.sql # SQL implementation")
        click.echo(f"   ├── resources/          # Resource definitions")
        click.echo(f"   ├── prompts/            # Prompt definitions")
        click.echo(f"   ├── evals/              # Evaluation definitions")
        click.echo(f"   ├── python/             # Python extensions")
        click.echo(f"   ├── plugins/            # Plugin definitions")
        click.echo(f"   ├── drift/              # Drift snapshots")
        click.echo(f"   ├── audit/              # Audit logs")
        click.echo(f"   └── data/               # Database files")
    else:
        click.echo(f"   ├── tools/              # Create your tool definitions here")
        click.echo(f"   ├── resources/          # Create your resource definitions here")
        click.echo(f"   ├── prompts/            # Create your prompt definitions here")
        click.echo(f"   ├── evals/              # Create your evaluation definitions here")
        click.echo(f"   ├── python/             # Create your Python extensions here")
        click.echo(f"   ├── plugins/            # Create your plugin definitions here")
        click.echo(f"   ├── sql/                # Create your SQL implementations here")
        click.echo(f"   ├── drift/              # Drift snapshots will be stored here")
        click.echo(f"   ├── audit/              # Audit logs will be stored here")
        click.echo(f"   └── data/               # Database files will be stored here")
    
    click.echo(f"\n{click.style('🚀 Next Steps:', fg='cyan', bold=True)}\n")
    
    # Step 1: Test locally
    click.echo(f"{click.style('1. Test your setup locally:', fg='yellow')}")
    click.echo(f"   cd {project_dir}")
    if bootstrap:
        click.echo(f"   mxcp run tool hello_world --param name=World")
    else:
        click.echo(f"   # Create your first tool in tools/")
        click.echo(f"   # Then run: mxcp run tool <tool_name>")
    
    # Step 2: Start the server
    click.echo(f"\n{click.style('2. Start the MCP server:', fg='yellow')}")
    click.echo(f"   mxcp serve")
    
    # Step 3: Connect to IDE
    if config_generated and cursor_configured:
        click.echo(f"\n{click.style('3. Connect to your preferred IDE:', fg='yellow')}")
        click.echo(f"   🔹 Claude Desktop: Add server_config.json to Claude config")
        click.echo(f"   🔹 Cursor IDE: Already configured! Open Cursor and start using.")
    elif config_generated:
        click.echo(f"\n{click.style('3. Connect to Claude Desktop:', fg='yellow')}")
        click.echo(f"   Add the generated server_config.json to your Claude Desktop config")
    elif cursor_configured:
        click.echo(f"\n{click.style('3. Connect to Cursor IDE:', fg='yellow')}")
        click.echo(f"   Already configured! Open Cursor and start using.")
    else:
        click.echo(f"\n{click.style('3. Connect to your IDE:', fg='yellow')}")
        click.echo(f"   Create configurations for Claude Desktop or Cursor IDE")
        click.echo(f"   Run 'mxcp init .' again to generate configurations")
    
    if config_generated or cursor_configured:
        # Show IDE-specific config locations
        click.echo(f"   Config locations:")
        if config_generated:
            if sys.platform == "darwin":
                click.echo(f"   • Claude Desktop: ~/Library/Application Support/Claude/claude_desktop_config.json")
            elif sys.platform == "win32":
                click.echo(f"   • Claude Desktop: %APPDATA%\\Claude\\claude_desktop_config.json")
            else:
                click.echo(f"   • Claude Desktop: ~/.config/Claude/claude_desktop_config.json")
        
        if cursor_configured:
            if cursor_install_type == "project":
                click.echo(f"   • Cursor IDE: {project_dir}/.cursor/mcp.json (project-specific)")
            else:
                click.echo(f"   • Cursor IDE: ~/.cursor/mcp.json (global)")
    
    # Step 4: Explore more
    click.echo(f"\n{click.style('4. Learn more:', fg='yellow')}")
    click.echo(f"   • List all endpoints:     mxcp list")
    click.echo(f"   • Validate endpoints:     mxcp validate")
    click.echo(f"   • Enable SQL tools:       Edit mxcp-site.yml (sql_tools: enabled: true)")
    click.echo(f"   • Add dbt integration:    Create dbt_project.yml and run dbt models")
    click.echo(f"   • View documentation:     https://mxcp.dev")
    
    if bootstrap:
        click.echo(f"\n{click.style('💡 Try it now:', fg='green')}")
        if config_generated and cursor_configured:
            click.echo(f"   In Claude Desktop or Cursor IDE, ask: \"Use the hello_world tool to greet Alice\"")
        elif config_generated:
            click.echo(f"   In Claude Desktop, ask: \"Use the hello_world tool to greet Alice\"")
        elif cursor_configured:
            click.echo(f"   In Cursor IDE, ask: \"Use the hello_world tool to greet Alice\"")
    
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
    3. Generating configurations for Claude Desktop and/or Cursor IDE integration
    
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
            
        # Load configs (this will handle migration checks)
        from mxcp.config.site_config import load_site_config
        from mxcp.engine.duckdb_session import DuckDBSession
        
        site_config = load_site_config(target_dir)
        new_user_config = load_user_config(site_config)
        
        # Initialize DuckDB session to create .duckdb file
        try:
            session = DuckDBSession(new_user_config, site_config)
            session.close()  # Database file is created when session connects in constructor
            click.echo("✓ Initialized DuckDB database")
        except Exception as e:
            click.echo(f"⚠️  Warning: Failed to initialize DuckDB database: {e}")
        
        # IDE Configuration Generation
        config_generated = False
        cursor_configured = False
        cursor_install_type = None
        
        # Generate Claude Desktop config
        try:
            if click.confirm("\nWould you like to generate a Claude Desktop configuration file?"):
                claude_config = generate_claude_config(target_dir, project)
                config_path = target_dir / "server_config.json"
                
                with open(config_path, 'w') as f:
                    json.dump(claude_config, f, indent=2)
                
                click.echo(f"✓ Generated server_config.json for Claude Desktop")
                
                # Show the config content
                click.echo("\nGenerated Claude Desktop configuration:")
                click.echo(json.dumps(claude_config, indent=2))
                config_generated = True
            else:
                click.echo("ℹ️  Skipped Claude Desktop configuration generation")
        except Exception as e:
            click.echo(f"⚠️  Warning: Failed to generate Claude config: {e}")
        
        # Generate Cursor IDE config
        try:
            if click.confirm("\nWould you like to set up Cursor IDE integration?"):
                cursor_config = generate_cursor_config(target_dir, project)
                
                # Generate deeplink by default
                deeplink = generate_cursor_deeplink(cursor_config, project)
                
                # Detect Cursor installation
                cursor_info = detect_cursor_installation()
                
                if cursor_info:
                    click.echo(f"✓ Detected Cursor IDE installation")
                    
                    # Offer installation options
                    click.echo("\nChoose Cursor configuration option:")
                    click.echo("1. Auto-configure (recommended) - Install directly to your Cursor config")
                    click.echo("2. Manual setup - Copy configuration manually")
                    
                    choice = click.prompt("Enter your choice", type=click.Choice(['1', '2']), default='1')
                    
                    if choice == '1':
                        # Ask for installation scope
                        scope_choice = click.prompt(
                            "Installation scope:\n1. Project-specific (only this project)\n2. Global (all Cursor workspaces)\nEnter choice",
                            type=click.Choice(['1', '2']), default='1'
                        )
                        
                        install_type = "project" if scope_choice == '1' else "global"
                        
                        if install_cursor_config(cursor_config, project, install_type, target_dir):
                            click.echo(f"✓ Configured Cursor MCP server ({'project-specific' if install_type == 'project' else 'globally'})")
                            cursor_configured = True
                            cursor_install_type = install_type
                        else:
                            click.echo(f"⚠️  Failed to configure Cursor automatically, using manual setup")
                            cursor_install_type = "manual"
                    else:
                        cursor_install_type = "manual"
                else:
                    # Cursor not detected, provide manual setup
                    click.echo("⚠️  Cursor IDE not detected in PATH")
                    cursor_install_type = "manual"
                
                # Show the config content
                click.echo(f"\n📋 Cursor IDE Configuration:")
                click.echo(json.dumps(cursor_config, indent=2))
                
                # Always show the deeplink
                click.echo(f"\n🔗 One-Click Install Link:")
                click.echo(f"   {deeplink}")
                click.echo(f"\n   💡 Share this link to let others install your MXCP server with one click!")
                
                if cursor_install_type == "manual":
                    show_cursor_next_steps(project, cursor_install_type)
            else:
                click.echo("ℹ️  Skipped Cursor IDE configuration generation")
        except Exception as e:
            click.echo(f"⚠️  Warning: Failed to generate Cursor config: {e}")
            
        # Show next steps
        show_next_steps(target_dir, project, bootstrap, config_generated, cursor_configured, cursor_install_type)
            
    except Exception as e:
        output_error(e, json_output=False, debug=debug) 