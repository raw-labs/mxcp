import click
from typing import Optional
from mxcp.cli.utils import output_result, output_error, configure_logging
from mxcp.config.analytics import track_command_with_timing
from mxcp.agent_help.navigator import HelpNavigator
from mxcp.agent_help.renderer import HelpRenderer

@click.command(name="agent-help")
@click.argument("path", nargs=-1)
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@track_command_with_timing("agent_help")
def agent_help(path: tuple, json_output: bool, debug: bool):
    """Hierarchical help system for AI agents.
    
    This command provides structured, task-oriented guidance that agents
    can navigate based on their specific requirements.
    
    \b
    Examples:
        mxcp agent-help                         # Show all categories
        mxcp agent-help getting-started         # Show getting started options
        mxcp agent-help endpoints tools         # Show tool creation help
        mxcp agent-help schemas configuration   # Show configuration schemas
        mxcp agent-help --json-output           # Output in JSON format
    """
    # Configure logging
    configure_logging(debug)
    
    try:
        # Convert tuple to list for easier handling
        path_list = list(path)
        
        # Create navigator and renderer
        navigator = HelpNavigator()
        renderer = HelpRenderer(json_output=json_output)
        
        # Get help content
        level, content = navigator.get_help_content(path_list)
        
        # Render and output
        result = renderer.render(level, content)
        
        if json_output:
            # For JSON output, we want to output the raw content
            output_result(content, json_output, debug)
        else:
            # For human output, we use the rendered text
            click.echo(result)
            
    except Exception as e:
        output_error(e, json_output, debug) 