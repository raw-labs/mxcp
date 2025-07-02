# MXCP Design Guide

MXCP (Model Execution + Context Protocol) is a developer-first toolkit that enables you to serve operational data to AI applications through a well-governed, testable interface. It combines the power of SQL, the flexibility of DuckDB, and the reliability of dbt to create a complete solution for AI data integration.

This design guide outlines the essential architecture, components, and workflows that make MXCP a powerful local-first tool with optional cloud orchestration.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Core Components](#core-components)
- [Configuration System](#configuration-system)
- [Endpoint Definitions](#endpoint-definitions)
- [Type System](#type-system)
- [Command Reference](#command-reference)
- [Policy System](#policy-system)
- [Extensions and Integrations](#extensions-and-integrations)
- [Development Workflow](#development-workflow)
- [Deployment Models](#deployment-models)
- [Implementation Architecture](#implementation-architecture)

## Architecture Overview

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

The design philosophy is simple: **clone a repository, run `mxcp serve`, and you're ready to serve AI-compatible endpoints** from your operational data. No external services or coordination layers required.

### Design Principles

1. **Local-First**: Full development environment in a single command
2. **Declarative**: All endpoints, policies, and configuration defined in version-controlled YAML
3. **Type-Safe**: Comprehensive type system with validation
4. **Testable**: Built-in testing framework for all endpoints
5. **Governed**: Policy-based access control and audit logging
6. **Extensible**: Plugin system for custom data sources and transformations

## Core Components

### 1. DuckDB: The Execution Engine

DuckDB serves as the runtime engine, providing:

- **Native Analytics Support**: Built-in OLAP capabilities and columnar data formats
- **Python Integration**: Support for Python UDFs via embedded extensions
- **Local-First Development**: File-based persistence with no server required
- **Flexible I/O**: Native support for various data sources (Parquet, CSV, JSON, HTTP, S3)
- **Extensions**: Support for core, community, and nightly extensions

Key features:
- Automatic secret injection from user configuration
- Python bootstrap support for custom functions
- Custom secret types for external system integration
- Seamless SQL parameter binding and type conversion

### 2. dbt: The Transformation Layer

dbt provides declarative ETL capabilities:

- **SQL-Based Transformations**: Define models as views or materialized tables
- **Git-Managed**: Version control for all data transformations
- **DuckDB Integration**: Native support via dbt-duckdb adapter
- **Automatic Configuration**: MXCP manages dbt profiles and setup
- **State Validation**: Ensures models are up-to-date before serving endpoints

### 3. MXCP CLI: The Orchestration Layer

The MXCP CLI orchestrates the entire system:

- **Project Management**: Reads configuration and manages environments
- **MCP Server**: Serves endpoints via multiple transport protocols
- **Validation**: Type checking, schema validation, and test execution
- **Policy Enforcement**: Access control and data filtering
- **Audit Logging**: Comprehensive execution tracking
- **Development Tools**: Initialization, validation, and testing utilities

## Configuration System

MXCP uses a two-tier configuration system for maximum flexibility and security.

### User Configuration (`~/.mxcp/config.yml`)

The user configuration file stores personal settings, secrets, and profiles:

```yaml
mxcp: 1

# Default transport settings
transport:
  provider: "streamable-http"  # streamable-http, sse, or stdio
  http:
    port: 8000
    host: "localhost"
    stateless: false  # Enable for serverless deployments

# Vault integration (optional)
vault:
  enabled: true
  address: "https://vault.example.com"
  token_env: "VAULT_TOKEN"

# Projects and profiles
projects:
  my_project:
    profiles:
      dev:
        secrets:
          - name: "database"
            type: "postgresql"
            parameters:
              host: "localhost"
              database: "${DB_NAME}"
              username: "vault://secret/db#username"
              password: "vault://secret/db#password"
          - name: "api_keys"
            type: "custom"
            parameters:
              public_key: "file:///path/to/public_key.pem"
              private_key: "file://keys/private_key.pem"
        auth:
          provider: "github"
          github:
            client_id: "${GITHUB_CLIENT_ID}"
            client_secret: "${GITHUB_CLIENT_SECRET}"
```

**Key Features:**
- **Environment Variable Interpolation**: Use `${ENV_VAR}` syntax
- **Vault Integration**: Use `vault://path/to/secret#key` for secure secret retrieval
- **File References**: Use `file://path/to/file` to read values from local files
  - Absolute paths: `file:///absolute/path/to/file`
  - Relative paths: `file://relative/path/to/file` (relative to current working directory)
- **Profile-Based**: Multiple environments per project
- **Transport Configuration**: Default settings for server protocols

### Configuration Interpolation

Both user and site configurations support several forms of value interpolation:

1. **Environment Variables**: Use `${ENV_VAR}` syntax to reference environment variables
2. **Vault Integration**: Use `vault://path/to/secret#field` URLs to fetch secrets from HashiCorp Vault
3. **File References**: Use `file:///path/to/file` or `file://relative/path` URLs to read values from files

Example:
```yaml
projects:
  my_project:
    profiles:
      production:
        secrets:
          - name: database
            parameters:
              password: ${DB_PASSWORD}              # From environment
              api_key: vault://secret/api#key      # From Vault
              ssl_cert: file:///etc/ssl/cert.pem   # From file
```

### Hot Reload Architecture

The MCP server supports hot reloading of external configuration values via SIGHUP signal. This is designed for safe updates in production environments:

**Design Principles:**
1. **Configuration templates are immutable** - Files are read once at startup
2. **Only external values are refreshed** - vault://, file://, ${ENV_VAR}
3. **No structural changes** - Service topology remains stable
4. **Graceful handling** - Active requests complete before reload

**Implementation:**
- `ExternalRefTracker` scans configs at startup, building a registry of all external references
- On SIGHUP, only these tracked references are re-resolved
- Runtime components (DB, Python) are always recreated to ensure fresh state
- If resolution fails, the server continues with existing values

**Benefits:**
- Safe for production - no risk from accidental config file changes
- Fast - only resolves what's needed
- Predictable - operators know exactly what will change
- Reliable - failures don't crash the service

### Repository Configuration (`mxcp-site.yml`)

The repository configuration defines project-specific settings:

```yaml
mxcp: 1
project: "my_project"
profile: "dev"

# Secrets used by this repository
secrets:
  - "database"
  - "api_credentials"

# DuckDB extensions
extensions:
  - "httpfs"
  - "parquet"
  - name: "h3"
    repo: "community"

# dbt integration
dbt:
  enabled: true
  model-paths: "models"

# Profile-specific overrides
profiles:
  dev:
    duckdb:
      path: "dev.duckdb"
      readonly: false
    drift:
      path: "drift-dev.json"
  prod:
    duckdb:
      path: "prod.duckdb"
      readonly: true
    drift:
      path: "drift-prod.json"

# Built-in SQL tools (disabled by default)
sql_tools:
  enabled: false
```

## Endpoint Definitions

MXCP supports three types of endpoints, each defined in YAML files:

### Tools

Tools are functions that can be called with parameters and return structured data:

```yaml
mxcp: 1
tool:
  name: "user_lookup"
  description: "Look up user information by email"
  tags: ["users", "lookup"]
  annotations:
    title: "User Lookup"
    readOnlyHint: true
    idempotentHint: true
  parameters:
    - name: "email"
      type: "string"
      format: "email"
      description: "User's email address"
      examples: ["user@example.com"]
    - name: "include_balance"
      type: "boolean"
      description: "Include account balance"
      default: false
  return:
    type: "object"
    properties:
      user_id:
        type: "integer"
      name:
        type: "string"
      balance:
        type: "number"
        sensitive: true
    required: ["user_id", "name"]
  language: "sql"
  source:
    file: "queries/user_lookup.sql"
  tests:
    - name: "lookup_existing_user"
      description: "Test lookup of existing user"
      arguments:
        - key: "email"
          value: "test@example.com"
        - key: "include_balance"
          value: true
      result:
        user_id: 123
        name: "Test User"
        balance: 1000.00
  policies:
    input:
      - condition: "!('user.read' in user.permissions)"
        action: "deny"
        reason: "Missing user.read permission"
    output:
      - condition: "user.role != 'admin'"
        action: "filter_sensitive_fields"
        reason: "Non-admin users cannot see sensitive data"
```

### Resources

Resources provide data that can be accessed via URI patterns:

```yaml
mxcp: 1
resource:
  uri: "users://profile/{user_id}"
  description: "User profile data"
  mime_type: "application/json"
  parameters:
    - name: "user_id"
      type: "integer"
      description: "User ID to retrieve"
  return:
    type: "object"
    properties:
      profile:
        type: "object"
        properties:
          name:
            type: "string"
          preferences:
            type: "object"
  source:
    file: "queries/user_profile.sql"
```

### Prompts

Prompts are templates for AI interactions with parameter substitution:

```yaml
mxcp: 1
prompt:
  name: "user_summary"
  description: "Generate a summary for a user"
  parameters:
    - name: "user_id"
      type: "integer"
      description: "User ID to summarize"
    - name: "include_activity"
      type: "boolean"
      description: "Include recent activity"
      default: true
  messages:
    - role: "system"
      type: "text"
      prompt: "You are a helpful assistant that summarizes user profiles."
    - role: "user"
      type: "text"
      prompt: |
        Please summarize the following user profile:
        User ID: {{ user_id }}
        {% if include_activity %}
        Include their recent activity in the summary.
        {% endif %}
```

## Type System

MXCP uses a comprehensive type system that ensures data integrity and provides clear API contracts.

### Base Types

| Type     | Description           | DuckDB Type | Example         |
|----------|-----------------------|-------------|-----------------|
| string   | Text values           | VARCHAR     | `"hello"`       |
| number   | Floating-point        | DOUBLE      | `3.14`          |
| integer  | Whole number          | INTEGER     | `42`            |
| boolean  | true/false            | BOOLEAN     | `true`          |
| array    | Ordered list          | ARRAY       | `["a", "b"]`    |
| object   | Key-value structure   | STRUCT      | `{"key": "val"}`|

### Format Annotations

String types can be specialized with format annotations:

| Format    | Description              | Example                  | DuckDB Type              |
|-----------|--------------------------|--------------------------|--------------------------|
| email     | Email address            | `"user@example.com"`     | VARCHAR                  |
| uri       | URI/URL                  | `"https://example.com"`  | VARCHAR                  |
| date      | ISO 8601 date            | `"2023-01-01"`          | DATE                     |
| time      | ISO 8601 time            | `"14:30:00"`            | TIME                     |
| date-time | ISO 8601 timestamp       | `"2023-01-01T14:30:00Z"`| TIMESTAMP WITH TIME ZONE |
| duration  | ISO 8601 duration        | `"P1DT2H"`              | INTERVAL                 |
| timestamp | Unix timestamp           | `1672531199`            | TIMESTAMP                |

### Sensitive Data

Fields containing sensitive information can be marked with the `sensitive` flag:

```yaml
parameters:
  - name: "password"
    type: "string"
    sensitive: true
    description: "User password (will be redacted in logs)"
```

Sensitive fields are:
- Automatically redacted in audit logs
- Subject to policy-based filtering
- Clearly documented for security awareness

## Command Reference

### Core Commands

| Command                | Purpose                                        |
|------------------------|------------------------------------------------|
| `mxcp init`           | Initialize a new MXCP repository               |
| `mxcp serve`          | Start the MCP server                           |
| `mxcp run`            | Execute a specific endpoint                    |
| `mxcp query`          | Run SQL queries directly                       |
| `mxcp validate`       | Validate endpoint definitions                  |
| `mxcp test`           | Run endpoint tests                             |
| `mxcp list`           | List all available endpoints                   |

### Development Commands

| Command                | Purpose                                        |
|------------------------|------------------------------------------------|
| `mxcp drift-snapshot` | Create a baseline snapshot for change detection|
| `mxcp drift-check`    | Check for changes against baseline             |
| `mxcp dbt-config`     | Configure dbt integration                      |
| `mxcp dbt`            | Run dbt commands with secret injection         |

### Audit and Monitoring

| Command                | Purpose                                        |
|------------------------|------------------------------------------------|
| `mxcp log`            | Query audit logs                               |

### Example Usage

```bash
# Initialize a new project
mxcp init my-project --bootstrap

# Start the server
mxcp serve --port 8080

# Run a specific tool
mxcp run tool user_lookup --param email=user@example.com

# Validate all endpoints
mxcp validate

# Run tests
mxcp test

# Check for schema drift
mxcp drift-check
```

## Policy System

MXCP includes a powerful policy system for access control and data governance:

### Policy Types

1. **Input Policies**: Control who can access endpoints
2. **Output Policies**: Filter or mask response data

### Policy Actions

- `allow`: Explicitly allow access
- `deny`: Block access with reason
- `warn`: Log a warning but allow
- `filter_fields`: Remove specific fields from response
- `filter_sensitive_fields`: Remove all fields marked as sensitive
- `mask_fields`: Replace field values with masked versions

### Example Policy

```yaml
policies:
  input:
    - condition: "user.role == 'guest'"
      action: "deny"
      reason: "Guests cannot access user data"
    - condition: "!('user.read' in user.permissions)"
      action: "deny"
      reason: "Missing required permission"
  output:
    - condition: "user.role != 'admin'"
      action: "filter_sensitive_fields"
      reason: "Non-admin users cannot see sensitive data"
    - condition: "user.department != 'finance'"
      action: "filter_fields"
      fields: ["balance", "credit_limit"]
      reason: "Only finance can see financial data"
```

## Extensions and Integrations

### DuckDB Extensions

MXCP supports the full ecosystem of DuckDB extensions:

```yaml
extensions:
  - "httpfs"      # Core extension
  - "parquet"     # Core extension
  - name: "h3"    # Community extension
    repo: "community"
  - name: "uc_catalog"  # Nightly extension
    repo: "core_nightly"
```

### dbt Integration

MXCP automatically manages dbt configuration and ensures models are up-to-date:

- Generates dbt profiles automatically
- Validates model state before serving
- Supports custom model paths and configurations
- Integrates with dbt testing and documentation

### Authentication

Support for OAuth-based authentication:

- GitHub OAuth
- Google OAuth
- Custom OAuth providers
- Token-based authentication
- Role-based access control

### Vault Integration

Secure secret management with HashiCorp Vault:

- Automatic secret retrieval
- Support for KV v1 and v2 engines
- Environment-based configuration
- Seamless integration with DuckDB secrets

## Development Workflow

### 1. Project Initialization

```bash
mxcp init my-project --bootstrap
cd my-project
```

### 2. Define Endpoints

Create YAML files defining tools, resources, or prompts:

```yaml
# tools/users.yml
mxcp: 1
tool:
  name: "list_users"
  description: "List users with filtering"
  # ... rest of definition
```

### 3. Write SQL

Create corresponding SQL files:

```sql
-- queries/list_users.sql
SELECT user_id, name, email, created_at
FROM users
WHERE (:status IS NULL OR status = :status)
  AND (:created_after IS NULL OR created_at >= :created_after)
ORDER BY created_at DESC
LIMIT COALESCE(:limit, 100)
```

### 4. Add Tests

Define test cases in endpoint YAML:

```yaml
tests:
  - name: "list_active_users"
    description: "Test filtering by active status"
    arguments:
      - key: "status"
        value: "active"
      - key: "limit"
        value: 10
    # Expected result validation
```

### 5. Validate and Test

```bash
mxcp validate
mxcp test
```

### 6. Serve Locally

```bash
mxcp serve
```

## Deployment Models

### Local Development

```bash
git clone https://github.com/org/my-mxcp-project.git
cd my-mxcp-project
pip install mxcp
mxcp serve
```

### CI/CD Integration

```yaml
# .github/workflows/validate.yml
- name: Validate MXCP
  run: |
    mxcp validate --json-output
    mxcp test --json-output
    mxcp drift-check --json-output
```

### Production Deployment

Options include:
- Containerized deployment with `mxcp serve`
- Serverless functions with `--stateless` mode
- Managed cloud services
- Integration with existing data platforms

### Cloud Integration

MXCP is designed to work seamlessly in cloud environments:

- Support for cloud storage (S3, GCS, Azure Blob)
- Integration with cloud databases
- Kubernetes-native deployment
- Auto-scaling capabilities

## Implementation Architecture

### Configuration Loading Strategy

MXCP follows a deliberate configuration loading pattern that prioritizes project requirements:

1. **Site Configuration First**: Load `mxcp-site.yml` to understand project structure and requirements
2. **User Configuration Second**: Load `~/.mxcp/config.yml` based on site config needs
3. **Auto-Generation**: Generate default user config in memory if file doesn't exist
4. **CLI Ownership**: Configuration loading handled at CLI layer, not in business logic

This approach enables:
- **Zero-configuration startup**: Projects work immediately after cloning
- **Clear separation of concerns**: Project requirements vs. personal settings
- **Flexible deployment**: Same project works across different environments

### DuckDB Session Architecture

MXCP's DuckDB integration is designed around session-based architecture:

#### Session Lifecycle
- **Per-Operation Sessions (CLI)**: Each command creates a fresh session
- **Shared Session (Server)**: Single session with thread-safe access
- **Session-Scoped Setup**: Extensions, secrets, and plugins loaded once per session

#### Connection Management
- **No Connection Pooling**: DuckDB is embedded, uses single connections
- **Context Manager Pattern**: Ensures proper cleanup and resource management
- **Thread Safety**: Server mode uses locking for concurrent access

#### Session Initialization
When a session starts, MXCP automatically:
1. Loads DuckDB extensions specified in site config
2. Injects secrets as DuckDB secrets for native connector access
3. Loads and initializes plugins for external data sources
4. Creates user token UDFs for authenticated access patterns

This architecture provides:
- **Consistent environment**: Same setup across all operations
- **Security isolation**: Secrets scoped to session lifetime
- **Performance**: Extensions and plugins loaded once per session
- **Reliability**: Automatic cleanup prevents resource leaks

## Key Benefits

1. **Developer Experience**: Simple, Git-based workflow with immediate feedback
2. **Type Safety**: Comprehensive validation prevents runtime errors
3. **Governance**: Policy-based access control and audit logging
4. **Performance**: DuckDB's columnar engine optimized for analytics
5. **Flexibility**: Support for multiple data sources and transformation patterns
6. **Reliability**: Built-in testing and drift detection
7. **Security**: Secure secret management and data classification

## Getting Started

1. **Install MXCP**: `pip install mxcp`
2. **Initialize Project**: `mxcp init my-project --bootstrap`
3. **Define Endpoints**: Create YAML files with tools, resources, or prompts
4. **Write SQL**: Create corresponding SQL query files
5. **Test**: Use `mxcp validate` and `mxcp test`
6. **Serve**: Run `mxcp serve` to start the MCP server
7. **Connect**: Use with Claude Desktop, custom clients, or other MCP-compatible tools

MXCP transforms the complexity of serving operational data to AI applications into a simple, declarative, and well-governed process that scales from development to production.
