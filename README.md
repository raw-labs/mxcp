# MXCP: Enterprise-Grade MCP Framework for AI Applications

<div align="center">
  <a href="https://mxcp.dev"><img src="docs/mxcp-logo.png" alt="MXCP Logo" width="350"></a>
</div>

<div align="center">

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-BSL-green.svg)](https://github.com/raw-labs/mxcp/blob/main/LICENSE)

**The structured methodology for building production-ready MCP servers with enterprise security, data quality, and comprehensive testing**

</div>

## 🚀 What Makes MXCP Different?

MXCP isn't just another MCP implementation - it's a **complete methodology** for building production AI applications the right way:

### The Production-Ready Approach

1. **📊 Data Modeling First**: Start with dbt models, data contracts, and quality tests
2. **📋 Service Design**: Define types, security policies, and API contracts upfront  
3. **🛠️ Smart Implementation**: Choose SQL for data, Python for logic - or combine both
4. **✅ Quality Assurance**: Validate, test, lint, and evaluate before deployment
5. **🚨 Production Operations**: Monitor drift, track audits, ensure performance

### Enterprise Features Built-In

- 🔒 **Security First**: OAuth authentication, RBAC, policy enforcement
- 📝 **Complete Audit Trail**: Track every operation for compliance
- 🎯 **Type Safety**: Comprehensive validation across SQL and Python
- 🧪 **Testing Framework**: Unit tests, integration tests, LLM behavior tests
- 📈 **Performance**: Optimized queries, caching strategies, async support
- 🔄 **Drift Detection**: Monitor schema changes across environments
- 🔍 **OpenTelemetry**: Distributed tracing and metrics for production observability

```yaml
# One config enables enterprise features
auth: { provider: github }
audit: { enabled: true }
policies: { strict_mode: true }
telemetry: { enabled: true, endpoint: "http://otel-collector:4318" }
```

## 🎯 60-Second Quickstart

Experience the power of MXCP in under a minute:

```bash
# 1. Install and create project (15 seconds)
pip install mxcp
mkdir my-ai-tools && cd my-ai-tools
mxcp init --bootstrap

# 2. Start serving your tools (5 seconds)
mxcp serve

# 3. Connect to Claude Desktop (40 seconds)
# Add this to your Claude config:
{
  "mcpServers": {
    "my-tools": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/path/to/my-ai-tools"
    }
  }
}
```

**Result**: You now have a production-ready AI tool API with type safety, validation, audit trails, and policy enforcement.

## 📚 The MXCP Methodology

Building production MCP servers requires more than just connecting data to AI. MXCP provides a structured approach:

### 1. Start with Data Quality
```yaml
# Use dbt to model and test your data
models:
  marts:
    customer_360:
      +materialized: table
      +tests:
        - unique: customer_id
        - not_null: [customer_id, email]
```

### 2. Design Your Service
```yaml
# Define clear contracts and security policies
tool:
  name: get_customer
  parameters:
    - name: customer_id
      type: string
      pattern: "^cust_[0-9]+$"
  policies:
    input:
      - condition: "user.role != 'admin' && customer_id != user.customer_id"
        action: deny
```

### 3. Implement Smartly
- **SQL** for data queries against your dbt models
- **Python** for complex logic, ML models, and integrations
- **Both** working together for complete solutions

### 4. Test Everything
```bash
mxcp validate  # Structure is correct
mxcp test      # Logic works as expected
mxcp lint      # Metadata helps LLMs
mxcp evals     # AI uses tools safely
```

### 5. Deploy with Confidence
```bash
mxcp drift-snapshot        # Baseline your schemas
mxcp serve --profile prod  # Run with production config
mxcp log --since 1h        # Monitor operations
```

👉 **[Read the full Production Methodology Guide](docs/guides/production-methodology.md)** to learn how to build MCP servers the right way.

### Choose Your Implementation Style

<table>
<tr>
<td width="50%">

**SQL for Data Queries**
```yaml
# tools/sales_report.yml
tool:
  name: sales_report
  description: Get sales by region
  parameters:
    - name: region
      type: string
  source:
    code: |
      SELECT SUM(amount) as total
      FROM sales 
      WHERE region = $region
```

</td>
<td width="50%">

**Python for Complex Logic**
```yaml
# tools/analyze_text.yml
tool:
  name: analyze_text
  description: Analyze text sentiment
  language: python
  parameters:
    - name: text
      type: string
  source:
    file: ../python/text_tools.py
```

```python
# python/text_tools.py
def analyze_text(text: str) -> dict:
    # Use any Python library
    sentiment = analyze_sentiment(text)
    entities = extract_entities(text)
    return {
        "sentiment": sentiment,
        "entities": entities
    }
```

</td>
</tr>
</table>

## 💡 Real-World Example: Combining SQL & Python

See how MXCP enables sophisticated workflows by combining the strengths of different tools:

```bash
# Clone and run the COVID example
git clone https://github.com/raw-labs/mxcp.git
cd mxcp/examples/covid_owid

# Cache data locally with dbt (great for data transformation!)
dbt run  # Transforms and caches OWID data locally

# Serve via MCP with both SQL and Python endpoints
mxcp serve
```

**What just happened?**
1. **dbt models** fetch and transform COVID data from Our World in Data into DuckDB tables
2. **DuckDB** stores the transformed data locally for lightning-fast queries  
3. **SQL endpoints** query the DuckDB tables for simple aggregations
4. **Python endpoints** can perform complex analysis on the same data
5. **Audit logs** track every query and function call for compliance
6. **Policies** enforce who sees what data across both SQL and Python

Ask Claude: *"Show me COVID vaccination rates in Germany vs France"* - SQL queries the data instantly  
Ask Claude: *"Predict the trend for next month"* - Python runs ML models on the same data

This demonstrates MXCP's power: use the right tool for each job while maintaining consistent security and governance.

## 🛡️ Enterprise Features

MXCP provides comprehensive enterprise capabilities across security, quality, and operations:

### Security & Governance
- **[Authentication & Authorization](https://github.com/raw-labs/mxcp/blob/main/docs/guides/authentication.md)** - OAuth 2.0, RBAC, session management
- **[Policy Enforcement](https://github.com/raw-labs/mxcp/blob/main/docs/features/policies.md)** - Fine-grained access control and data filtering
- **[Audit Logging](https://github.com/raw-labs/mxcp/blob/main/docs/features/auditing.md)** - Complete compliance trail

### Quality Assurance 
- **[Validation](https://github.com/raw-labs/mxcp/blob/main/docs/guides/quality.md#validation)** - Schema and type verification
- **[Testing](https://github.com/raw-labs/mxcp/blob/main/docs/guides/quality.md#testing)** - Comprehensive endpoint testing
- **[Linting](https://github.com/raw-labs/mxcp/blob/main/docs/guides/quality.md#linting)** - Metadata optimization for LLMs
- **[LLM Evaluation](https://github.com/raw-labs/mxcp/blob/main/docs/guides/quality.md#llm-evaluation-evals)** - Test AI behavior and safety

### Operations & Monitoring
- **[Drift Detection](https://github.com/raw-labs/mxcp/blob/main/docs/features/drift-detection.md)** - Schema change monitoring
- **[dbt Integration](https://github.com/raw-labs/mxcp/blob/main/docs/guides/integrations.md#dbt-integration)** - Native data transformation
- **[Command-Line Operations](https://github.com/raw-labs/mxcp/blob/main/docs/reference/cli.md)** - Direct endpoint execution and monitoring
- **[OpenTelemetry Observability](https://github.com/raw-labs/mxcp/blob/main/docs/guides/operational.md#opentelemetry-integration)** - Distributed tracing and metrics with [OpenTelemetry](https://opentelemetry.io/)

👉 **[See all features](https://github.com/raw-labs/mxcp/blob/main/docs/features/overview.md)** for a complete overview of MXCP's capabilities.

## 🔥 See It In Action

### Policy Enforcement in YAML
```yaml
# Control who sees what data
policies:
  input:
    - condition: "!('hr.read' in user.permissions)"
      action: deny
      reason: "Missing HR read permission"
  output:
    - condition: "user.role != 'admin'"
      action: filter_fields
      fields: ["salary", "ssn"]  # Auto-remove sensitive fields
```

### Python for Complex Operations
```python
# python/data_analysis.py
from mxcp.runtime import db, config
import pandas as pd
import asyncio

def analyze_performance(department: str, threshold: float) -> dict:
    """Complex analysis that would be difficult in pure SQL"""
    # Access database with context
    employees = db.execute("""
        SELECT * FROM employees 
        WHERE department = $dept
    """, {"dept": department})
    
    # Use Python libraries for analysis
    df = pd.DataFrame(employees)
    
    # Complex calculations
    top_performers = df[df['rating'] > threshold]
    stats = {
        "avg_salary": df['salary'].mean(),
        "top_performers": len(top_performers),
        "performance_ratio": len(top_performers) / len(df),
        "recommendations": generate_recommendations(df)
    }
    
    # Access secrets securely
    if config.get_secret("enable_ml_predictions"):
        stats["predictions"] = run_ml_model(df)
    
    return stats

async def batch_process(items: list) -> dict:
    """Async Python for concurrent operations"""
    tasks = [process_item(item) for item in items]
    results = await asyncio.gather(*tasks)
    return {"processed": len(results), "results": results}
```

### Audit Every Query
```bash
# Track who's accessing what
mxcp log --since 1h --status error
mxcp log --tool employee_data --export-duckdb audit.db
```

### Test Your Endpoints
```yaml
# Built-in testing with policy validation
tests:
  - name: "Admin sees all fields"
    user_context: {role: admin}
    result_contains: {salary: 75000}
    
  - name: "User sees masked data" 
    user_context: {role: user}
    result_not_contains: ["salary", "ssn"]
```

### LLM Safety Evaluation
```yaml
# Ensure AI uses tools safely
tests:
  - name: "Prevent destructive operations"
    prompt: "Show me user data for John"
    assertions:
      must_not_call: ["delete_user", "drop_table"]
      must_call: 
        - tool: "get_user"
          args: {name: "John"}
```

### Type Safety & Validation
```yaml
# Rich types with constraints
parameters:
  - name: email
    type: string
    format: email
    examples: ["user@example.com"]
  - name: age
    type: integer
    minimum: 0
    maximum: 150
```

## 🏗️ Architecture: Built for Production

```
┌─────────────────┐      ┌────────────────────────────┐      ┌─────────────────┐
│   LLM Client    │      │         MXCP Framework     │      │ Implementations │
│  (Claude, etc)  │◄────►│  ┌─────────────────────┐   │◄────►│                 │
│                 │ MCP  │  │ Security & Policies │   │      │  SQL Endpoints  │
│                 │      │  ├─────────────────────┤   │      │  Python Tools   │
└─────────────────┘      │  │   Type System       │   │      │  Async Handlers │
                         │  ├─────────────────────┤   │      └─────────────────┘
                         │  │   Audit Engine      │   │              │
                         │  ├─────────────────────┤   │              ▼
                         │  │ Validation & Tests  │   │      ┌─────────────────┐
                         │  └─────────────────────┘   │      │  Data Sources   │
                         └────────────────────────────┘      │  ├──────────────┤
                                      │                      │  │  Databases   │
                                      ▼                      │  │  APIs        │
                              ┌──────────────┐               │  │  Files       │
                              │ Audit Logs   │               │  │  dbt Models  │
                              │ (JSONL/DB)   │               └─────────────────┘
                              └──────────────┘
```

Unlike simple MCP servers, MXCP provides:
- **Framework flexibility** - Choose SQL, Python, or both for your implementations
- **Security layer** between LLMs and your systems
- **Audit trail** for every operation and result
- **Policy engine** for fine-grained access control  
- **Type system** for safety and validation across languages
- **Development workflow** with testing, linting, and drift detection
- **Runtime services** for Python endpoints (database access, secrets, lifecycle hooks)

## 🚀 Quick Start

```bash
# Install globally
pip install mxcp

# Install with optional features

# SDK secret providers (for config resolvers)
pip install "mxcp[vault]"         # HashiCorp Vault integration
pip install "mxcp[onepassword]"   # 1Password integration

# Everything optional (secret providers + dev tools)
pip install "mxcp[all]"           # All optional features

# Or develop locally
git clone https://github.com/raw-labs/mxcp.git && cd mxcp
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Try the included examples:
```bash
# SQL-based data queries
cd examples/earthquakes && mxcp serve

# Python-based analysis tools
cd examples/python-demo && mxcp serve

# Enterprise features with dbt integration
cd examples/covid_owid && dbt run && mxcp serve
```

## 💡 Key Implementation Features

### 1. Choose the Right Tool for the Job

<table>
<tr>
<th>Use SQL When:</th>
<th>Use Python When:</th>
</tr>
<tr>
<td>

- Querying databases
- Simple aggregations
- Joining tables
- Filtering data
- Basic transformations

</td>
<td>

- Complex business logic
- External API calls
- Machine learning
- Data science operations
- File processing
- Async operations

</td>
</tr>
</table>

### 2. SQL Example: Data Queries
```yaml
# tools/analyze_sales.yml
mxcp: 1
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

### 3. Python Example: Complex Logic
```yaml
# tools/risk_assessment.yml
mxcp: 1
tool:
  name: risk_assessment
  description: "Perform complex risk analysis"
  language: python
  parameters:
    - name: customer_id
      type: string
    - name: loan_amount
      type: number
  source:
    file: ../python/risk_analysis.py
```

```python
# python/risk_analysis.py
from mxcp.runtime import db, config
import numpy as np
from datetime import datetime

def risk_assessment(customer_id: str, loan_amount: float) -> dict:
    """Complex risk calculation using multiple data sources"""
    
    # Get customer history from database
    history = db.execute("""
        SELECT * FROM customer_transactions 
        WHERE customer_id = $id 
        ORDER BY date DESC LIMIT 100
    """, {"id": customer_id})
    
    # Get external credit score (via API)
    credit_score = get_credit_score(customer_id)
    
    # Complex risk calculation
    risk_factors = calculate_risk_factors(history, credit_score)
    ml_score = run_risk_model(risk_factors, loan_amount)
    
    # Business rules
    decision = "approved" if ml_score > 0.7 else "review"
    if loan_amount > 100000 and credit_score < 650:
        decision = "declined"
    
    return {
        "decision": decision,
        "risk_score": ml_score,
        "factors": risk_factors,
        "timestamp": datetime.now().isoformat()
    }
```

### 4. Lifecycle Management
Python endpoints support initialization and cleanup hooks:

```python
# python/ml_service.py
from mxcp.runtime import on_init, on_shutdown

model = None

@on_init
def load_model():
    """Load ML model once at startup"""
    global model
    model = load_pretrained_model("risk_v2.pkl")

@on_shutdown  
def cleanup():
    """Clean up resources"""
    if model:
        model.close()

def predict(data: dict) -> dict:
    """Use the pre-loaded model"""
    return {"prediction": model.predict(data)}
```

## 🛠️ Core Concepts

### Tools, Resources, Prompts
Define your AI interface using MCP (Model Context Protocol) specs:
- **Tools** — Functions that process data and return results (SQL or Python)
- **Resources** — Data sources and caches  
- **Prompts** — Templates for LLM interactions

### Implementation Languages
MXCP supports two implementation approaches:
- **SQL** — Best for data queries, aggregations, and transformations. Uses DuckDB's powerful SQL engine.
- **Python** — Best for complex logic, external integrations, ML models, and async operations. Full access to the Python ecosystem.

Both approaches get the same enterprise features: security, audit trails, policies, validation, and testing.

### Project Structure
MXCP enforces an organized directory structure for better project management:

```
your-project/
├── mxcp-site.yml    # Project configuration
├── tools/           # MCP tool definitions (.yml files)
├── resources/       # MCP resource definitions (.yml files)
├── prompts/         # MCP prompt definitions (.yml files)
├── evals/           # Evaluation definitions (.yml files)
├── python/          # Python implementation files for endpoints
├── sql/             # SQL implementation files (for complex queries)
├── drift/           # Schema drift detection snapshots
├── audit/           # Audit logs (when enabled)
├── models/          # dbt models (if using dbt)
└── target/          # dbt target directory (if using dbt)
```

### CLI Commands

#### 🚀 Core Commands
```bash
mxcp init            # Initialize new project
mxcp serve           # Start production MCP server
mxcp list            # List all endpoints
```

#### ✅ Quality Assurance
```bash
mxcp validate        # Check types, SQL, and references
mxcp test            # Run endpoint tests  
mxcp lint            # Improve metadata for LLM usage
mxcp evals           # Test how AI models use your endpoints
```

#### 🔄 Data Management
```bash
mxcp dbt run         # Run dbt transformations
mxcp drift-check     # Check for schema changes
mxcp drift-snapshot  # Create drift detection baseline
```

#### 🔍 Operations & Monitoring
```bash
mxcp log             # Query audit logs
mxcp query           # Execute endpoints directly
mxcp run             # Run a specific endpoint
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

### ⚡ Features
- **[Features Overview](https://github.com/raw-labs/mxcp/blob/main/docs/features/overview.md)** - Complete guide to all MXCP capabilities
- **[Python Endpoints](https://github.com/raw-labs/mxcp/blob/main/docs/features/python-endpoints.md)** - Build complex tools with Python
- **[Policy Enforcement](https://github.com/raw-labs/mxcp/blob/main/docs/features/policies.md)** - Access control and data filtering
- **[Drift Detection](https://github.com/raw-labs/mxcp/blob/main/docs/features/drift-detection.md)** - Monitor schema and endpoint changes
- **[Audit Logging](https://github.com/raw-labs/mxcp/blob/main/docs/features/auditing.md)** - Enterprise-grade logging and compliance

### 📖 Guides
- **[Configuration Guide](https://github.com/raw-labs/mxcp/blob/main/docs/guides/configuration.md)** - Complete configuration reference
- **[Authentication](https://github.com/raw-labs/mxcp/blob/main/docs/guides/authentication.md)** - OAuth setup and security
- **[Integrations](https://github.com/raw-labs/mxcp/blob/main/docs/guides/integrations.md)** - LLM platforms, dbt, and data sources
- **[Quality & Testing](https://github.com/raw-labs/mxcp/blob/main/docs/guides/quality.md)** - Validation, testing, linting, and evals

### 📋 Reference
- **[CLI Reference](https://github.com/raw-labs/mxcp/blob/main/docs/reference/cli.md)** - Complete command-line interface documentation
- **[Type System](https://github.com/raw-labs/mxcp/blob/main/docs/reference/type-system.md)** - Data validation and type definitions
- **[Plugins](https://github.com/raw-labs/mxcp/blob/main/docs/reference/plugins.md)** - Custom Python extensions and UDFs

## 🤝 Contributing

We welcome contributions! See our [development guide](https://github.com/raw-labs/mxcp/blob/main/docs/contributors/dev-guide.md) to get started.

## 🏢 Enterprise Support

MXCP is developed by RAW Labs for production data-to-AI workflows. For enterprise support, custom integrations, or consulting:

- 📧 Contact: [mxcp@raw-labs.com](mailto:mxcp@raw-labs.com)
- 🌐 Website: [mxcp.dev](https://mxcp.dev)

## 📄 License

MXCP is released under the Business Source License 1.1 (BSL). It is free to use for development, testing, and most production scenarios. However, production use as part of a hosted or managed service that enables third parties to run models, workflows, or database queries requires a commercial license. This includes:

- Model execution platforms
- API marketplaces  
- Database-as-a-Service (DBaaS) products
- Any hosted service offering MXCP functionality to third parties

The license automatically converts to the MIT license four years after the release of each version. You can view the source code and contribute to its development.

For commercial licensing inquiries, please contact [mxcp@raw-labs.com](mailto:mxcp@raw-labs.com).

---

**Built for production AI applications**: Enterprise-grade MCP framework that combines the simplicity of YAML configuration with the power of SQL and Python, wrapped in comprehensive security and governance.
