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

### Prerequisites

Make sure you have MXCP installed:
```bash
# Option 1: Install globally
pip install mxcp

# Option 2: Install in development mode (if you cloned the repo)
cd /path/to/mxcp
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Running the Example

1. Navigate to the earthquakes example:
   ```bash
   cd examples/earthquakes
   ```

2. Start the MCP server:
   ```bash
   mxcp serve
   ```

## 🔌 Integration

### Claude Desktop

To use this example with Claude Desktop:

### 1. Locate Claude's Configuration

Find your Claude Desktop configuration file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

### 2. Configure the MCP Server

Add this configuration to your `claude_desktop_config.json`:

#### If you installed MXCP globally:
```json
{
  "mcpServers": {
    "earthquakes": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/absolute/path/to/mxcp/examples/earthquakes"
    }
  }
}
```

#### If you're using a virtual environment:
```json
{
  "mcpServers": {
    "earthquakes": {
      "command": "/bin/bash",
      "args": [
        "-c",
        "cd /absolute/path/to/mxcp/examples/earthquakes && source ../../.venv/bin/activate && mxcp serve --transport stdio"
      ]
    }
  }
}
```

**Important**: Replace `/absolute/path/to/mxcp` with the actual path to your MXCP installation.

### 3. Restart Claude Desktop

After saving the configuration, restart Claude Desktop to load the new MCP server.

### 4. Test the Integration

In Claude Desktop, try asking:
- "Show me recent earthquakes above magnitude 5.0"
- "What was the strongest earthquake in the last 24 hours?"
- "List earthquakes near California"

Claude will automatically use the earthquake data tools to answer your questions.

### Cursor

To use this example with Cursor:

#### Option 1: Automatic Setup (Recommended)

Run `mxcp init .` in the earthquakes directory and follow the prompts to automatically configure Cursor.

#### Option 2: Manual Setup

1. **Locate Cursor's Configuration**:
   - **Project-specific**: Create `.cursor/mcp.json` in the earthquakes directory
   - **Global**: `~/.cursor/mcp.json` in your home directory

2. **Add Configuration**:

   For global installations:
   ```json
   {
     "mcpServers": {
       "earthquakes": {
         "command": "mxcp",
         "args": ["serve", "--transport", "stdio"],
         "cwd": "/absolute/path/to/mxcp/examples/earthquakes"
       }
     }
   }
   ```

   For virtual environment installations:
   ```json
   {
     "mcpServers": {
       "earthquakes": {
         "command": "/bin/bash",
         "args": [
           "-c",
           "cd /absolute/path/to/mxcp/examples/earthquakes && source ../../.venv/bin/activate && mxcp serve --transport stdio"
         ]
       }
     }
   }
   ```

3. **Test the Integration**:

In Cursor, try asking:
- "Show me recent earthquakes above magnitude 5.0"
- "What was the strongest earthquake in the last 24 hours?"
- "List earthquakes near California"

## 🛠️ Other MCP Clients

This example also works with other MCP-compatible tools:

- **mcp-cli**: `pip install mcp-cli` then use the same server config
- **Custom integrations**: Use the MCP specification to build your own client

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