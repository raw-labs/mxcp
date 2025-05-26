# Earthquakes Example

This example demonstrates how to use MXCP to create a real-time earthquake data API. It shows how to:
- Query live earthquake data from the USGS API
- Transform JSON data using SQL
- Create type-safe endpoints for LLM consumption

## Features

- **Real-time Data**: Fetches the latest earthquake data from USGS
- **Type Safety**: Strong typing for LLM safety
- **SQL Transformations**: Complex JSON parsing and data transformation
- **Test Coverage**: Includes example tests

## Getting Started

1. Start the MCP server:
   ```bash
   mxcp serve
   ```

2. Connect using your preferred MCP client:
   - [Claude Desktop](https://docs.anthropic.com/claude/docs/claude-desktop)
   - [mcp-cli](https://github.com/chrishayuk/mcp-cli)

## Example Usage

Ask your LLM to:
- "Show me recent earthquakes above magnitude 5.0"
- "What was the strongest earthquake in the last 24 hours?"
- "List earthquakes near [location]"

## Implementation Details

The example uses:
- DuckDB's `read_json_auto` function to parse USGS GeoJSON
- SQL window functions for data analysis
- Type-safe parameters for filtering

For more details on:
- Type system: See [Type System Documentation](../../docs/type-system.md)
- SQL capabilities: See [Integrations Documentation](../../docs/integrations.md)
- Configuration: See [Configuration Guide](../../docs/configuration.md)

## Project Structure

```
earthquakes/
├── endpoints/
│   └── tool.yml      # Endpoint definition
├── mxcp-site.yml     # Project configuration
└── tests/            # Example tests
```

## Learn More

- [Quickstart Guide](../../docs/quickstart.md) - Get started with MXCP
- [CLI Reference](../../docs/cli.md) - Available commands
- [Configuration](../../docs/configuration.md) - Project setup 