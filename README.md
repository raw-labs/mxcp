# MXCP: Instantly Serve Your Operational Data to LLMs — Safely

<div align="center">

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-BSL-green.svg)](LICENSE)

**Transform your data into AI-ready interfaces in minutes, not months**

</div>

## ✨ Why MXCP?

MXCP (Model eXecution + Context Protocol) is a developer-first tool that bridges the gap between your operational data and AI applications. It lets you:

- 🚀 **Go from data to AI in minutes** — Define interfaces in YAML + SQL, serve instantly
- 🔒 **Keep control of your data** — Run locally, with full observability and type safety
- 🎯 **Build production-ready AI tools** — Combine real-time data, caching, and business logic
- 🛠️ **Use familiar tools** — DuckDB for execution, dbt for modeling, Git for versioning

## 🚀 Quick Start

```bash
# Install globally
pip install mxcp

# Install with Vault support (optional)
pip install "mxcp[vault]"

# Or develop locally
git clone https://github.com/raw-labs/mxcp.git && cd mxcp
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Try the included Earthquakes example:
```bash
cd examples/earthquakes
mxcp serve
```

## 💡 Key Features

### 1. Declarative Interface Definition
```yaml
# tools/summarize_earthquakes.yml
mxcp: "1.0.0"
tool:
  name: summarize_earthquakes
  description: "Summarize earthquakes for a given date"
  parameters:
    - name: date
      type: string
      format: date
      description: "Date to summarize earthquakes for"
  return:
    type: object
    properties:
      summary:
        type: string
        description: "Summary of earthquakes for the date"
  source:
    code: |
      SELECT 'Summary for ' || $date || ': ' || COUNT(*) || ' earthquakes' AS summary
      FROM earthquakes
      WHERE event_date = $date
```

- **Type-safe** — Strong typing for LLM safety and schema tracing
- **Fast restart** — Quick server restarts for development
- **dbt integration** — Directly use your dbt models in endpoints

### 2. Powerful Data Engine
- **DuckDB-powered** — Run instantly, with no infrastructure
- **Rich integrations** — PostgreSQL, Parquet, CSV, JSON, HTTP, S3, and more
- **Full SQL support** — Joins, filters, aggregations, UDFs

### 3. Production-Ready Features
- **dbt integration** — Use your data models directly
- **Git-based workflow** — Version control and collaboration
- **Validation tools** — Type checking, SQL linting, and testing
- **Drift detection** — Monitor schema and endpoint changes across environments

## 🛠️ Core Concepts

### Tools, Resources, Prompts
Define your AI interface using MCP (Model Context Protocol) specs:
- **Tools** — Functions that process data and return results
- **Resources** — Data sources and caches
- **Prompts** — Templates for LLM interactions

### Project Structure
```
your-project/
├── mxcp-site.yml    # Project configuration
├── tools/           # Tool definitions
├── resources/       # Data sources
├── prompts/         # LLM templates
└── models/          # (Optional) dbt transformations & caches
```

### CLI Commands
```bash
mxcp serve           # Start local MCP server
mxcp list            # List all endpoints
mxcp validate        # Check types, SQL, and references
mxcp test            # Run endpoint tests
mxcp query           # Execute SQL queries
mxcp init            # Initialize new project
mxcp dbt-config      # Configure dbt integration
mxcp dbt             # Run dbt commands
mxcp drift-snapshot  # Create drift detection baseline
mxcp drift-check     # Check for schema and endpoint drift
mxcp log             # Query audit logs
```

## 🔌 LLM Integration

MXCP implements the Model Context Protocol (MCP), making it compatible with:

- **Claude Desktop** — Native MCP support
- **OpenAI-compatible tools** — Via MCP adapters
- **Custom integrations** — Using the MCP specification

For specific setup instructions, see:
- [Earthquakes Example](examples/earthquakes/README.md) — Complete Claude Desktop setup walkthrough
- [Integration Guide](docs/integrations.md) — Claude Desktop, OpenAI, mcp-cli, and custom integrations

## 📚 Documentation

- [Overview](docs/overview.md) — Core concepts and architecture
- [Quickstart](docs/quickstart.md) — Get up and running
- [CLI Reference](docs/cli.md) — Command-line tools
- [Configuration](docs/configuration.md) — Project setup
- [Plugins](docs/plugins.md) — Extend DuckDB with custom Python functions
- [Authentication](docs/authentication.md) — OAuth authentication setup
- [Policy Enforcement](docs/policies.md) — Access control and data filtering
- [Audit Logging](docs/auditing.md) — Enterprise-grade execution logging
- [Type System](docs/type-system.md) — Data types and validation
- [Integrations](docs/integrations.md) — Data sources and tools
- [Drift Detection](docs/drift-detection.md) — Schema and endpoint change monitoring

## 🤝 Contributing

We welcome contributions! See our [development guide](docs/dev-guide.md) to get started.

## 🧠 About

MXCP is developed by RAW Labs, combining the best of:
- dbt's modular data modeling
- DuckDB's speed and connectors
- Python MCP official server
- Modern AI-native workflows
