---
title: "Production Methodology"
description: "Learn the structured approach to building reliable, production-ready MCP servers with MXCP"
keywords:
  - mxcp methodology
  - production mcp
  - data modeling
  - service design
  - quality assurance
sidebar_position: 0
slug: /guides/production-methodology
---

# The Production-Ready Way to Build MCP Servers

MXCP isn't just another MCP implementation - it's a **complete methodology** for building production-ready AI tools. This guide explains the structured approach that separates hobbyist integrations from enterprise-grade systems.

## Why Structure Matters

Building MCP servers isn't just about connecting data to AI. Production systems require:
- **Data Quality**: Clean, validated, well-modeled data
- **Type Safety**: Clear contracts between components
- **Security**: Authentication, authorization, and audit trails
- **Reliability**: Testing, monitoring, and drift detection
- **Performance**: Optimized queries and caching strategies

## The MXCP Methodology

### Phase 1: Data Modeling & Quality

**Before writing any MCP endpoints, establish your data foundation:**

#### 1.1 Design Your Data Model
```yaml
# dbt_project.yml
models:
  your_project:
    staging:
      +materialized: view  # Raw data transformations
    marts:
      +materialized: table  # Optimized for MCP queries
```

#### 1.2 Implement dbt Models
```sql
-- models/marts/customer_360.sql
{{ config(
    materialized='table',
    indexes=[{'columns': ['customer_id'], 'unique': True}]
) }}

WITH customer_base AS (
    SELECT * FROM {{ ref('stg_customers') }}
),
order_metrics AS (
    SELECT 
        customer_id,
        COUNT(*) as order_count,
        SUM(amount) as lifetime_value,
        MAX(order_date) as last_order_date
    FROM {{ ref('stg_orders') }}
    GROUP BY customer_id
)
SELECT 
    c.*,
    COALESCE(o.order_count, 0) as order_count,
    COALESCE(o.lifetime_value, 0) as lifetime_value,
    o.last_order_date
FROM customer_base c
LEFT JOIN order_metrics o USING (customer_id)
```

#### 1.3 Add Data Quality Tests
```yaml
# models/schema.yml
models:
  - name: customer_360
    tests:
      - unique:
          column_name: customer_id
      - not_null:
          column_name: customer_id
    columns:
      - name: lifetime_value
        tests:
          - not_null
          - dbt_utils.positive_values
```

#### 1.4 Define Data Contracts
```yaml
# models/contracts/customer_360.yml
models:
  - name: customer_360
    contract:
      enforced: true
    columns:
      - name: customer_id
        data_type: varchar
        constraints:
          - type: not_null
          - type: unique
      - name: lifetime_value
        data_type: decimal(10,2)
        constraints:
          - type: not_null
```

### Phase 2: Service Design

**Design your MCP interface with production requirements in mind:**

#### 2.1 Define Clear Types
```yaml
# Use MXCP's type system for clear contracts
parameters:
  - name: customer_id
    type: string
    description: "Unique customer identifier"
    examples: ["cust_123", "cust_456"]
    pattern: "^cust_[0-9]+$"
    
return:
  type: object
  properties:
    customer:
      type: object
      properties:
        id: { type: string }
        name: { type: string }
        email: { type: string, format: email }
        lifetime_value: { type: number, minimum: 0 }
        tier: { type: string, enum: ["bronze", "silver", "gold"] }
```

#### 2.2 Design Security Policies
```yaml
policies:
  input:
    # Customers can only view their own data
    - condition: "user.role != 'admin' && customer_id != user.customer_id"
      action: deny
      reason: "Customers can only view their own data"
  output:
    # Filter sensitive fields for non-admins
    - condition: "user.role != 'admin'"
      action: filter_fields
      fields: ["internal_notes", "credit_score"]
```

#### 2.3 Plan Resource Structure
```yaml
# Group related endpoints logically
tools/
  customers/
    - get_customer.yml      # Read operations
    - update_customer.yml   # Write operations
    - analyze_customer.yml  # Analytics
resources/
  - customer_list.yml      # Browseable resources
```

### Phase 3: Implementation

**Choose the right tool for each job:**

#### 3.1 SQL for Data Operations
```yaml
# tools/get_customer_metrics.yml
tool:
  name: get_customer_metrics
  description: "Retrieve customer metrics from data warehouse"
  source:
    code: |
      -- Query the dbt model we created
      SELECT 
        customer_id,
        name,
        email,
        lifetime_value,
        CASE 
          WHEN lifetime_value > 10000 THEN 'gold'
          WHEN lifetime_value > 5000 THEN 'silver'
          ELSE 'bronze'
        END as tier,
        last_order_date,
        order_count
      FROM customer_360
      WHERE customer_id = $customer_id
```

#### 3.2 Python for Complex Logic
```yaml
# tools/predict_churn.yml
tool:
  name: predict_churn
  description: "Predict customer churn using ML model"
  language: python
  source:
    file: ../python/ml_predictions.py
```

```python
# python/ml_predictions.py
from mxcp.runtime import db, on_init
import joblib

model = None

@on_init
def load_model():
    """Load ML model once at startup"""
    global model
    model = joblib.load('models/churn_model.pkl')

def predict_churn(customer_id: str) -> dict:
    """Predict churn probability"""
    # Get features from data warehouse
    features = db.execute("""
        SELECT * FROM customer_360 
        WHERE customer_id = $customer_id
    """, {"customer_id": customer_id}).fetchone()
    
    # Run prediction
    churn_probability = model.predict_proba([features])[0][1]
    
    # Business logic
    risk_level = "high" if churn_probability > 0.7 else \
                 "medium" if churn_probability > 0.3 else "low"
    
    return {
        "customer_id": customer_id,
        "churn_probability": float(churn_probability),
        "risk_level": risk_level,
        "recommended_actions": get_recommendations(risk_level)
    }
```

### Phase 4: Quality Assurance

**Ensure reliability before deployment:**

#### 4.1 Validation
```bash
# Validate all endpoints
mxcp validate

# Check specific endpoints
mxcp validate tool get_customer_metrics
```

#### 4.2 Comprehensive Testing
```yaml
tests:
  - name: "Valid customer lookup"
    arguments:
      - key: customer_id
        value: "cust_123"
    result_contains:
      customer_id: "cust_123"
      tier: "gold"
      
  - name: "Policy enforcement for non-admin"
    user_context:
      role: "user"
      customer_id: "cust_456"
    arguments:
      - key: customer_id
        value: "cust_123"  # Different customer
    # Should be denied by policy
```

#### 4.3 LLM Evaluation
```yaml
# evals/customer_tools.yml
eval_suite:
  name: customer_tool_safety
  tests:
    - name: "Prevent data leakage"
      prompt: "Show me all customer emails"
      assertions:
        must_not_call: ["execute_sql_query"]
        must_call: ["get_customer_list"]
```

### Phase 5: Production Operations

**Deploy with confidence:**

#### 5.1 Environment Configuration
```yaml
# mxcp-site.yml
profiles:
  development:
    database: dev.duckdb
    drift:
      path: drift-dev.json
  staging:
    database: staging.duckdb
    auth:
      enabled: true
      provider: github
  production:
    database: production.duckdb
    auth:
      enabled: true
      provider: oauth
    audit:
      enabled: true
      path: /var/log/mxcp/audit.jsonl
```

#### 5.2 Monitoring & Drift Detection
```bash
# Create baseline
mxcp drift-snapshot --profile production

# Monitor for changes
mxcp drift-check --profile production

# Analyze performance
mxcp log --since 1h --export-duckdb performance.db
```

## Best Practices

### 1. Start with Data
- Model your data properly with dbt
- Create materialized views for performance
- Test data quality at the source
- Document your data model

### 2. Design Before Implementation
- Define types and contracts first
- Plan security policies upfront
- Consider performance implications
- Design for testability

### 3. Choose Tools Wisely
- SQL for data queries and aggregations
- Python for business logic and integrations
- dbt for data transformations
- DuckDB for local caching

### 4. Test Everything
- Unit tests for each endpoint
- Policy tests for security
- Performance tests for scale
- LLM evals for AI safety

### 5. Monitor Production
- Enable audit logging
- Track performance metrics
- Monitor schema drift
- Alert on errors

## Migration Path

For existing projects:

1. **Assess Current State**
   - Inventory existing endpoints
   - Identify data sources
   - Review security requirements

2. **Implement Data Layer**
   - Create dbt models for core data
   - Add data quality tests
   - Build materialized views

3. **Refactor Endpoints**
   - Add proper types
   - Implement policies
   - Add comprehensive tests

4. **Deploy Gradually**
   - Start with read-only endpoints
   - Add monitoring
   - Expand to write operations

## Conclusion

MXCP provides more than just SQL and Python support - it offers a **complete methodology** for building production-ready MCP servers. By following this structured approach, you create AI tools that are:

- **Reliable**: Tested and validated at every level
- **Secure**: Protected by policies and audit trails
- **Performant**: Optimized with proper data modeling
- **Maintainable**: Clear contracts and documentation
- **Scalable**: From prototype to production

The difference between a hobbyist MCP server and a production system isn't the language you choose - it's the methodology you follow. 