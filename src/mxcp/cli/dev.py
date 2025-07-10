import click
import subprocess
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from mxcp.config.site_config import load_site_config, find_repo_root
from mxcp.config.user_config import load_user_config
from mxcp.cli.utils import output_error, configure_logging
from mxcp.config.analytics import track_command_with_timing
import logging

logger = logging.getLogger(__name__)

@click.group(name='dev')
def dev():
    """Development lifecycle commands."""
    pass

def load_lifecycle_config(site_config: Dict[str, Any]) -> Dict[str, Any]:
    """Load lifecycle configuration from site config.
    
    Args:
        site_config: The loaded site configuration
        
    Returns:
        The lifecycle configuration section
        
    Raises:
        click.ClickException: If no lifecycle config is found
    """
    lifecycle = site_config.get('lifecycle', {})
    
    if not lifecycle:
        raise click.ClickException(
            "No lifecycle configuration found in mxcp-site.yml. "
            "Add a 'lifecycle' section to define commands."
        )
    
    return lifecycle

def run_command(cmd: str, cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None, 
                dry_run: bool = False, verbose: bool = False) -> subprocess.CompletedProcess:
    """Execute a command with proper error handling.
    
    Args:
        cmd: Command to execute
        cwd: Working directory for command execution
        env: Environment variables
        dry_run: If True, only print what would be executed
        verbose: If True, show command output in real-time
        
    Returns:
        The completed process result
        
    Raises:
        click.ClickException: If command fails
    """
    if dry_run:
        click.echo(f"[DRY RUN] Would execute: {cmd}")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    
    try:
        # Prepare environment
        cmd_env = os.environ.copy()
        if env:
            cmd_env.update(env)
        
        # For cross-platform compatibility
        if sys.platform == "win32":
            # Windows: use shell=True with default shell
            if verbose:
                result = subprocess.run(cmd, shell=True, cwd=cwd, env=cmd_env, check=False)
            else:
                result = subprocess.run(cmd, shell=True, cwd=cwd, env=cmd_env, 
                                      capture_output=True, text=True, check=False)
        else:
            # Unix-like: use bash explicitly if available
            shell_executable = '/bin/bash' if Path('/bin/bash').exists() else None
            if verbose:
                result = subprocess.run(cmd, shell=True, cwd=cwd, env=cmd_env, 
                                      executable=shell_executable, check=False)
            else:
                result = subprocess.run(cmd, shell=True, cwd=cwd, env=cmd_env,
                                      capture_output=True, text=True, 
                                      executable=shell_executable, check=False)
        
        if result.returncode != 0:
            error_msg = f"Command failed with exit code {result.returncode}: {cmd}"
            if not verbose and result.stderr:
                error_msg += f"\nError output:\n{result.stderr}"
            raise click.ClickException(error_msg)
        
        return result
        
    except Exception as e:
        if isinstance(e, click.ClickException):
            raise
        raise click.ClickException(f"Failed to execute command: {str(e)}")

def check_required_env(required_vars: List[str]) -> None:
    """Check if required environment variables are set.
    
    Args:
        required_vars: List of required environment variable names
        
    Raises:
        click.ClickException: If any required variables are missing
    """
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        raise click.ClickException(
            f"Missing required environment variables: {', '.join(missing)}"
        )

def run_command_list(commands: List[Union[str, Dict[str, Any]]], description: Optional[str] = None,
                    dry_run: bool = False, verbose: bool = False, cwd: Optional[Path] = None) -> None:
    """Run a list of commands with progress reporting.
    
    Args:
        commands: List of commands (strings or dicts with 'command' and optional 'name')
        description: Optional description to show before running
        dry_run: If True, only show what would be executed
        verbose: If True, show command output
        cwd: Working directory for commands
    """
    if description:
        click.echo(f"\n{click.style(description, bold=True)}")
    
    for i, cmd_config in enumerate(commands, 1):
        if isinstance(cmd_config, str):
            cmd = cmd_config
            name = cmd
            condition = None
        else:
            cmd = cmd_config['command']
            name = cmd_config.get('name', cmd)
            condition = cmd_config.get('condition')
        
        # Check condition if present
        if condition and condition.startswith('if_not_exists:'):
            check_path = Path(condition.split(':', 1)[1])
            if cwd:
                check_path = cwd / check_path
            if check_path.exists():
                click.echo(f"\n[{i}/{len(commands)}] {name} - Skipped (condition: {check_path} exists)")
                continue
        
        click.echo(f"\n[{i}/{len(commands)}] {name}")
        
        if not dry_run:
            with click.progressbar(length=1, label='Running...', show_percent=False) as bar:
                run_command(cmd, cwd=cwd, dry_run=dry_run, verbose=verbose)
                bar.update(1)
        else:
            run_command(cmd, cwd=cwd, dry_run=dry_run, verbose=verbose)

@dev.command(name='setup')
@click.option('--dry-run', is_flag=True, help='Show what would be executed without running')
@click.option('--verbose', '-v', is_flag=True, help='Show command output')
@click.option('--debug', is_flag=True, help='Show detailed debug information')
@click.pass_context
@track_command_with_timing("dev_setup")
def dev_setup(ctx, dry_run: bool, verbose: bool, debug: bool):
    """Run project setup commands."""
    configure_logging(debug)
    
    try:
        # Load configurations
        repo_root = find_repo_root()
        site_config = load_site_config(repo_root)
        lifecycle = load_lifecycle_config(site_config)
        
        setup_config = lifecycle.get('setup', {})
        if not setup_config:
            raise click.ClickException("No setup configuration found in lifecycle section")
        
        description = setup_config.get('description', 'Running setup commands')
        commands = setup_config.get('commands', [])
        
        if not commands:
            click.echo("No setup commands defined")
            return
        
        # Run the setup commands
        run_command_list(commands, description, dry_run, verbose, repo_root)
        
        if not dry_run:
            click.echo(f"\n{click.style('✅ Setup completed successfully!', fg='green', bold=True)}")
        
    except Exception as e:
        output_error(e, False, debug)
        ctx.exit(1)

@dev.command(name='test')
@click.option('--level', type=click.Choice(['light', 'full', 'unit']), default='light',
              help='Test level to run')
@click.option('--dry-run', is_flag=True, help='Show what would be executed without running')
@click.option('--verbose', '-v', is_flag=True, help='Show command output')
@click.option('--debug', is_flag=True, help='Show detailed debug information')
@click.pass_context
@track_command_with_timing("dev_test")
def dev_test(ctx, level: str, dry_run: bool, verbose: bool, debug: bool):
    """Run project tests."""
    configure_logging(debug)
    
    try:
        # Load configurations
        repo_root = find_repo_root()
        site_config = load_site_config(repo_root)
        lifecycle = load_lifecycle_config(site_config)
        
        test_config = lifecycle.get('test', {})
        if not test_config:
            raise click.ClickException("No test configuration found in lifecycle section")
        
        # Handle both old format (test levels as direct children) and new format
        if level in test_config:
            level_config = test_config[level]
        else:
            # Fallback to a default test configuration if level not found
            click.echo(f"Warning: Test level '{level}' not found, using default test commands")
            level_config = {
                'description': f'Running {level} tests',
                'commands': test_config.get('commands', [])
            }
        
        if isinstance(level_config, dict):
            description = level_config.get('description', f'Running {level} tests')
            commands = level_config.get('commands', [])
        else:
            # Handle legacy format where level_config might be a list
            description = f'Running {level} tests'
            commands = level_config if isinstance(level_config, list) else []
        
        if not commands:
            click.echo(f"No {level} test commands defined")
            return
        
        # Run the test commands
        run_command_list(commands, description, dry_run, verbose, repo_root)
        
        if not dry_run:
            click.echo(f"\n{click.style('✅ Tests completed successfully!', fg='green', bold=True)}")
        
    except Exception as e:
        output_error(e, False, debug)
        ctx.exit(1)

@dev.command(name='deploy')
@click.option('--target', required=True, help='Deployment target')
@click.option('--dry-run', is_flag=True, help='Show what would be executed without running')
@click.option('--verbose', '-v', is_flag=True, help='Show command output')
@click.option('--debug', is_flag=True, help='Show detailed debug information')
@click.pass_context
@track_command_with_timing("dev_deploy")
def dev_deploy(ctx, target: str, dry_run: bool, verbose: bool, debug: bool):
    """Deploy project to specified target."""
    configure_logging(debug)
    
    try:
        # Load configurations
        repo_root = find_repo_root()
        site_config = load_site_config(repo_root)
        lifecycle = load_lifecycle_config(site_config)
        
        deploy_config = lifecycle.get('deploy', {})
        if not deploy_config:
            raise click.ClickException("No deploy configuration found in lifecycle section")
        
        targets = deploy_config.get('targets', {})
        if target not in targets:
            available = ', '.join(targets.keys())
            raise click.ClickException(
                f"Unknown deployment target '{target}'. Available targets: {available}"
            )
        
        target_config = targets[target]
        description = target_config.get('description', f'Deploying to {target}')
        commands = target_config.get('commands', [])
        
        # Check environment variables if specified
        env_config = target_config.get('environment', {})
        required_env = env_config.get('required', [])
        if required_env and not dry_run:
            check_required_env(required_env)
        
        if not commands:
            click.echo(f"No deployment commands defined for target '{target}'")
            return
        
        # Run the deployment commands
        run_command_list(commands, description, dry_run, verbose, repo_root)
        
        if not dry_run:
            click.echo(f"\n{click.style('✅ Deployment completed successfully!', fg='green', bold=True)}")
        
    except Exception as e:
        output_error(e, False, debug)
        ctx.exit(1)

@dev.command(name='run')
@click.argument('command_name')
@click.option('--dry-run', is_flag=True, help='Show what would be executed without running')
@click.option('--verbose', '-v', is_flag=True, help='Show command output')
@click.option('--debug', is_flag=True, help='Show detailed debug information')
@click.pass_context
@track_command_with_timing("dev_run")
def dev_run(ctx, command_name: str, dry_run: bool, verbose: bool, debug: bool):
    """Run a custom lifecycle command."""
    configure_logging(debug)
    
    try:
        # Load configurations
        repo_root = find_repo_root()
        site_config = load_site_config(repo_root)
        lifecycle = load_lifecycle_config(site_config)
        
        custom_config = lifecycle.get('custom', {})
        if not custom_config:
            raise click.ClickException("No custom commands found in lifecycle section")
        
        if command_name not in custom_config:
            available = ', '.join(custom_config.keys())
            raise click.ClickException(
                f"Unknown custom command '{command_name}'. Available commands: {available}"
            )
        
        cmd_config = custom_config[command_name]
        description = cmd_config.get('description', f'Running {command_name}')
        commands = cmd_config.get('commands', [])
        
        if not commands:
            click.echo(f"No commands defined for '{command_name}'")
            return
        
        # Run the custom commands
        run_command_list(commands, description, dry_run, verbose, repo_root)
        
        if not dry_run:
            click.echo(f"\n{click.style('✅ Command completed successfully!', fg='green', bold=True)}")
        
    except Exception as e:
        output_error(e, False, debug)
        ctx.exit(1)

@dev.command(name='list')
@click.option('--debug', is_flag=True, help='Show detailed debug information')
@click.pass_context
@track_command_with_timing("dev_list")
def dev_list(ctx, debug: bool):
    """List all available lifecycle commands."""
    configure_logging(debug)
    
    try:
        # Load configurations
        repo_root = find_repo_root()
        site_config = load_site_config(repo_root)
        
        # Check if lifecycle config exists
        lifecycle = site_config.get('lifecycle', {})
        if not lifecycle:
            click.echo("No lifecycle configuration found in mxcp-site.yml")
            click.echo("\nAdd a 'lifecycle' section to define commands. Example:")
            click.echo("""
lifecycle:
  setup:
    description: "Initialize project"
    commands:
      - "pip install -r requirements.txt"
  test:
    light:
      description: "Run quick tests"
      commands:
        - "mxcp test"
""")
            return
        
        click.echo(click.style("Available Lifecycle Commands", bold=True, fg='cyan'))
        click.echo("=" * 40)
        
        # List setup commands
        if 'setup' in lifecycle:
            setup = lifecycle['setup']
            desc = setup.get('description', 'No description')
            click.echo(f"\n{click.style('Setup:', bold=True)}")
            click.echo(f"  {desc}")
            click.echo(f"  Run: {click.style('mxcp dev setup', fg='green')}")
        
        # List test levels
        if 'test' in lifecycle:
            test = lifecycle['test']
            click.echo(f"\n{click.style('Test Levels:', bold=True)}")
            for level in ['light', 'full', 'unit']:
                if level in test:
                    level_config = test[level]
                    if isinstance(level_config, dict):
                        desc = level_config.get('description', f'{level} tests')
                    else:
                        desc = f'{level} tests'
                    click.echo(f"  {level}: {desc}")
                    click.echo(f"    Run: {click.style(f'mxcp dev test --level {level}', fg='green')}")
        
        # List deployment targets
        if 'deploy' in lifecycle and 'targets' in lifecycle['deploy']:
            targets = lifecycle['deploy']['targets']
            click.echo(f"\n{click.style('Deployment Targets:', bold=True)}")
            for target, config in targets.items():
                desc = config.get('description', 'No description')
                click.echo(f"  {target}: {desc}")
                click.echo(f"    Run: {click.style(f'mxcp dev deploy --target {target}', fg='green')}")
        
        # List custom commands
        if 'custom' in lifecycle:
            custom = lifecycle['custom']
            click.echo(f"\n{click.style('Custom Commands:', bold=True)}")
            for cmd_name, config in custom.items():
                desc = config.get('description', 'No description')
                click.echo(f"  {cmd_name}: {desc}")
                click.echo(f"    Run: {click.style(f'mxcp dev run {cmd_name}', fg='green')}")
        
        click.echo(f"\n{click.style('Tip:', fg='yellow')} Use --dry-run flag to preview commands without executing them")
        
    except Exception as e:
        output_error(e, False, debug)
        ctx.exit(1) 