---
title: "Features Overview"
description: "Complete overview of MXCP's enterprise features for production data-to-AI workflows"
sidebar_position: 1
slug: /features
---

# MXCP Features Overview

MXCP provides a comprehensive set of enterprise features designed for production data-to-AI workflows. Unlike simple data connectors, MXCP offers security, governance, quality assurance, and operational excellence.

## 🔒 Security & Governance

### [Authentication & Authorization](../guides/authentication.md)
- **OAuth 2.0 Integration**: GitHub, Atlassian, Salesforce, and custom providers
- **Session Management**: Secure token handling with persistence
- **Role-Based Access Control**: Fine-grained permissions and scopes
- **API Key Support**: For programmatic access
- **Stateless Mode**: For serverless deployments

### [Policy Enforcement](./policies.md)
- **Input Policies**: Control who can execute endpoints
- **Output Policies**: Filter sensitive data dynamically
- **CEL Expressions**: Flexible condition evaluation
- **User Context**: Rich context for policy decisions
- **Field-Level Security**: Mask or remove specific fields

### [Audit Logging](./auditing.md)
- **Complete Trail**: Every query, result, and error logged
- **User Attribution**: Track who did what and when
- **Flexible Storage**: JSONL files or DuckDB
- **Query Interface**: Search and analyze audit logs
- **Compliance Ready**: Export for regulatory requirements

## ✅ Quality Assurance

### [Validation](../guides/quality.md#validation)
- **Schema Validation**: Ensure endpoints meet specifications
- **Type Checking**: Validate parameter and return types
- **SQL Verification**: Check query syntax
- **Reference Validation**: Verify file and resource references

### [Testing](../guides/quality.md#testing)
- **Unit Tests**: Test endpoints with various inputs
- **Assertion Types**: Exact match, partial match, exclusions
- **Policy Testing**: Verify access controls work correctly
- **CI/CD Integration**: JSON output for automation

### [Linting](../guides/quality.md#linting)
- **Metadata Quality**: Improve LLM understanding
- **Best Practices**: Suggest descriptions, examples, tags
- **Severity Levels**: Warnings and suggestions
- **Bulk Analysis**: Check entire codebase at once

### [LLM Evaluation](../guides/quality.md#llm-evaluation-evals)
- **AI Behavior Testing**: Verify LLMs use tools correctly
- **Safety Checks**: Ensure destructive operations are avoided
- **Context Testing**: Validate permission-based access
- **Model Support**: Test with multiple AI models

## 🔄 Data & Operations

### [Drift Detection](./drift-detection.md)
- **Schema Monitoring**: Track changes across environments
- **Baseline Snapshots**: Compare against known good state
- **Change Detection**: Identify added, modified, removed endpoints
- **CI/CD Integration**: Prevent breaking changes

### [dbt Integration](../guides/integrations.md#dbt-integration)
- **Native Support**: Run dbt models directly
- **Local Caching**: Use dbt to populate DuckDB
- **Model Discovery**: Automatic model detection
- **Transformation Pipeline**: ETL/ELT workflows

### [Monitoring & Operations](../reference/cli.md)
- **Health Checks**: Endpoint availability monitoring
- **Performance Metrics**: Query execution times
- **Error Tracking**: Detailed error logs and traces
- **Operational Commands**: Direct endpoint execution

## 🚀 Developer Experience

### [Type System](../reference/type-system.md)
- **Rich Types**: Primitives, objects, arrays, dates
- **Validation**: Automatic input/output validation
- **Constraints**: Min/max, patterns, enums
- **LLM Hints**: Help AI understand data types

### [SQL Reference](../reference/sql.md)
- **DuckDB Syntax**: PostgreSQL-compatible analytical SQL
- **Built-in Functions**: User authentication functions
- **Named Parameters**: Safe parameter binding
- **Extensions**: httpfs, json, parquet, and more

### [Python Reference](../reference/python.md)
- **Runtime APIs**: Database, config, secrets access
- **Lifecycle Hooks**: Server initialization/shutdown/reload
- **Thread Safety**: Concurrent execution support
- **Type Compatibility**: Seamless SQL/Python integration

### [Plugin System](../reference/plugins.md)
- **Python Extensions**: Custom functions and UDFs
- **Provider Plugins**: OAuth and authentication
- **Shared Libraries**: Reusable components
- **Hot Reloading**: Development productivity

### [CLI Tools](../reference/cli.md)
- **Project Management**: Init, serve, list
- **Quality Tools**: Validate, test, lint, evals
- **Operations**: Log queries, drift checks
- **Development**: Live reload, debug mode

## 🔌 Integrations

### [LLM Platforms](../guides/integrations.md#llm-integration)
- **Claude Desktop**: Native MCP support
- **OpenAI Tools**: Via adapters
- **Custom Clients**: MCP protocol implementation
- **Multi-Model**: Support various AI providers

### [Data Sources](../guides/integrations.md#data-sources)
- **DuckDB**: Built-in analytical database
- **SQL Databases**: Via DuckDB extensions
- **APIs**: HTTP/REST endpoints
- **Files**: CSV, Parquet, JSON

### [Secret Management](../guides/configuration.md#vault-integration-optional)
- **HashiCorp Vault**: Enterprise secret storage
- **Environment Variables**: Simple secret injection
- **Encrypted Storage**: Secure local secrets
- **Runtime Injection**: No secrets in code

## 📊 Use Cases

MXCP's features enable powerful use cases:

- **Secure AI Analytics**: Give LLMs data access with governance
- **Compliant Automation**: Track all AI actions for audit
- **Multi-Tenant SaaS**: Isolate customer data with policies
- **Data Products**: Package data as AI-ready interfaces
- **DevOps Automation**: Monitor and control infrastructure

## Getting Started

1. **[Quickstart Guide](../getting-started/quickstart.md)** - Get running in 60 seconds
2. **[Configuration](../guides/configuration.md)** - Set up your project
3. **[Write Endpoints](../getting-started/overview.md#endpoints)** - Create your first tool
4. **[Add Security](./policies.md)** - Implement access control
5. **[Test & Deploy](../guides/quality.md)** - Ensure quality

---

*MXCP combines enterprise features with developer productivity, making it the ideal platform for production data-to-AI workflows.* 