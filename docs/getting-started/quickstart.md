---
title: "Quickstart"
description: "Get started with MXCP in 5 minutes. Create AI tools with SQL or Python, integrate with Claude Desktop, and deploy production-ready MCP servers."
sidebar:
  order: 2
---

This guide demonstrates MXCP's structured approach to building production-ready MCP servers. You'll learn not just how to create AI tools, but how to build them the right way - with proper data modeling, comprehensive testing, and enterprise-grade security.

## Installation

Install MXCP using pip:

```bash
pip install mxcp
```

For advanced features, install optional dependencies:

```bash
pip install "mxcp[vault]"       # HashiCorp Vault integration
pip install "mxcp[onepassword]" # 1Password integration
pip install "mxcp[all]"         # All optional features
```

## Create Your First Project

Initialize a new MXCP project with example endpoints:

```bash
mkdir my-mxcp-project
cd my-mxcp-project
mxcp init --bootstrap
```

This creates an organized project structure:

```
my-mxcp-project/
├── mxcp-site.yml       # Project configuration
├── tools/              # Tool definitions (.yml files)
│   └── hello-world.yml # Example tool
├── resources/          # Resource definitions
├── prompts/            # Prompt definitions
├── evals/              # Evaluation definitions
├── python/             # Python endpoints
├── plugins/            # DuckDB plugins
├── sql/                # SQL implementations
│   └── hello-world.sql # SQL for tools
├── drift/              # Drift snapshots
├── audit/              # Audit logs
└── server_config.json  # Claude Desktop config
```

The bootstrap creates a working hello world example:

**Tool Definition** (`tools/hello-world.yml`):
```yaml
mxcp: 1
tool:
  name: hello_world
  description: A simple hello world tool
  enabled: true
  parameters:
    - name: name
      type: string
      description: Name to greet
      examples: ["World", "Alice", "Bob"]
  return:
    type: string
    description: Greeting message
  source:
    file: ../sql/hello-world.sql
```

**SQL Implementation** (`sql/hello-world.sql`):
```sql
SELECT 'Hello, ' || $name || '!' as greeting
```

## Run the Tool

Test your tool directly from the command line:

```bash
mxcp run tool hello_world --param name=MXCP
```

Output:
```
greeting
---------
Hello, MXCP!
```

## Start the Server

Start the MCP server:

```bash
mxcp serve
```

The server starts in stdio mode by default, ready for LLM integration. For HTTP transport:

```bash
mxcp serve --transport streamable-http --port 8000
```

## Connect to Claude Desktop

Add MXCP to your Claude Desktop configuration:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "my-project": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/absolute/path/to/my-mxcp-project"
    }
  }
}
```

Restart Claude Desktop. You can now ask Claude to use your tools:

> "Say hello to Alice using the hello_world tool"

## Create a SQL Endpoint

SQL endpoints are ideal for data queries and aggregations. Create a tool that queries sales data:

**Define the tool** (`tools/sales-summary.yml`):
```yaml
mxcp: 1
tool:
  name: sales_summary
  description: Get sales summary by region
  parameters:
    - name: region
      type: string
      description: Region to filter by
      examples: ["North", "South", "East", "West"]
    - name: min_amount
      type: number
      description: Minimum sale amount
      default: 0
  return:
    type: object
    properties:
      region:
        type: string
      total_sales:
        type: number
      transaction_count:
        type: integer
  source:
    file: ../sql/sales-summary.sql
```

**Write the SQL** (`sql/sales-summary.sql`):
```sql
SELECT
  $region as region,
  SUM(amount) as total_sales,
  COUNT(*) as transaction_count
FROM sales
WHERE region = $region
  AND amount >= $min_amount
```

## Create a Python Endpoint

Python endpoints are ideal for complex logic, API integrations, and ML models:

**Define the tool** (`tools/fibonacci.yml`):
```yaml
mxcp: 1
tool:
  name: calculate_fibonacci
  description: Calculate Fibonacci number at position n
  language: python
  parameters:
    - name: n
      type: integer
      description: Position in Fibonacci sequence
      minimum: 0
      maximum: 100
  return:
    type: object
    properties:
      position:
        type: integer
      value:
        type: integer
  source:
    file: ../python/math_tools.py
```

**Write the Python** (`python/math_tools.py`):
```python
from mxcp.runtime import db

def calculate_fibonacci(n: int) -> dict:
    """Calculate the nth Fibonacci number."""
    if n <= 1:
        value = n
    else:
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        value = b

    return {
        "position": n,
        "value": value
    }
```

## Validate Your Project

MXCP provides comprehensive quality tools:

```bash
# Validate all endpoints
mxcp validate

# Run tests
mxcp test

# Check for LLM-optimization issues
mxcp lint

# List all endpoints
mxcp list
```

## Add Tests

Add tests directly in your endpoint definition:

```yaml
tool:
  name: hello_world
  # ... parameters and return ...
  tests:
    - name: basic_greeting
      description: Test basic greeting
      arguments:
        - key: name
          value: World
      result: "Hello, World!"
    - name: custom_name
      description: Test with custom name
      arguments:
        - key: name
          value: Alice
      result_contains_text: "Alice"
```

Run tests:

```bash
mxcp test
```

## Add Security

Enable policy enforcement to control access:

```yaml
tool:
  name: employee_data
  # ... parameters and return ...

  policies:
    input:
      - condition: "user.role == 'guest'"
        action: deny
        reason: "Guests cannot access employee data"
    output:
      - condition: "user.role != 'admin'"
        action: filter_fields
        fields: ["salary", "ssn"]
        reason: "Sensitive data restricted to admins"
```

Test with user context:

```bash
mxcp run tool employee_data \
  --param employee_id=123 \
  --user-context '{"role": "admin", "permissions": ["hr.read"]}'
```

## Enable Audit Logging

Track all operations in your `mxcp-site.yml`:

```yaml
profiles:
  default:
    audit:
      enabled: true
      path: audit/logs.jsonl
```

Query audit logs:

```bash
mxcp log --since 1h
mxcp log --tool hello_world
mxcp log --status error
```

## Advanced Patterns

### Combining SQL and Python

Create powerful tools that leverage both SQL efficiency and Python flexibility:

```yaml
# tools/customer-insights.yml
mxcp: 1
tool:
  name: customer_insights
  description: Generate AI insights for customer behavior
  language: python
  parameters:
    - name: customer_id
      type: string
  return:
    type: object
  source:
    file: ../python/insights.py
```

```python
# python/insights.py
from mxcp.runtime import db
import statistics

def customer_insights(customer_id: str) -> dict:
    """Combine SQL data analysis with Python ML insights."""

    # Use SQL for efficient data aggregation
    purchase_data = db.execute("""
        SELECT
            COUNT(*) as total_purchases,
            SUM(amount) as total_spent,
            AVG(amount) as avg_order_value
        FROM purchases
        WHERE customer_id = $customer_id
    """, {"customer_id": customer_id})

    # Get purchase history for pattern analysis
    history = db.execute("""
        SELECT amount, purchase_date
        FROM purchases
        WHERE customer_id = $customer_id
        ORDER BY purchase_date DESC
        LIMIT 50
    """, {"customer_id": customer_id})

    # Use Python for complex analysis
    amounts = [p["amount"] for p in history]
    trend = "stable"
    if len(amounts) >= 10:
        recent = statistics.mean(amounts[:10])
        older = statistics.mean(amounts[10:20]) if len(amounts) >= 20 else amounts[-1]
        trend = "increasing" if recent > older * 1.1 else "decreasing" if recent < older * 0.9 else "stable"

    return {
        "customer_id": customer_id,
        "purchase_summary": purchase_data[0] if purchase_data else None,
        "spending_trend": trend
    }
```

### Type-Safe Parameter Validation

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

## Why MXCP?

MXCP provides unique value for building AI-powered applications:

1. **Flexible Implementation**: Choose SQL for data queries, Python for complex logic, or both
2. **Enterprise Security**: Policy enforcement, audit trails, OAuth authentication
3. **Production Ready**: Type safety, monitoring, drift detection, comprehensive testing
4. **Developer Experience**: Fast iteration, hot reload, comprehensive validation
5. **Scalability**: From prototype to production without re-architecting

## Key Architecture Patterns

### SQL + dbt Workflow

1. **dbt models** (`models/*.sql`) - Create tables/views in DuckDB using dbt syntax
2. **MXCP tools** (`tools/*.yml`) - Query the dbt tables directly using standard SQL
3. **SQL files** (`sql/*.sql`) - Contain the actual SQL logic referenced by tools

### Python Workflow

1. **Python modules** (`python/*.py`) - Implement complex logic, API calls, ML models
2. **MXCP tools** (`tools/*.yml`) - Define interfaces with `language: python`
3. **Runtime services** - Access database, config, and secrets via `mxcp.runtime`

**Perfect separation**: Choose the right tool for each job, with all endpoints getting enterprise features automatically.

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

**Validation errors:**
```bash
# Get detailed validation output
mxcp validate --debug

# Check specific endpoint
mxcp validate tools/my-tool.yml
```

**Python import errors:**
```bash
# Ensure virtual environment is active
source .venv/bin/activate

# Check Python path
mxcp run tool my_tool --debug
```

### Getting Help

- **Documentation**: All features are documented in the docs
- **Examples**: Check `examples/` directory for real-world patterns
- **Validation**: Use `mxcp validate` to check your configuration
- **Debug mode**: Add `--debug` to any command for verbose output

## Next Steps

You've created your first MXCP project with tools, tests, and security. Here's where to go next:

### Learn Core Concepts
- [Endpoints](concepts/endpoints) - Understand tools, resources, and prompts
- [Type System](concepts/type-system) - Master input/output validation
- [Project Structure](concepts/project-structure) - Organize your project

### Build More Complex Tools
- [SQL Endpoints Tutorial](tutorials/sql-endpoints) - Query data efficiently
- [Python Endpoints Tutorial](tutorials/python-endpoints) - Build complex logic
- [dbt Integration](integrations/dbt) - Data transformation pipelines

### Add Enterprise Features
- [Authentication](security/authentication) - OAuth setup
- [Policies](security/policies) - Fine-grained access control
- [Audit Logging](security/auditing) - Compliance tracking

### Go to Production
- [Configuration](operations/configuration) - Environment management
- [Deployment](operations/deployment) - Docker, systemd patterns
- [Monitoring](operations/monitoring) - Observability setup

### Ensure Quality
- [Validation](quality/validation) - Endpoint correctness
- [Testing](quality/testing) - Comprehensive test coverage
- [Evals](quality/evals) - AI behavior verification
