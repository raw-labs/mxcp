"""Table rendering utilities for CLI output."""

import json
from typing import Any, Dict, List, Union

import click


def render_table(
    data: Union[List[Dict[str, Any]], List[Any]],
    title: str = "Results",
    max_rows: int = 100,
    max_col_width: int = 50,
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

    # Analyze data type composition
    dict_count = 0
    non_dict_count = 0
    sample_size = min(len(data), 100)  # Check first 100 items for performance

    for i in range(sample_size):
        if isinstance(data[i], dict):
            dict_count += 1
        else:
            non_dict_count += 1

    # Determine rendering strategy based on data composition
    if dict_count > 0 and non_dict_count == 0:
        # All sampled items are dicts - render as table
        # But first verify all dicts have consistent keys
        try:
            first_keys = set(data[0].keys())
            keys_consistent = True

            for i in range(1, sample_size):
                if set(data[i].keys()) != first_keys:
                    keys_consistent = False
                    break

            if keys_consistent:
                _render_dict_table(data, title, max_rows, max_col_width)
            else:
                # Inconsistent keys - fall back to primitive rendering
                click.echo(
                    f"\n{click.style('⚠️  Warning: Inconsistent dict keys found. Displaying as list.', fg='yellow')}"
                )
                _render_primitive_list(data, title, max_rows, max_col_width)
        except (AttributeError, TypeError):
            # Safety fallback if dict operations fail
            _render_primitive_list(data, title, max_rows, max_col_width)

    elif dict_count == 0 and non_dict_count > 0:
        # All sampled items are non-dicts - render as primitive list
        _render_primitive_list(data, title, max_rows, max_col_width)

    else:
        # Mixed types - warn and render as primitives
        click.echo(
            f"\n{click.style('⚠️  Warning: Mixed data types found. Displaying all as strings.', fg='yellow')}"
        )
        _render_primitive_list(data, title, max_rows, max_col_width)


def _render_primitive_list(data: List[Any], title: str, max_rows: int, max_col_width: int) -> None:
    """Render a list of primitive values."""
    click.echo(f"\n{click.style(f'📊 {title} ({len(data)} items):', fg='cyan', bold=True)}\n")

    # Calculate column width
    display_data = data[:max_rows]
    col_width = min(
        max(len(str(item)) for item in display_data) if display_data else 5, max_col_width
    )
    col_width = max(col_width, 5)  # Minimum width for "Value" header

    # Print header
    click.echo("Value")
    click.echo("─" * col_width)

    # Print values
    for item in display_data:
        value_str = str(item)
        if len(value_str) > max_col_width:
            value_str = value_str[: max_col_width - 3] + "..."
        click.echo(value_str)

    if len(data) > max_rows:
        click.echo(f"\n... and {len(data) - max_rows} more items")


def _render_dict_table(
    data: List[Dict[str, Any]], title: str, max_rows: int, max_col_width: int
) -> None:
    """Render a list of dictionaries as a table."""
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
            # Safely handle non-dict rows that might have slipped through
            if isinstance(row, dict):
                val_len = len(str(row.get(col, "")))
                if val_len > col_widths[col]:
                    col_widths[col] = val_len
        # Cap column width
        col_widths[col] = min(col_widths[col], max_col_width)

    # Print header
    header_parts = []
    for col in columns:
        header_parts.append(str(col).ljust(col_widths[col]))
    header = " │ ".join(header_parts)
    click.echo(header)
    click.echo("─" * len(header))

    # Print rows
    display_rows = data[:max_rows]
    for row in display_rows:
        # Skip non-dict rows as a safety measure
        if not isinstance(row, dict):
            continue

        row_parts = []
        for col in columns:
            val = str(row.get(col, ""))
            if len(val) > col_widths[col]:
                val = val[: col_widths[col] - 3] + "..."
            row_parts.append(val.ljust(col_widths[col]))
        click.echo(" │ ".join(row_parts))

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

        click.echo(json.dumps(result, indent=2, default=str))
    elif isinstance(result, (str, int, float, bool, type(None))):
        # Simple scalar value
        click.echo(f"\n{click.style('📋 Result:', fg='cyan', bold=True)} {result}")
    else:
        # Complex type - fall back to JSON
        click.echo(f"\n{click.style('📋 Result:', fg='cyan', bold=True)}\n")

        click.echo(json.dumps(result, indent=2, default=str))
