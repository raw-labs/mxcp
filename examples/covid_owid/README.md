# COVID-19 MCP Server Example

This example demonstrates how to create an MCP server that provides LLM-friendly access to COVID-19 data. It automatically fetches the latest [Our World in Data (OWID) COVID-19 dataset](https://ourworldindata.org/coronavirus) from GitHub, processes and caches it using dbt transformations, and exposes it through configurable endpoints for both direct queries and natural language interactions.

## What This Example Shows

1. **Data Pipeline**:
   - Fetching data from OWID's GitHub repository
   - Data transformation and caching using dbt models

2. **MCP Server Setup**:
   - How to configure MCP endpoints for data access
   - How to create an LLM-friendly prompt for natural language queries
   - How to expose DuckDB data through MCP tools.

3. **Data Sources**:
   - COVID-19 cases and deaths
   - Vaccination data
   - Hospitalization statistics
   - Country-specific information

## Prerequisites

- Raw MCP CLI tools (`mxcp`)
- dbt-core
- dbt-duckdb
- Python 3.8 or higher

## Project Structure

```
covid_owid/
├── endpoints/                # MCP endpoint definitions
│   ├── prompt.yml           # LLM system prompt for natural language queries
│   ├── hospitalizations.yml # Hospital data endpoint
│   └── owid-covid.yml      # Main COVID data endpoint
├── models/                  # Data models
│   ├── covid_data.sql      # Main COVID-19 statistics
│   ├── hospitalizations.sql # Hospital/ICU data
│   └── locations.sql       # Geographic data
├── mxcp-site.yml           # MCP site configuration
├── dbt_project.yml         # dbt configuration
└── server_config.json      # Server configuration
```

## Quick Start

1. **Setup**:
   ```bash
   # Navigate to the example
   cd examples/covid_owid

   # Install dependencies
   pip install dbt-core dbt-duckdb
   ```

2. **Prepare the Data**:
   ```bash
   # Initialize and run dbt models to populate DuckDB
   dbt deps
   dbt run
   ```

3. **Start MCP Server**:
   ```bash
   # Start the server
   mxcp serve
   ```

## Using the Server

### Server Configuration
First, create a `server_config.json` file:

```json
{
  "mcpServers": {
    "local": {
      "command": "bash",
      "args": [
        "-c",
        "cd /path/to/raw-mcp/examples/covid_owid && source ../../.venv/bin/activate && mxcp serve --transport stdio"
      ],
      "env": {
        "PATH": "/path/to/raw-mcp/.venv/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/home/user"
      }
    }
  }
}
```

### Using MCP CLI
Once your server is configured, you can interact with it using the MCP CLI:

```bash
# Start an interactive session
mcp-cli --config-file ./server_config.json
```

The CLI will use the LLM to interpret your questions and return formatted results.

## MCP Endpoint Structure

The server provides three types of endpoints:

1. **Data Exploration Endpoints**:
   - `list_tables`: View available tables
   - `get_table_schema`: Examine table structures
   - `execute_sql_query`: Run custom SQL queries

2. **LLM Interface** (`prompt.yml`):
   - Handles natural language queries
   - Converts questions to SQL
   - Formats responses for users

3. **Specialized Data Access**:
   - `owid-covid.yml`: Core COVID-19 statistics
   - `hospitalizations.yml`: Hospital metrics

## Resources

- [Our World in Data COVID-19 Dataset](https://github.com/owid/covid-19-data)
- [DuckDB Documentation](https://duckdb.org/docs/)
- [dbt Documentation](https://docs.getdbt.com/)

## Contributing

Feel free to submit issues and enhancement requests!
