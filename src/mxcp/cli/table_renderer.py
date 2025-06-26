"""Table rendering utilities for CLI output."""
import click
from typing import List, Dict, Any, Union


def render_table(
    data: Union[List[Dict[str, Any]], List[Any]], 
    title: str = "Results",
    max_rows: int = 100,
    max_col_width: int = 50
) -> None:
    """Render data as a table in the CLI.
    
    Args:
        data: Either list of dicts (tabular) or list of primitives
        title: Title for the table
        max_rows: Maximum rows to display
        max_col_width: Maximum column width
    """
    if not data:
        click.echo(f"\n{click.style(f'📊 {title} (0 items)', fg='cyan', bold=True)}")
        return
    
    # Check if it's a list of primitives (not dicts)
    if data and not isinstance(data[0], dict):
        # Single column table for primitives
        click.echo(f"\n{click.style(f'📊 {title} ({len(data)} items):', fg='cyan', bold=True)}\n")
        
        # Calculate column width
        display_data = data[:max_rows]
        col_width = min(
            max(len(str(item)) for item in display_data) if display_data else 5,
            max_col_width
        )
        col_width = max(col_width, 5)  # Minimum width for "Value" header
        
        # Print header
        click.echo("Value")
        click.echo("─" * col_width)
        
        # Print values
        for item in display_data:
            value_str = str(item)
            if len(value_str) > max_col_width:
                value_str = value_str[:max_col_width-3] + "..."
            click.echo(value_str)
        
        if len(data) > max_rows:
            click.echo(f"\n... and {len(data) - max_rows} more items")
        return
    
    # Handle list of dicts (tabular data)
    click.echo(f"\n{click.style(f'📊 {title} ({len(data)} rows):', fg='cyan', bold=True)}\n")
    
    # Get column names from first row
    columns = list(data[0].keys())
    
    # Calculate column widths
    col_widths = {}
    for col in columns:
        # Start with column name length
        col_widths[col] = len(str(col))
        # Check data widths (limit to first max_rows for performance)
        for row in data[:max_rows]:
            val_len = len(str(row.get(col, '')))
            if val_len > col_widths[col]:
                col_widths[col] = val_len
        # Cap column width
        col_widths[col] = min(col_widths[col], max_col_width)
    
    # Print header
    header_parts = []
    for col in columns:
        header_parts.append(str(col).ljust(col_widths[col]))
    header = ' │ '.join(header_parts)
    click.echo(header)
    click.echo('─' * len(header))
    
    # Print rows
    display_rows = data[:max_rows]
    for row in display_rows:
        row_parts = []
        for col in columns:
            val = str(row.get(col, ''))
            if len(val) > col_widths[col]:
                val = val[:col_widths[col]-3] + '...'
            row_parts.append(val.ljust(col_widths[col]))
        click.echo(' │ '.join(row_parts))
    
    if len(data) > max_rows:
        click.echo(f"\n... and {len(data) - max_rows} more rows")


def format_result_for_display(result: Any, max_rows: int = 100) -> None:
    """Format and display any result type nicely.
    
    Args:
        result: The result to display
        max_rows: Maximum rows to display for lists
    """
    if isinstance(result, list) and result:
        # Use table rendering for lists
        render_table(result, max_rows=max_rows)
    elif isinstance(result, dict):
        # Pretty print single dict
        click.echo(f"\n{click.style('📋 Result:', fg='cyan', bold=True)}\n")
        import json
        click.echo(json.dumps(result, indent=2, default=str))
    elif isinstance(result, (str, int, float, bool, type(None))):
        # Simple scalar value
        click.echo(f"\n{click.style('📋 Result:', fg='cyan', bold=True)} {result}")
    else:
        # Complex type - fall back to JSON
        click.echo(f"\n{click.style('📋 Result:', fg='cyan', bold=True)}\n")
        import json
        click.echo(json.dumps(result, indent=2, default=str)) 