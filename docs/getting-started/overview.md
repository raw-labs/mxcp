---
title: "Overview"
description: "Learn about MXCP, an enterprise-grade MCP framework for building production AI tools with SQL or Python, featuring security, audit trails, and policy enforcement."
keywords: 
  - mxcp
  - model context protocol
  - mcp framework
  - enterprise mcp
  - python mcp
  - sql mcp
  - ai tools
  - production ai
  - llm tools
sidebar_position: 1
slug: /
---

# MXCP Overview

MXCP is an enterprise-grade MCP (Model Context Protocol) framework that provides a **complete methodology** for building production-ready AI tools. More than just supporting SQL and Python, MXCP offers a structured approach to creating secure, testable, and governable AI applications.

## Why MXCP?

While other MCP servers focus on quick integrations, MXCP provides the **right way** to build production AI tools:

### The Structured Approach

1. **Data Quality First**: Start with proper data modeling using dbt
   - Create data models with clear schemas
   - Implement data quality tests
   - Build performance-optimized views
   - Document your data contracts

2. **Service Design**: Plan before you build
   - Define comprehensive type systems
   - Design security policies upfront
   - Create clear API contracts
   - Structure your endpoints logically

3. **Smart Implementation**: Use the right tool for the job
   - SQL for data queries and aggregations
   - Python for complex logic and integrations
   - Combine both for complete solutions

4. **Quality Assurance**: Test at every level
   - Validate structure and schemas
   - Test functionality with real data
   - Lint for LLM comprehension
   - Evaluate AI behavior safety

5. **Production Operations**: Deploy with confidence
   - Monitor schema drift
   - Track every operation
   - Analyze performance
   - Scale securely

### Enterprise Features

- **Security**: OAuth authentication, RBAC, policy enforcement
- **Audit Trails**: Complete tracking for compliance
- **Type Safety**: Validation across SQL and Python
- **Testing**: Comprehensive quality assurance
- **Monitoring**: Drift detection and performance tracking

## Core Architecture

MXCP provides a flexible framework that supports multiple implementation approaches:

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

### Framework Components

#### 1. Implementation Layer

Choose the right tool for each endpoint:

- **SQL Endpoints**: Best for data queries, aggregations, and transformations
  - Powered by DuckDB's analytical engine
  - Support for dbt models and transformations
  - Native handling of various data formats (Parquet, CSV, JSON)

- **Python Tools**: Best for complex logic and integrations
  - Full Python ecosystem access
  - Async/await support for concurrent operations  
  - Runtime services for database access and secrets
  - Lifecycle hooks for initialization and cleanup

#### 2. Framework Services

Every endpoint gets these enterprise features automatically:

- **Security & Policies**: OAuth, RBAC, fine-grained access control
- **Type System**: Comprehensive validation across SQL and Python
- **Audit Engine**: Track every operation for compliance
- **Validation & Tests**: Ensure quality before deployment

#### 3. Runtime Environment

MXCP provides a consistent runtime for all implementations:

- **Database Access**: `mxcp.runtime.db` for Python endpoints
- **Configuration**: Access to secrets and settings
- **Plugin System**: Extend with custom Python functions
- **Session Management**: Thread-safe execution for concurrent requests

## Key Features

### 1. Choose Your Implementation

- **SQL for Data**: Query databases, aggregate data, join tables
- **Python for Logic**: Call APIs, run ML models, process files
- **Mix & Match**: Use both in the same project for maximum flexibility

### 2. Enterprise-Ready

- **Authentication**: OAuth support for GitHub, Google, Microsoft, and more
- **Policy Engine**: Fine-grained access control with CEL expressions
- **Audit Trails**: Track every operation for compliance
- **Type Safety**: Comprehensive validation across all languages

### 3. Developer Experience

- **Local-First**: Develop and test locally before deployment
- **Hot Reload**: Changes take effect immediately
- **Comprehensive Testing**: Unit tests, integration tests, and LLM evaluations
- **Rich Documentation**: Auto-generated from your YAML definitions

### 4. Production Features

- **Drift Detection**: Monitor schema and API changes
- **Performance**: Async support, connection pooling, caching
- **Monitoring**: Built-in metrics and logging
- **Scalability**: From local development to production deployment

## Getting Started

1. Install MXCP:
   ```bash
   pip install mxcp
   ```

2. Create a new project:
   ```bash
   mxcp init
   ```

3. Define your endpoints using either SQL or Python:

   **SQL Example** (for data queries):
   ```yaml
   # tools/sales_report.yml
   mxcp: 1
   tool:
     name: sales_report
     description: Get sales by region
     parameters:
       - name: region
         type: string
     return:
       type: object
     source:
       code: |
         SELECT 
           SUM(amount) as total,
           COUNT(*) as transactions
         FROM sales 
         WHERE region = $region
   ```

   **Python Example** (for complex logic):
   ```yaml
   # tools/analyze_sentiment.yml
   mxcp: 1
   tool:
     name: analyze_sentiment
     description: Analyze text sentiment
     language: python
     parameters:
       - name: text
         type: string
     return:
       type: object
     source:
       file: ../python/text_analysis.py
   ```

   ```python
   # python/text_analysis.py
   from mxcp.runtime import db, config
   
   def analyze_sentiment(text: str) -> dict:
       # Use any Python library or API
       sentiment_score = calculate_sentiment(text)
       
       # Access database if needed
       similar_texts = db.execute(
           "SELECT * FROM texts WHERE sentiment_score BETWEEN $min AND $max",
           {"min": sentiment_score - 0.1, "max": sentiment_score + 0.1}
       )
       
       return {
           "text": text,
           "sentiment_score": sentiment_score,
           "sentiment_label": get_label(sentiment_score),
           "similar_count": len(similar_texts)
       }
   ```

4. Start the server:
   ```bash
   mxcp serve
   ```

Your AI tools are now available with full security, audit trails, and policy enforcement!

## Next Steps

- [Quickstart Guide](quickstart.md) - Get up and running with MXCP
- [Python Endpoints](../features/python-endpoints.md) - Build complex tools with Python
- [Type System](../reference/type-system.md) - Learn about MXCP's type system
- [Configuration](../guides/configuration.md) - Configure your MXCP project
- [Quality & Testing](../guides/quality.md) - Write tests, run LLM evals, and ensure endpoint quality
- [Authentication](../guides/authentication.md) - Set up OAuth authentication
- [CLI Reference](../reference/cli.md) - Explore available commands
- [Integrations](../guides/integrations.md) - Connect with other tools and services 