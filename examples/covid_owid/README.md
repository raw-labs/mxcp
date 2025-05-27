# COVID-19 Data Analysis Project

This project demonstrates the integration of [Our World in Data (OWID)](https://ourworldindata.org/coronavirus) COVID-19 dataset with DuckDB and dbt. It showcases how to build a data pipeline that processes and analyzes global COVID-19 data using modern data tools.

## Overview

This example project:
- Fetches COVID-19 data directly from OWID's GitHub repository
- Processes the data using dbt and DuckDB
- Provides models for analyzing COVID-19 cases, hospitalizations, and location data
- Exposes the processed data through a REST API

## Prerequisites

- DuckDB
- dbt-core
- Python 3.8+
- Raw MCP CLI tools

## Project Structure

```
covid_owid/
├── models/              # dbt models for data transformation
│   ├── covid_data.sql      # Main COVID-19 data model
│   ├── hospitalizations.sql # Hospitalization metrics
│   └── locations.sql       # Location-specific data
├── endpoints/           # API endpoint definitions
├── tests/              # Data tests
└── mxcp-site.yml       # Raw MCP configuration
```

## Getting Started

1. Clone the repository and navigate to this example:
   ```bash
   cd examples/covid_owid
   ```

2. Start the Raw MCP server:
   ```bash
   mxcp serve
   ```

3. Run the dbt models:
   ```bash
   dbt run
   ```

4. Run the tests to ensure data quality:
   ```bash
   dbt test
   ```

## Data Models

- **covid_data**: Raw COVID-19 data from OWID
- **hospitalizations**: Filtered view of hospitalization metrics
- **locations**: Geographic and demographic information about locations

## API Endpoints

The processed data is available through REST API endpoints defined in the `endpoints/` directory. The server configuration is managed through `server_config.json`.

## Resources

- [Our World in Data COVID-19 Dataset](https://github.com/owid/covid-19-data)
- [dbt Documentation](https://docs.getdbt.com/)
- [DuckDB Documentation](https://duckdb.org/docs/)
- [Raw MCP Documentation](https://raw-labs.com/)
