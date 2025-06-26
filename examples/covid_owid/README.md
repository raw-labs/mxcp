# COVID-19 OWID Example

This example demonstrates how to use MXCP to create a COVID-19 data analysis API. It shows how to:
- Fetch and cache COVID-19 data from Our World in Data (OWID)
- Transform data using dbt and DuckDB
- Create a natural language interface for data exploration using generic SQL tools

## Features

- **Comprehensive Data**: Global COVID-19 statistics from OWID
- **Data Transformation**: dbt models for efficient querying
- **Natural Language**: LLM-friendly query interface (prompt only)

## Getting Started

### Prerequisites

Make sure you have the required tools installed:
```bash
# Install MXCP and dependencies
pip install mxcp dbt-core dbt-duckdb

# Option: Install in development mode
cd /path/to/mxcp
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Running the Example

1. Navigate to the COVID example:
   ```bash
   cd examples/covid_owid
   ```

2. Initialize the data:
   ```bash
   dbt deps
   dbt run
   ```

3. Start the MCP server:
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
    "covid": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/absolute/path/to/mxcp/examples/covid_owid"
    }
  }
}
```

#### If you're using a virtual environment:
```json
{
  "mcpServers": {
    "covid": {
      "command": "/bin/bash",
      "args": [
        "-c",
        "cd /absolute/path/to/mxcp/examples/covid_owid && source ../../.venv/bin/activate && mxcp serve --transport stdio"
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
- "Show me COVID-19 cases in the United States for 2022"
- "Compare vaccination rates between France and Germany"
- "What were the peak hospitalization rates in the UK?"

### Cursor

To use this example with Cursor:

#### Option 1: Automatic Setup (Recommended)

Run `mxcp init .` in the covid_owid directory and follow the prompts to automatically configure Cursor.

#### Option 2: Manual Setup

1. **Locate Cursor's Configuration**:
   - **Project-specific**: Create `.cursor/mcp.json` in the covid_owid directory
   - **Global**: `~/.cursor/mcp.json` in your home directory

2. **Add Configuration**:

   For global installations:
   ```json
   {
     "mcpServers": {
       "covid": {
         "command": "mxcp",
         "args": ["serve", "--transport", "stdio"],
         "cwd": "/absolute/path/to/mxcp/examples/covid_owid"
       }
     }
   }
   ```

   For virtual environment installations:
   ```json
   {
     "mcpServers": {
       "covid": {
         "command": "/bin/bash",
         "args": [
           "-c",
           "cd /absolute/path/to/mxcp/examples/covid_owid && source ../../.venv/bin/activate && mxcp serve --transport stdio"
         ]
       }
     }
   }
   ```

3. **Test the Integration**:

In Cursor, try asking:
- "Show me COVID-19 cases in the United States for 2022"
- "Compare vaccination rates between France and Germany"
- "What were the peak hospitalization rates in the UK?"

## 🛠️ Other MCP Clients

This example works with any MCP-compatible tool:
- **mcp-cli**: Interactive command-line interface
- **Custom integrations**: Build your own using the MCP specification

## Example Usage

The LLM can help you analyze:
- Case numbers and death rates
- Vaccination progress
- Hospital occupancy
- Regional comparisons
- Policy effectiveness

All queries are handled through the generic SQL query interface. You can:
- Use `list_tables` to see available tables
- Use `get_table_schema` to inspect table structure
- Use `execute_sql_query` to run custom SQL queries

## Implementation Details

The example uses:
- dbt for data transformation
- DuckDB for efficient storage and querying
- SQL analytics for complex calculations
- Type-safe parameters for filtering

## Project Structure

```
covid_owid/
├── endpoints/                # MCP endpoint definitions
│   └── prompt.yml           # LLM system prompt (generic query interface only)
├── models/                  # dbt transformations
│   ├── covid_data.sql      # Main COVID-19 statistics
│   ├── hospitalizations.sql # Hospital/ICU data
│   └── locations.sql       # Geographic data
├── mxcp-site.yml           # MCP configuration
└── dbt_project.yml         # dbt configuration
```

## Learn More

- [OWID COVID-19 Data](https://github.com/owid/covid-19-data) - Data source
- [dbt Documentation](https://docs.getdbt.com/) - Data transformation
- [DuckDB Documentation](https://duckdb.org/docs/) - Database engine
- [MXCP Documentation](../../docs/quickstart.md) - MCP framework
