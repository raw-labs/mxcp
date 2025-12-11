---
title: "Quickstart Guide"
description: "Get started with MXCP quickly - create AI tools with SQL or Python. Learn to build tools, integrate with dbt, and deploy production-ready AI applications."
sidebar:
  order: 2
---

This guide demonstrates MXCP's structured approach to building production-ready MCP servers. You'll learn not just how to create AI tools, but how to build them **the right way** - with proper data modeling, comprehensive testing, and enterprise-grade security.

## Table of Contents

- [Installation](#installation)
- [Path 1: Hello World (2 minutes)](#path-1-hello-world-2-minutes)
- [Path 2: Real-World Data Pipeline (10 minutes)](#path-2-real-world-data-pipeline-10-minutes)
- [Path 3: Python-Powered Tools (5 minutes)](#path-3-python-powered-tools-5-minutes)
- [Path 4: Enterprise Features (15 minutes)](#path-4-enterprise-features-15-minutes)
- [Advanced Patterns](#advanced-patterns)
- [LLM Integration Options](#llm-integration-options)
- [Production Deployment](#production-deployment)
- [Next Steps](#next-steps)
- [Troubleshooting](#troubleshooting)
- [Why MXCP?](#why-mxcp)
- [Key Architecture Patterns](#key-architecture-patterns)

## Installation

First, install MXCP:

```bash
pip install mxcp

# For advanced features (optional)
pip install "mxcp[vault]"      # HashiCorp Vault integration
pip install "mxcp[onepassword]" # 1Password integration
pip install "mxcp[all]"        # All optional features
```

## Path 1: Hello World (2 minutes)

Perfect for understanding the basics with both SQL and Python examples:

### 1. Initialize a Project

Create a new project with hello world examples:

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
├── python/             # Python endpoints and shared code
├── plugins/            # MXCP plugins for DuckDB
├── sql/                # SQL implementations
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
- **`python/`** - Python endpoints and shared code
- **`plugins/`** - MXCP plugins for DuckDB (User Defined Functions)
- **`sql/`** - SQL implementations for data queries
- **`drift/`** - Schema drift detection snapshots (auto-generated)
- **`audit/`** - Audit logs (auto-generated when enabled)

The `--bootstrap` flag provides:
- ✅ Complete organized directory structure
- ✅ Examples in both SQL and Python
- ✅ Automatic `server_config.json` generation that handles virtualenvs
- ✅ Clear, actionable next steps
- ✅ Platform-specific Claude Desktop config paths

### 2. Explore the Generated Files

The bootstrap creates examples in both languages:

**SQL Example** (for data queries):
```yaml
# tools/hello-world.yml
mxcp: 1
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
    file: "../sql/hello-world.sql"
```

```sql
-- sql/hello-world.sql
SELECT 'Hello, ' || $name || '!' as greeting
```

**Python Example** (for complex logic):
```yaml
# tools/calculate-fibonacci.yml
mxcp: 1
tool:
  name: "calculate_fibonacci"
  description: "Calculate Fibonacci number"
  language: python
  parameters:
    - name: "n"
      type: "integer"
      description: "Position in Fibonacci sequence"
      minimum: 0
      maximum: 100
  return:
    type: "object"
    properties:
      position: { type: "integer" }
      value: { type: "integer" }
      calculation_time: { type: "number" }
  source:
    file: "../python/math_tools.py"
```

```python
# python/math_tools.py
import time
from mxcp.runtime import db, config

def calculate_fibonacci(n: int) -> dict:
    """Calculate the nth Fibonacci number"""
    start_time = time.time()
    
    if n <= 1:
        value = n
    else:
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        value = b
    
    # Optional: Store in database for caching
    db.execute(
        "INSERT OR REPLACE INTO fibonacci_cache (n, value) VALUES ($n, $value)",
        {"n": n, "value": value}
    )
    
    return {
        "position": n,
        "value": value,
        "calculation_time": time.time() - start_time
    }
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
version: '1'
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

**Built-in SQL Tools**: MXCP provides optional SQL query tools (`execute_sql_query`, `list_tables`, `get_table_schema`) that let Claude explore and query your data directly. These tools are disabled by default but can be enabled in your configuration.

## Path 3: Python-Powered Tools (5 minutes)

Build complex AI tools using Python's full ecosystem:

### 1. Create a Python Analysis Tool

```yaml
# tools/sentiment-analyzer.yml
mxcp: 1
tool:
  name: sentiment_analyzer
  description: "Analyze text sentiment with ML"
  language: python
  parameters:
    - name: texts
      type: array
      items:
        type: string
      description: "Texts to analyze"
      maxItems: 100
  return:
    type: array
    items:
      type: object
      properties:
        text: { type: string }
        sentiment: { type: string, enum: ["positive", "negative", "neutral"] }
        confidence: { type: number, minimum: 0, maximum: 1 }
  source:
    file: "../python/ml_tools.py"
```

```python
# python/ml_tools.py
from mxcp.runtime import db, config, on_init
import asyncio

# Simulate ML model loading (replace with real model)
model = None

@on_init
def load_model():
    """Load ML model on startup"""
    global model
    print("Loading sentiment model...")
    # model = load_your_model_here()
    model = {"loaded": True}  # Placeholder

async def sentiment_analyzer(texts: list[str]) -> list[dict]:
    """Analyze sentiment for multiple texts concurrently"""
    
    async def analyze_one(text: str) -> dict:
        # Simulate async API call or model inference
        await asyncio.sleep(0.1)
        
        # Simple rule-based sentiment (replace with real ML)
        sentiment = "positive" if "good" in text.lower() else \
                   "negative" if "bad" in text.lower() else \
                   "neutral"
        
        confidence = 0.95 if sentiment != "neutral" else 0.6
        
        # Optional: Store results for analytics
        db.execute(
            """
            INSERT INTO sentiment_history (text, sentiment, confidence, analyzed_at)
            VALUES ($text, $sentiment, $confidence, CURRENT_TIMESTAMP)
            """,
            {"text": text[:200], "sentiment": sentiment, "confidence": confidence}
        )
        
        return {
            "text": text,
            "sentiment": sentiment,
            "confidence": confidence
        }
    
    # Process all texts concurrently
    results = await asyncio.gather(*[analyze_one(text) for text in texts])
    return results
```

### 2. Create an API Integration Tool

```yaml
# tools/weather-forecast.yml
mxcp: 1
tool:
  name: weather_forecast
  description: "Get weather forecast for a location"
  language: python
  parameters:
    - name: location
      type: string
      description: "City name or coordinates"
  return:
    type: object
    properties:
      location: { type: string }
      temperature: { type: number }
      conditions: { type: string }
      forecast: 
        type: array
        items:
          type: object
          properties:
            day: { type: string }
            high: { type: number }
            low: { type: number }
  source:
    file: "../python/api_tools.py"
```

```python
# python/api_tools.py
import httpx
from mxcp.runtime import config, db
from datetime import datetime

async def weather_forecast(location: str) -> dict:
    """Fetch weather forecast from external API"""
    
    # Get API key from secure config
    api_key = config.get_secret("weather_api_key")
    
    # Check cache first
    cached = db.execute(
        """
        SELECT forecast_data 
        FROM weather_cache 
        WHERE location = $location 
          AND cached_at > datetime('now', '-1 hour')
        """,
        {"location": location}
    ).fetchone()
    
    if cached:
        return cached["forecast_data"]
    
    # Fetch from API
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.weather.com/forecast",
            params={"location": location, "key": api_key}
        )
        data = response.json()
    
    # Transform and cache the result
    result = {
        "location": location,
        "temperature": data["current"]["temp"],
        "conditions": data["current"]["conditions"],
        "forecast": [
            {
                "day": day["date"],
                "high": day["high"],
                "low": day["low"]
            }
            for day in data["forecast"][:5]
        ]
    }
    
    # Cache for future requests
    db.execute(
        """
        INSERT OR REPLACE INTO weather_cache (location, forecast_data, cached_at)
        VALUES ($location, $data, CURRENT_TIMESTAMP)
        """,
        {"location": location, "data": result}
    )
    
    return result
```

### 3. Combine SQL and Python

Create powerful tools that leverage both SQL for data and Python for logic:

```yaml
# tools/customer-insights.yml
mxcp: 1
tool:
  name: customer_insights
  description: "Generate AI insights for customer behavior"
  language: python
  parameters:
    - name: customer_id
      type: string
  return:
    type: object
  source:
    file: "../python/insights.py"
```

```python
# python/insights.py
from mxcp.runtime import db
import statistics

def customer_insights(customer_id: str) -> dict:
    """Combine SQL data analysis with Python ML insights"""
    
    # Use SQL for efficient data aggregation
    purchase_data = db.execute("""
        SELECT 
            COUNT(*) as total_purchases,
            SUM(amount) as total_spent,
            AVG(amount) as avg_order_value,
            MAX(purchase_date) as last_purchase,
            STRING_AGG(DISTINCT category, ', ') as categories
        FROM purchases
        WHERE customer_id = $customer_id
    """, {"customer_id": customer_id}).fetchone()
    
    # Get purchase history for pattern analysis
    history = db.execute("""
        SELECT amount, purchase_date, category
        FROM purchases
        WHERE customer_id = $customer_id
        ORDER BY purchase_date DESC
        LIMIT 50
    """, {"customer_id": customer_id}).fetchall()
    
    # Use Python for complex analysis
    amounts = [p["amount"] for p in history]
    
    insights = {
        "customer_id": customer_id,
        **dict(purchase_data),
        "spending_trend": calculate_trend(amounts),
        "purchase_frequency": calculate_frequency(history),
        "predicted_ltv": predict_lifetime_value(purchase_data, history),
        "recommendations": generate_recommendations(history)
    }
    
    return insights

def calculate_trend(amounts):
    """Calculate spending trend"""
    if len(amounts) < 2:
        return "insufficient_data"
    
    recent = statistics.mean(amounts[:10])
    older = statistics.mean(amounts[10:20]) if len(amounts) >= 20 else amounts[-1]
    
    if recent > older * 1.1:
        return "increasing"
    elif recent < older * 0.9:
        return "decreasing"
    else:
        return "stable"
```

### 4. Test Your Python Tools

```bash
# Run individual tools
mxcp run tool sentiment_analyzer --param texts='["This is great!", "Bad experience"]'

# Test with mock data
mxcp test

# View execution logs
mxcp log --tool sentiment_analyzer
```

## Path 4: Enterprise Features (15 minutes)

Experience MXCP's production-grade security and governance:

### 1. Policy Enforcement

Create a new endpoint with access control:

```yaml
# tools/employee-data.yml
mxcp: 1
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

### Option C: Built-in SQL Tools (Optional)

MXCP provides optional SQL exploration tools that work with any MCP client:

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

**Configure SQL Tools** (required to enable):
```yaml
# mxcp-site.yml
sql_tools:
  enabled: true  # Default: false - must be explicitly enabled
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
   
   > 💡 Learn more about writing tests and ensuring quality in the [Quality & Testing Guide](../guides/quality)

2. **Explore the CLI**
   ```bash
   mxcp --help       # See all commands
   mxcp run --help   # Understand execution options
   mxcp log --help   # Learn about audit querying
   ```

### Dive Deeper
1. **[Type System](../reference/type-system)** - Master MXCP's type safety features
2. **[Quality & Testing](../guides/quality)** - Write comprehensive tests and ensure quality
3. **[Policies](../features/policies)** - Implement fine-grained access control
4. **[Authentication](../guides/authentication)** - Set up OAuth for your organization
5. **[Plugins](../reference/plugins)** - Extend DuckDB with custom Python functions
6. **[Drift Detection](../features/drift-detection)** - Monitor changes across environments

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

1. **Flexible Implementation**: Choose SQL for data queries, Python for complex logic, or both
2. **Enterprise Security**: Policy enforcement, audit trails, OAuth authentication
3. **Production Ready**: Type safety, monitoring, drift detection, comprehensive testing
4. **Developer Experience**: Fast iteration, hot reload, comprehensive validation
5. **Scalability**: From prototype to production without re-architecting

## Key Architecture Patterns

**SQL + dbt Workflow:**
1. **dbt models** (`models/*.sql`) → Create tables/views in DuckDB using dbt syntax
2. **MXCP tools** (`tools/*.yml`) → Query the dbt tables directly using standard SQL
3. **SQL files** (`sql/*.sql`) → Contain the actual SQL logic referenced by tools

**Python Workflow:**
1. **Python modules** (`python/*.py`) → Implement complex logic, API calls, ML models
2. **MXCP tools** (`tools/*.yml`) → Define interfaces with `language: python`
3. **Runtime services** → Access database, config, and secrets via `mxcp.runtime`

**Perfect separation**: Choose the right tool for each job, with all endpoints getting enterprise features automatically.

### Learn More
- **[Python Endpoints](../features/python-endpoints)** - Build complex tools with Python
- **[Type System](../reference/type-system)** - Master MXCP's type validation system
- **[dbt Integration](../guides/integrations#dbt-integration)** - Build robust data transformation pipelines
- **[Drift Detection](../features/drift-detection)** - Monitor changes across environments
- **[Plugin Development](../reference/plugins)** - Extend MXCP with custom functionality 
