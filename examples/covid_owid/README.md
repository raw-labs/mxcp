# COVID-19 MCP Server Example

This example demonstrates how to create an MCP server that provides LLM-friendly access to COVID-19 data. It automatically fetches the latest [Our World in Data (OWID) COVID-19 dataset](https://ourworldindata.org/coronavirus) from GitHub, processes and caches it in a DuckDB database using dbt transformations, and exposes it through configurable endpoints for both direct queries and natural language interactions.

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
   pip install dbt-core duckdb
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

## Using the Server

### Direct Data Access
```bash
# Example: Query COVID data for a specific country
curl -X POST http://localhost:8080/owid-covid \
  -d '{"country_code": "USA", "start_date": "2022-01-01"}'
```

### Natural Language Queries
The LLM interface accepts questions in plain English:
```bash
# Example: Ask about COVID trends
curl -X POST http://localhost:8080/prompt \
  -d '{"question": "What were the peak cases in Germany during 2022?"}'
```

## Customizing the Server

### Adding New Endpoints
1. Create a new YAML file in `endpoints/`
2. Define the endpoint structure:
   ```yaml
   mxcp: 1.0.0
   tool:
     name: "endpoint_name"
     description: "Endpoint description"
     parameters:
       # Define parameters
     return:
       # Define return type
   ```

### Modifying the LLM Prompt
Edit `endpoints/prompt.yml` to:
- Adjust the system prompt
- Add new query capabilities
- Modify response formatting

## Resources

- [Raw MCP Documentation](https://raw-labs.com/)
- [Our World in Data COVID-19 Dataset](https://github.com/owid/covid-19-data)
- [DuckDB Documentation](https://duckdb.org/docs/)
- [dbt Documentation](https://docs.getdbt.com/)

## Contributing

Feel free to submit issues and enhancement requests!
