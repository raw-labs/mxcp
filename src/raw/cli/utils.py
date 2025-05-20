import json
import traceback
from typing import Any, Dict, Optional
import click

def format_error(error: Exception, debug: bool = False) -> Dict[str, Any]:
    """Format an error for output.
    
    Args:
        error: The exception that occurred
        debug: Whether to include debug information
        
    Returns:
        Dict containing error information
    """
    error_info = {
        "error": str(error)
    }
    
    if debug:
        error_info["traceback"] = traceback.format_exc()
        error_info["type"] = error.__class__.__name__
    
    return error_info

def output_result(result: Any, json_output: bool = False, debug: bool = False) -> None:
    """Output a result in either JSON or human-readable format.
    
    Args:
        result: The result to output
        json_output: Whether to output in JSON format
        debug: Whether to include debug information
    """
    if json_output:
        print(json.dumps({
            "status": "ok",
            "result": result
        }, indent=2))
    else:
        if isinstance(result, list):
            for row in result:
                click.echo(row)
        else:
            click.echo(result)

def output_error(error: Exception, json_output: bool = False, debug: bool = False) -> None:
    """Output an error in either JSON or human-readable format.
    
    Args:
        error: The exception that occurred
        json_output: Whether to output in JSON format
        debug: Whether to include debug information
    """
    error_info = format_error(error, debug)
    
    if json_output:
        print(json.dumps({
            "status": "error",
            **error_info
        }, indent=2))
    else:
        click.echo(f"Error: {error_info['error']}", err=True)
        if debug and "traceback" in error_info:
            click.echo("\nTraceback:", err=True)
            click.echo(error_info["traceback"], err=True)
    
    raise click.Abort() 