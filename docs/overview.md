# MXCP Overview

MXCP (Model Execution + Context Protocol) is a developer-first toolkit that enables you to serve your operational data to AI applications through a well-governed, testable interface. It combines the power of SQL, the flexibility of DuckDB, and the reliability of dbt to create a complete solution for AI data integration.

## Core Architecture

MXCP is built around three key components that work together seamlessly:

```
┌────────┐      ┌────────┐      ┌────────────┐
│  dbt   ├─────►│ DuckDB │◄─────┤  MXCP CLI  │
└────────┘      └────────┘      └────────────┘
     ▲                                ▲
     │                                │
  Git repo                    ~/.mxcp/config.yml
                              + mxcp-site.yml
```

### 1. DuckDB: The Execution Engine

DuckDB serves as the runtime engine of MXCP, providing:

- **Native Analytics Support**: Built-in capabilities for OLAP-style analytics and columnar data formats (Parquet, CSV, JSON)
- **Python Integration**: Support for Python UDFs via embedded extensions
- **Local-First Development**: File-based persistence with no server required
- **Flexible I/O**: Native support for various data sources and formats
- **Extensible**: Support for core, community, and nightly extensions (e.g., httpfs, parquet, h3)

DuckDB's architecture makes it ideal for operational workloads, with MXCP automatically injecting necessary extensions, secrets, and Python functions.

### 2. dbt: The Transformation Layer

dbt provides the ETL capabilities in MXCP:

- **Declarative Transformations**: Define data models as views or materialized tables
- **SQL-Based**: Express transformations in standard SQL
- **Git-Managed**: Version control for all data transformations
- **DuckDB Integration**: Native support via dbt-duckdb adapter
- **Caching Strategies**: Use dbt materializations and DuckDB tables for performance optimization

### 3. MXCP CLI: The Orchestration Layer

The MXCP CLI ties everything together:

- **Project Management**: Reads project definitions (`mxcp-site.yml`) and configuration
- **MCP Server**: Serves endpoints as an MCP-compatible HTTP interface
- **Validation**: Validates endpoint definitions and runs tests
- **Integration**: Seamless integration with dbt and Python
- **Flexible Deployment**: Works locally, in CI/CD, or as a managed service

## Key Features

### 1. Local-First Development

- Clone a repository, run `mxcp serve`, and you're ready to go
- No external services or coordination layers required
- Full development environment in a single command

### 2. Declarative Interface Definition

- Define tools, resources, and prompts in YAML
- Version control all definitions in Git
- Test and validate changes before deployment

### 3. Production-Ready Features

- Type safety and schema validation
- Comprehensive testing framework
- Integration with existing data pipelines
- Support for secrets management

### 4. Flexible Deployment

- Run locally for development
- Deploy in CI/CD pipelines
- Use as a managed service
- Scale from development to production

## Getting Started

1. Install MXCP:
   ```bash
   pip install mxcp
   ```

2. Create a new project:
   ```bash
   mxcp init
   ```

3. Define your endpoints in YAML:
   ```yaml
   # tools/example.yml
   name: example_tool
   type: tool
   input:
     date: date
   output:
     result: string
   sql: |
     SELECT 'Result for ' || :date AS result
   ```

4. Start the server:
   ```bash
   mxcp serve
   ```

## Next Steps

- [Quickstart Guide](quickstart.md) - Get up and running with MXCP
- [Type System](type-system.md) - Learn about MXCP's type system
- [Configuration](configuration.md) - Configure your MXCP project
- [Authentication](authentication.md) - Set up OAuth authentication
- [CLI Reference](cli.md) - Explore available commands
- [Integrations](integrations.md) - Connect with other tools and services 