# MXCP: Enterprise-Grade Data-to-AI Infrastructure

<div align="center">
  <a href="https://mxcp.dev"><img src="docs/mxcp-logo.png" alt="MXCP Logo" width="350"></a>
</div>

<div align="center">

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-BSL-green.svg)](https://github.com/raw-labs/mxcp/blob/main/LICENSE)

**The MCP server built for production: Transform your data into AI-ready interfaces with enterprise security, audit trails, and policy enforcement**

</div>

## 🚀 What Makes MXCP Different?

While other MCP servers focus on simple data access, MXCP is built for **production environments** where security, governance, and scalability matter:

- 🔒 **Enterprise Security**: Policy enforcement, audit logging, OAuth authentication
- ⚡ **Developer Experience**: Go from SQL to AI interface in under 60 seconds
- 🎯 **dbt Native**: Cache data locally with dbt, serve instantly via MCP
- 🛡️ **Production Ready**: Type safety, drift detection, comprehensive validation
- 📊 **Data Governance**: Track every query, enforce access controls, mask sensitive data

## 🎯 60-Second Quickstart

Experience the power of MXCP in under a minute:

```bash
# 1. Install and create project (15 seconds)
pip install mxcp
mkdir my-data-api && cd my-data-api
mxcp init --bootstrap

# 2. Start serving your data (5 seconds)
mxcp serve

# 3. Connect to Claude Desktop (40 seconds)
# Add this to your Claude config:
{
  "mcpServers": {
    "my-data": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/path/to/my-data-api"
    }
  }
}
```

**Result**: You now have a type-safe, validated data API that Claude can use to query your data with full audit trails and policy enforcement.

## 💡 Real-World Example: dbt + Data Caching

See how MXCP transforms data workflows with our COVID-19 example:

```bash
# Clone and run the COVID example
git clone https://github.com/raw-labs/mxcp.git
cd mxcp/examples/covid_owid

# Cache data locally with dbt (this is the magic!)
dbt run  # Transforms and caches OWID data locally

# Serve cached data via MCP
mxcp serve
```

**What just happened?**
1. **dbt models** fetch and transform COVID data from Our World in Data into DuckDB tables
2. **DuckDB** stores the transformed data locally for lightning-fast queries  
3. **MCP endpoints** query the DuckDB tables directly (no dbt syntax needed)
4. **Audit logs** track every query for compliance
5. **Policies** can enforce who sees what data

Ask Claude: *"Show me COVID vaccination rates in Germany vs France"* - and it queries the `covid_data` table instantly, with full audit trails.

## 🛡️ Enterprise Features That Set Us Apart

### Policy Enforcement
```yaml
# Control who can access what data
policies:
  input:
    - condition: "!('hr.read' in user.permissions)"
      action: deny
      reason: "Missing HR read permission"
  output:
    - condition: "user.role != 'admin'"
      action: filter_fields
      fields: ["salary", "ssn"]
```

### Audit Logging
```bash
# Track every query with enterprise-grade logging
mxcp log --since 1h --status error
mxcp log --tool employee_data --export-duckdb audit.db
```

### Authentication & Authorization
- OAuth integration (GitHub, Atlassian, custom)
- Role-based access control
- Fine-grained permissions
- Session management

## 🏗️ Architecture: Built for Production

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   LLM Client    │    │      MXCP        │    │   Data Sources  │
│  (Claude, etc)  │◄──►│   (Security      │◄──►│  (DB, APIs,     │
│                 │    │    Audit         │    │   Files, dbt)   │
│                 │    │    Policies)     │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │ Audit Logs   │
                       │ (JSONL/DB)   │
                       └──────────────┘
```

Unlike simple data connectors, MXCP provides:
- **Security layer** between LLMs and your data
- **Audit trail** for every query and result
- **Policy engine** for fine-grained access control
- **Type system** for LLM safety and validation
- **Development workflow** with testing and drift detection

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

Try the included examples:
```bash
# Simple data queries
cd examples/earthquakes && mxcp serve

# Enterprise features (policies, audit, dbt)
cd examples/covid_owid && dbt run && mxcp serve
```

## 💡 Key Features

### 1. Declarative Interface Definition
```yaml
# tools/analyze_sales.yml
mxcp: "1.0.0"
tool:
  name: analyze_sales
  description: "Analyze sales data with automatic caching"
  parameters:
    - name: region
      type: string
      description: "Sales region to analyze"
  return:
    type: object
    properties:
      total_sales: { type: number }
      top_products: { type: array }
  source:
    code: |
      -- This queries the table created by dbt
      SELECT 
        SUM(amount) as total_sales,
        array_agg(product) as top_products
      FROM sales_summary  -- Table created by dbt model
      WHERE region = $region
```

### 2. dbt Integration
```sql
-- models/sales_summary.sql (dbt model)
{{ config(materialized='table') }}

SELECT 
  region,
  product,
  SUM(amount) as amount,
  created_at::date as sale_date
FROM {{ source('raw', 'sales_data') }}
WHERE created_at >= current_date - interval '90 days'
GROUP BY region, product, sale_date
```

**Why this matters**: dbt creates optimized tables in DuckDB, MXCP endpoints query them directly - perfect separation of concerns with caching, transformations, and governance built-in.

### 3. Production-Ready Security
- **Authentication**: OAuth, API keys, session management
- **Authorization**: Role-based access, permission checking
- **Audit**: Every query logged with user context
- **Policies**: Dynamic data filtering and access control
- **Drift Detection**: Monitor schema changes across environments

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
└── models/          # dbt transformations & caches
```

### CLI Commands
```bash
mxcp serve           # Start production MCP server
mxcp init            # Initialize new project
mxcp list            # List all endpoints
mxcp validate        # Check types, SQL, and references
mxcp test            # Run endpoint tests
mxcp dbt run         # Run dbt transformations
mxcp log             # Query audit logs
mxcp drift-check     # Check for schema changes
```

## 🔌 LLM Integration

MXCP implements the Model Context Protocol (MCP), making it compatible with:

- **Claude Desktop** — Native MCP support
- **OpenAI-compatible tools** — Via MCP adapters  
- **Custom integrations** — Using the MCP specification

For specific setup instructions, see:
- [Earthquakes Example](https://github.com/raw-labs/mxcp/blob/main/examples/earthquakes/README.md) — Complete Claude Desktop setup
- [COVID + dbt Example](https://github.com/raw-labs/mxcp/blob/main/examples/covid_owid/README.md) — Advanced dbt integration

## 📚 Documentation

### 📚 Getting Started
- **[Overview](https://github.com/raw-labs/mxcp/blob/main/docs/getting-started/overview.md)** - Introduction to MXCP and its core architecture
- **[Quickstart Guide](https://github.com/raw-labs/mxcp/blob/main/docs/getting-started/quickstart.md)** - Get up and running quickly with examples

### 📖 Guides
- **[Configuration Guide](https://github.com/raw-labs/mxcp/blob/main/docs/guides/configuration.md)** - Complete configuration reference
- **[Authentication](https://github.com/raw-labs/mxcp/blob/main/docs/guides/authentication.md)** - OAuth setup and security
- **[Integrations](https://github.com/raw-labs/mxcp/blob/main/docs/guides/integrations.md)** - LLM platforms, dbt, and data sources
- **[Quality & Testing](https://github.com/raw-labs/mxcp/blob/main/docs/guides/quality.md)** - Validation, testing, and linting best practices

### ⚡ Features
- **[Policy Enforcement](https://github.com/raw-labs/mxcp/blob/main/docs/features/policies.md)** - Access control and data filtering
- **[Drift Detection](https://github.com/raw-labs/mxcp/blob/main/docs/features/drift-detection.md)** - Monitor schema and endpoint changes
- **[Audit Logging](https://github.com/raw-labs/mxcp/blob/main/docs/features/auditing.md)** - Enterprise-grade logging and compliance

### 📋 Reference
- **[CLI Reference](https://github.com/raw-labs/mxcp/blob/main/docs/reference/cli.md)** - Complete command-line interface documentation
- **[Type System](https://github.com/raw-labs/mxcp/blob/main/docs/reference/type-system.md)** - Data validation and type definitions
- **[Plugins](https://github.com/raw-labs/mxcp/blob/main/docs/reference/plugins.md)** - Custom Python extensions and UDFs

## 🤝 Contributing

We welcome contributions! See our [development guide](https://github.com/raw-labs/mxcp/blob/main/docs/contributors/dev-guide.md) to get started.

## 🏢 Enterprise Support

MXCP is developed by RAW Labs for production data-to-AI workflows. For enterprise support, custom integrations, or consulting:

- 📧 Contact: [hello@raw-labs.com](mailto:hello@raw-labs.com)
- 🌐 Website: [www.raw-labs.com](https://www.raw-labs.com)

---

**Built for the modern data stack**: Combines dbt's modeling power, DuckDB's performance, and enterprise-grade security into a single AI-ready platform.
