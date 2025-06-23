---
title: "Quickstart Guide"
description: "Get started with MXCP quickly - from basic setup to advanced enterprise features. Learn to create projects, integrate with dbt, and deploy production-ready AI data pipelines."
keywords:
  - mxcp quickstart
  - mxcp tutorial
  - ai data pipeline
  - dbt integration
  - claude desktop setup
  - mcp server
sidebar_position: 2
slug: /quickstart
---

# MXCP Quickstart Guide

This guide will help you get started with MXCP quickly, from basic setup to advanced enterprise features. We'll cover creating new projects, exploring examples, and leveraging MXCP's unique production capabilities.

## Installation

First, install MXCP:

```bash
pip install mxcp

# For advanced features (optional)
pip install "mxcp[vault]"  # HashiCorp Vault integration
```

## Path 1: Hello World (2 minutes)

Perfect for understanding the basics:

### 1. Initialize a Project

Create a new project with a hello world example:

```bash
# Create a new directory and initialize MXCP
mkdir my-mxcp-project
cd my-mxcp-project
mxcp init --bootstrap
```

This creates an organized project structure:

```
my-mxcp-project/
├── mxcp-site.yml       # Project configuration
├── tools/              # Tool definitions (MCP tools)
│   └── hello-world.yml # Example tool definition
├── resources/          # Resource definitions (MCP resources)
├── prompts/            # Prompt definitions (MCP prompts)
├── evals/              # Evaluation definitions
├── python/             # Python extensions & shared code
├── sql/                # SQL implementation files
│   └── hello-world.sql # SQL implementation for tools
├── drift/              # Drift detection snapshots
├── audit/              # Audit logs
└── server_config.json  # Claude Desktop config (auto-generated)
```

**🏗️ Organized by Design**: MXCP enforces a structured approach where each endpoint type has its own directory:

- **`tools/`** - MCP tool definitions (`.yml` files that define callable functions)
- **`resources/`** - MCP resource definitions (`.yml` files that define data resources)  
- **`prompts/`** - MCP prompt definitions (`.yml` files that define reusable prompts)
- **`evals/`** - Evaluation definitions for testing your endpoints
- **`python/`** - Python extensions and shared code modules
- **`sql/`** - SQL implementation files (referenced by YAML definitions)
- **`drift/`** - Schema drift detection snapshots (auto-generated)
- **`audit/`** - Audit logs (auto-generated when enabled)

The `--bootstrap` flag provides:
- ✅ Complete organized directory structure
- ✅ Properly formatted SQL files in dedicated `sql/` directory
- ✅ Automatic `server_config.json` generation that handles virtualenvs
- ✅ Clear, actionable next steps
- ✅ Platform-specific Claude Desktop config paths

### 2. Explore the Generated Files

The bootstrap creates a simple hello world tool:

```yaml
# tools/hello-world.yml
mxcp: "1.0.0"
tool:
  name: "hello_world"
  description: "A simple hello world tool"
  enabled: true
  parameters:
    - name: "name"
      type: "string"
      description: "Name to greet"
      examples: ["World"]
  return:
    type: "string"
    description: "Greeting message"
  source:
    file: "../sql/hello-world.sql"  # References SQL file in sql/ directory
```

```sql
-- sql/hello-world.sql
SELECT 'Hello, ' || $name || '!' as greeting
```

### 3. Start the MCP Server

```bash
mxcp serve
```

The server starts in stdio mode, ready for LLM integration. If you used `--bootstrap`, the generated `server_config.json` is already configured correctly for your environment (virtualenv, poetry, or system-wide installation).

## Path 2: Real-World Data Pipeline (10 minutes)

Experience MXCP's production capabilities with the COVID-19 + dbt example:

### 1. Get the COVID Example

```bash
git clone https://github.com/raw-labs/mxcp.git
cd mxcp/examples/covid_owid
```

### 2. Understand the dbt Integration

This example showcases MXCP's killer feature: **dbt-native data caching**

```yaml
# dbt_project.yml - Standard dbt project
name: 'covid_owid'
version: '1.0.0'
profile: 'covid_owid'
model-paths: ["models"]
target-path: "target"
```

```sql
-- models/covid_data.sql - dbt model that creates covid_data table
{{ config(materialized='table') }}

select *
from read_csv_auto('https://github.com/owid/covid-19-data/raw/master/public/data/owid-covid-data.csv')
```

**The magic**: This dbt model fetches COVID data from the web and creates a `covid_data` table in DuckDB. MXCP endpoints then query this table directly using standard SQL.

### 3. Run the Data Pipeline

```bash
# Install dbt dependencies
dbt deps

# Run dbt transformations (this caches the data locally)
dbt run

# Start MXCP server
mxcp serve
```

**What just happened?**
1. `dbt run` fetched COVID data from OWID and created a `covid_data` table in DuckDB
2. MXCP server exposes SQL query tools that can query this table directly
3. LLMs can analyze months of COVID data instantly (no API calls!)

### 4. Connect to Claude Desktop

Add this to your Claude Desktop config:

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

### 5. Test the Integration

Ask Claude:
- *"Show me COVID cases in Germany vs France during 2021"*
- *"What were the vaccination rates in the UK by month?"*
- *"Compare hospitalization data between Italy and Spain"*

The responses are instant because the data is cached locally!

**Built-in SQL Tools**: MXCP automatically provides SQL query tools (`execute_sql_query`, `list_tables`, `get_table_schema`) that let Claude explore and query your data directly - no custom endpoints needed for basic data exploration!

## Path 3: Enterprise Features (15 minutes)

Experience MXCP's production-grade security and governance:

### 1. Policy Enforcement

Create a new endpoint with access control:

```yaml
# tools/employee-data.yml
mxcp: "1.0.0"
tool:
  name: employee_data
  description: "Query employee information"
  parameters:
    - name: employee_id
      type: string
      description: "Employee ID to query"
  return:
    type: object
    properties:
      name: { type: string }
      department: { type: string }
      salary: { type: number }
      ssn: { type: string, sensitive: true }
  source:
    code: |
      SELECT 
        'John Doe' as name,
        'Engineering' as department,
        95000 as salary,
        '123-45-6789' as ssn

# Add enterprise-grade policies
policies:
  input:
    - condition: "!('hr.read' in user.permissions)"
      action: deny
      reason: "Missing HR read permission"
  output:
    - condition: "user.role != 'hr_manager'"
      action: filter_fields
      fields: ["salary", "ssn"]
      reason: "Sensitive data restricted to HR managers"
```

### 2. Enable Audit Logging

```yaml
# mxcp-site.yml - Add audit configuration
profiles:
  production:
    audit:
      enabled: true
      path: audit-logs.jsonl
```

### 3. Test with User Context

```bash
# Test as regular user (will filter sensitive data)
mxcp run tool employee_data \
  --param employee_id=123 \
  --user-context '{"role": "user", "permissions": ["hr.read"]}'

# Test as HR manager (will see all data)
mxcp run tool employee_data \
  --param employee_id=123 \
  --user-context '{"role": "hr_manager", "permissions": ["hr.read", "pii.view"]}'

# View audit logs
mxcp log --since 10m
```

### 4. Authentication Setup

For production, enable OAuth authentication:

```yaml
# mxcp-site.yml
profiles:
  production:
    auth:
      enabled: true
      provider: github
      client_id: your_github_client_id
      redirect_uri: http://localhost:8080/callback
```

## Advanced Patterns

### 1. Multi-Source Data Pipeline

**Step 1: dbt creates the tables**
```sql
-- models/sales_analysis.sql (dbt model)
{{ config(materialized='table') }}

WITH daily_sales AS (
  SELECT * FROM {{ source('raw', 'sales_data') }}
),
customer_info AS (
  SELECT * FROM {{ ref('customers') }}  -- Another dbt model
),
external_data AS (
  SELECT * FROM 'https://api.example.com/market-data.json'
)
SELECT 
  s.date,
  s.amount,
  c.segment,
  e.market_trend
FROM daily_sales s
JOIN customer_info c ON s.customer_id = c.id
JOIN external_data e ON s.date = e.date
```

**Step 2: MXCP endpoint queries the table**
```yaml
# tools/sales-analysis.yml
tool:
  name: get_sales_analysis
  source:
    code: |
      SELECT * FROM sales_analysis  -- Table created by dbt
      WHERE date >= $start_date
```

### 2. Dynamic Caching Strategy

**Step 1: dbt model combines live and historical data**
```sql
-- models/live_dashboard.sql (dbt model)
{{ config(
  materialized='table',
  post_hook="PRAGMA optimize"
) }}

-- Cache recent data every hour, historical data daily
SELECT * FROM read_json('https://api.metrics.com/live-data')
WHERE timestamp >= current_timestamp - interval '24 hours'

UNION ALL

SELECT * FROM {{ ref('historical_metrics') }}
WHERE timestamp < current_timestamp - interval '24 hours'
```

**Step 2: MXCP endpoint queries the combined table**
```yaml
# tools/dashboard.yml
tool:
  name: get_dashboard_metrics
  source:
    code: |
      SELECT * FROM live_dashboard  -- Table created by dbt
      WHERE metric_type = $metric_type
      ORDER BY timestamp DESC
```

### 3. Common Data Transformation Patterns

**Reading and Aggregating Data**
```sql
-- Aggregate data by time periods
SELECT 
  DATE_TRUNC('month', created_at) as month,
  COUNT(*) as total_orders,
  SUM(amount) as total_revenue,
  AVG(amount) as avg_order_value
FROM orders
WHERE created_at >= $start_date
GROUP BY DATE_TRUNC('month', created_at)
ORDER BY month DESC;

-- Join multiple data sources
SELECT 
  u.name,
  u.email,
  COUNT(o.id) as order_count,
  SUM(o.amount) as total_spent
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE u.created_at >= $since_date
GROUP BY u.id, u.name, u.email
HAVING COUNT(o.id) > 0;
```

**Reading from Various Sources**
```sql
-- Read from CSV files
SELECT * FROM read_csv('data/sales-*.csv') 
WHERE region = $region;

-- Read from JSON APIs
SELECT * FROM read_json_auto('https://api.example.com/data')
WHERE status = 'active';

-- Read from Parquet files
SELECT customer_id, SUM(amount) as total
FROM read_parquet('s3://bucket/transactions/*.parquet')
GROUP BY customer_id;
```

### 4. Type-Safe Parameter Validation

```yaml
parameters:
  - name: date_range
    type: object
    properties:
      start_date:
        type: string
        format: date
        description: "Start date (YYYY-MM-DD)"
      end_date:
        type: string
        format: date
        description: "End date (YYYY-MM-DD)"
    required: ["start_date", "end_date"]
    
  - name: metrics
    type: array
    items:
      type: string
      enum: ["revenue", "users", "conversion"]
    description: "Metrics to include"
    minItems: 1
    maxItems: 5
```

## LLM Integration Options

### Option A: Claude Desktop Integration

Best for interactive development and testing:

```json
{
  "mcpServers": {
    "my-project": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

### Option B: HTTP API Mode

Perfect for web applications and custom integrations:

```bash
# Start HTTP server
mxcp serve --transport http --port 8080

# Test with curl
curl -X POST http://localhost:8080/tools/employee_data \
  -H "Content-Type: application/json" \
  -d '{"employee_id": "123"}'
```

### Option C: Built-in SQL Tools (Auto-enabled)

MXCP automatically provides SQL exploration tools that work with any MCP client:

**Available Tools:**
- `execute_sql_query` - Run custom SQL queries
- `list_tables` - See all available tables
- `get_table_schema` - Inspect table structure

**Example Usage:**
```bash
# With mcp-cli
pip install mcp-cli
mcp-cli tools call list_tables
mcp-cli tools call execute_sql_query --sql "SELECT COUNT(*) FROM users"

# LLMs can use these directly
"Show me what tables are available, then count the users created this month"
```

**Configure SQL Tools** (optional):
```yaml
# mxcp-site.yml
sql_tools:
  enabled: true  # Default: true
```

## Production Deployment

### 1. Environment Configuration

```yaml
# mxcp-site.yml
profiles:
  development:
    database: dev.duckdb
    auth:
      enabled: false
      
  staging:
    database: staging.duckdb
    auth:
      enabled: true
      provider: github
    audit:
      enabled: true
      path: staging-audit.jsonl
      
  production:
    database: production.duckdb
    auth:
      enabled: true
      provider: atlassian
    audit:
      enabled: true
      path: /var/log/mxcp/audit.jsonl
    policies:
      strict_mode: true
```

### 2. Monitoring and Alerting

```bash
# Monitor error rates
mxcp log --since 1h --status error --export-duckdb errors.db

# Set up alerts for policy violations
mxcp log --policy deny --since 10m --export-csv violations.csv

# Track performance
mxcp log --since 1d | jq '.duration_ms' | awk '{sum+=$1; count++} END {print "Avg:", sum/count "ms"}'
```

### 3. Schema Drift Detection

```bash
# Create baseline snapshot
mxcp drift-snapshot --profile production

# Check for changes (run in CI/CD)
mxcp drift-check --profile production
```

## Next Steps
### Immediate Actions

1. **Validate Your Setup**
   ```bash
   mxcp validate     # Check all endpoints
   mxcp test         # Run endpoint tests
   mxcp list         # Verify everything is loaded
   ```
   
   > 💡 Learn more about writing tests and ensuring quality in the [Quality & Testing Guide](../guides/quality.md)

2. **Explore the CLI**
   ```bash
   mxcp --help       # See all commands
   mxcp run --help   # Understand execution options
   mxcp log --help   # Learn about audit querying
   ```

### Dive Deeper
1. **[Type System](../reference/type-system.md)** - Master MXCP's type safety features
2. **[Quality & Testing](../guides/quality.md)** - Write comprehensive tests and ensure quality
3. **[Policies](../features/policies.md)** - Implement fine-grained access control
4. **[Authentication](../guides/authentication.md)** - Set up OAuth for your organization
5. **[Plugins](../reference/plugins.md)** - Extend DuckDB with custom Python functions
6. **[Drift Detection](../features/drift-detection.md)** - Monitor changes across environments

### Build Your Own
1. **Start Simple**: Begin with basic SQL queries
2. **Add Types**: Implement comprehensive type definitions
3. **Enable Security**: Add authentication and policies
4. **Monitor**: Set up audit logging and drift detection
5. **Scale**: Move to production with proper profiles and monitoring

## Troubleshooting

### Common Issues

**dbt models not found:**
```bash
# Ensure dbt project is properly configured
dbt debug
dbt compile
```

**Policy errors:**
```bash
# Test with explicit user context
mxcp run tool my_tool --user-context '{"role": "admin"}'
```

**Authentication issues:**
```bash
# Check OAuth configuration
mxcp validate --profile production
```

### Getting Help

- **Documentation**: All features are documented in the `docs/` directory
- **Examples**: Check `examples/` for real-world patterns
- **Community**: Join our community for support and discussions
- **Issues**: Report bugs and feature requests on GitHub

## Why MXCP?

After completing this quickstart, you should understand MXCP's unique value:

1. **dbt Integration**: dbt creates optimized tables in DuckDB, MXCP endpoints query them directly
2. **Enterprise Security**: Policy enforcement, audit trails, authentication
3. **Production Ready**: Type safety, monitoring, drift detection
4. **Developer Experience**: Fast iteration, comprehensive validation
5. **Scalability**: From prototype to production without re-architecting

## Key Architecture Pattern

**The MXCP + dbt Workflow:**
1. **dbt models** (`models/*.sql`) → Create tables/views in DuckDB using dbt syntax
2. **MXCP tools** (`tools/*.yml`) → Query the dbt tables directly using standard SQL
3. **SQL files** (`sql/*.sql`) → Contain the actual SQL logic referenced by tools
4. **Perfect separation**: dbt handles data transformation, MXCP handles AI interface, organized directories keep everything clean

### Learn More
- **[Type System](../reference/type-system.md)** - Master MXCP's type validation system
- **[dbt Integration](../guides/integrations.md#dbt-integration)** - Build robust data transformation pipelines
- **[Drift Detection](../features/drift-detection.md)** - Monitor changes across environments
- **[Plugin Development](../reference/plugins.md)** - Extend MXCP with custom functionality 