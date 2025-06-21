---
title: "Configuration Guide"
description: "Complete guide to MXCP configuration including user settings, repository configuration, endpoint definitions, and environment variables."
keywords:
  - mxcp configuration
  - user config
  - site config
  - endpoint configuration
  - secrets management
  - environment variables
sidebar_position: 1
slug: /guides/configuration
---

# MXCP Configuration Guide

This guide covers all aspects of MXCP configuration, from user settings to endpoint definitions.

## User Configuration

The user configuration file (`~/.mxcp/config.yml`) stores user-specific settings and secrets.

### Environment Variable Interpolation

The user configuration file supports environment variable interpolation using `${ENV_VAR}` syntax. This allows you to reference environment variables in your configuration, which is particularly useful for sensitive values like passwords and API keys.

Example:
```yaml
mxcp: "1.0.0"
projects:
  my_project:
    profiles:
      dev:
        secrets:
          - name: "db_credentials"
            type: "database"
            parameters:
              host: "localhost"
              port: "5432"
              database: "${DB_NAME}"
              username: "${DB_USER}"
              password: "${DB_PASSWORD}"
```

If any referenced environment variable is not set, MXCP will raise an error when loading the configuration.

### Schema Version
```yaml
mxcp: "1.0.0"  # Always use this version
```

### Transport Configuration
```yaml
transport:
  provider: "streamable-http"  # Default transport: streamable-http, sse, or stdio
  http:
    port: 8000      # Default port for HTTP transport
    host: "localhost"  # Default host for HTTP transport
    stateless: false  # Enable stateless HTTP mode (default: false)
```

The transport configuration sets the default behavior for the `mxcp serve` command. You can override these settings using command-line options.

**Transport Options:**

- **provider**: The transport protocol to use
  - `streamable-http`: HTTP with streaming support (default)
  - `sse`: Server-sent events
  - `stdio`: Standard input/output

- **http**: HTTP-specific configuration
  - **port**: Port number to bind to (default: 8000)
  - **host**: Host address to bind to (default: "localhost")
  - **stateless**: Enable stateless HTTP mode (default: false)
    - When `true`, no session state is maintained between requests
    - Required for serverless deployments
    - Can be overridden with `mxcp serve --stateless`

**Example with stateless mode for serverless deployment:**
```yaml
transport:
  provider: "streamable-http"
  http:
    port: 8080
    host: "0.0.0.0"
    stateless: true
```

### Projects Configuration
```yaml
projects:
  my_project:  # Project name
    profiles:
      dev:  # Profile name
        secrets:  # List of secrets for this profile
          - name: "db_credentials"
            type: "database"
            parameters:
              host: "localhost"
              port: "5432"
              database: "mydb"
              username: "user"
              password: "pass"
        auth:  # Authentication configuration for this profile
          provider: "github"
          github:
            client_id: "your_github_client_id"
            client_secret: "your_github_client_secret"
            auth_url: "https://github.com/login/oauth/authorize"
            token_url: "https://github.com/login/oauth/access_token"
```

### Vault Integration (Optional)

MXCP supports HashiCorp Vault for secure secret management. When enabled, you can use `vault://` URLs in your configuration to retrieve secrets from Vault.

```yaml
vault:
  enabled: true
  address: "https://vault.example.com"
  token_env: "VAULT_TOKEN"  # Environment variable containing the Vault token
```

#### Using Vault URLs

Once Vault is configured, you can use `vault://` URLs anywhere in your configuration where you would normally put sensitive values:

```yaml
mxcp: "1.0.0"
vault:
  enabled: true
  address: "https://vault.example.com"
  token_env: "VAULT_TOKEN"
projects:
  my_project:
    profiles:
      dev:
        secrets:
          - name: "db_credentials"
            type: "database"
            parameters:
              host: "localhost"
              port: "5432"
              database: "mydb"
              username: "vault://secret/database#username"
              password: "vault://secret/database#password"
```

**Vault URL Format:** `vault://path/to/secret#key`

- `path/to/secret`: The path to the secret in Vault
- `key`: The specific key within that secret

**Requirements:**
- The `hvac` Python library must be installed: `pip install "mxcp[vault]"` or `pip install hvac`
- Vault must be configured with `enabled: true`
- The Vault token must be available in the specified environment variable (default: `VAULT_TOKEN`)

**Supported Secret Engines:**
- KV Secrets Engine v2 (default)
- KV Secrets Engine v1 (fallback)

## Repository Configuration

The repository configuration file (`mxcp-site.yml`) defines project-specific settings.

### Basic Configuration
```yaml
mxcp: "1.0.0"  # Schema version
project: "my_project"  # Must match a project in ~/.mxcp/config.yml
profile: "dev"  # Profile to use
```

### Secrets
```yaml
secrets:
  - "db_credentials"  # List of secret names used by this repo
  - "api_key"
```

### Extensions
```yaml
extensions:
  - "httpfs"  # Core extension
  - "parquet"  # Core extension
  - name: "h3"  # Community extension
    repo: "community"
  - name: "uc_catalog"  # Nightly extension
    repo: "core_nightly"
```

### dbt Integration
```yaml
dbt:
  enabled: true
  model_paths: ["models"]  # Paths to dbt model directories
```

> **Note:** While MXCP doesn't provide built-in caching, you can implement caching strategies using:
> - dbt materializations (tables, incremental models)
> - DuckDB persistent tables
> - External caching layers

### Profile-Specific Settings
```yaml
profiles:
  dev:
    duckdb:
      path: "db-dev.duckdb"
      readonly: false
    drift:
      path: "drift-dev.json"
  prod:
    duckdb:
      path: "db-prod.duckdb"
      readonly: true
    drift:
      path: "drift-prod.json"
```

#### Drift Detection Configuration

The `drift` section configures drift detection for each profile:

```yaml
profiles:
  default:
    drift:
      path: "drift-default.json"  # Path to drift snapshot file
```

- **path**: Path to the drift snapshot file (relative to project root)
  - Used as the default baseline for `mxcp drift-check`
  - Created by `mxcp drift-snapshot`
  - Should be unique per profile to avoid conflicts

For more details on drift detection, see the [Drift Detection Guide](../features/drift-detection.md).

### SQL Tools
```yaml
sql_tools:
  enabled: true  # Enable built-in SQL querying tools
```

## Endpoint Definitions

Endpoints are defined in YAML files and can be of three types: tools, resources, or prompts.

### Tool Definition
```yaml
mxcp: "1.0.0"
tool:
  name: "my_tool"
  description: "A tool that does something"
  tags: ["tag1", "tag2"]
  annotations:
    title: "My Tool"
    readOnlyHint: true
    destructiveHint: false
    idempotentHint: true
    openWorldHint: false
  parameters:
    - name: "param1"
      type: "string"
      description: "First parameter"
      examples: ["example1"]
    - name: "param2"
      type: "number"
      description: "Second parameter"
      minimum: 0
      maximum: 100
  return:
    type: "object"
    properties:
      result:
        type: "string"
        description: "The result"
  language: "sql"
  source:
    file: "my_tool.sql"  # Or use code: "SELECT ..."
  enabled: true
  tests:
    - name: "basic_test"
      description: "Tests basic functionality"
      arguments:
        - key: "param1"
          value: "test"
        - key: "param2"
          value: 42
      result: "expected result"
  policies:  # Optional: Define access control policies
    input:
      - condition: "user.role in ['admin', 'user']"
        action: deny
        reason: "Only admins and users can access this tool"
    output:
      - condition: "user.role != 'admin'"
        action: filter_fields
        fields: ["sensitive_data"]
```

### Resource Definition
```yaml
mxcp: "1.0.0"
resource:
  uri: "my://resource/{id}"
  description: "A resource that provides data"
  tags: ["tag1", "tag2"]
  mime_type: "application/json"
  parameters:
    - name: "id"
      type: "string"
      description: "Resource ID"
  return:
    type: "object"
    properties:
      data:
        type: "array"
        items:
          type: "string"
  language: "sql"
  source:
    file: "my_resource.sql"
  enabled: true
  policies:  # Optional: Define access control policies
    input:
      - condition: "!('resource.read' in user.permissions)"
        action: deny
        reason: "Missing resource.read permission"
```

### Prompt Definition
```yaml
mxcp: "1.0.0"
prompt:
  name: "my_prompt"
  description: "A prompt template"
  tags: ["tag1", "tag2"]
  parameters:
    - name: "name"
      type: "string"
      description: "Name to use in prompt"
  messages:
    - role: "system"
      type: "text"
      prompt: "You are a helpful assistant."
    - role: "user"
      type: "text"
      prompt: "Hello, {{ name }}!"
  policies:  # Optional: Define access control policies
    input:
      - condition: "user.role == 'guest'"
        action: deny
        reason: "Guests cannot use AI prompts"
```

### Policy Enforcement

MXCP supports policy-based access control for endpoints. Policies can control who can access endpoints and what data they can see.

**Key features:**
- Input policies: Control access before execution
- Output policies: Filter or mask sensitive data
- CEL expressions: Flexible condition evaluation
- User context: Role-based and permission-based access

For detailed information on policy configuration and examples, see the [Policy Enforcement Guide](../features/policies.md).

## SQL Source Files

SQL can be defined either inline in the YAML or in separate files:

### Inline SQL
```yaml
source:
  code: |
    SELECT *
    FROM my_table
    WHERE id = :id
```

### External SQL File
```yaml
source:
  file: "queries/my_query.sql"
```

## Type System

MXCP uses a comprehensive type system for input validation and output conversion. See the [Type System](../reference/type-system.md) documentation for details.

## Jinja Templates in Prompts

Prompts support Jinja2 templating syntax:

```yaml
prompt: |
  Hello, {{ name }}!
  {% if role == "admin" %}
    You have admin privileges.
  {% else %}
    You have user privileges.
  {% endif %}
  
  {% for item in items %}
    - {{ item }}
  {% endfor %}
```

## Environment Variables

MXCP can be configured using environment variables:

- `MXCP_CONFIG`: Path to user config file (default: `~/.mxcp/config.yml`)
- `MXCP_DISABLE_ANALYTICS`: Disable analytics (set to "1", "true", or "yes")
- `MXCP_DEBUG`: Enable debug logging
- `MXCP_PROFILE`: Set default profile
- `MXCP_READONLY`: Enable read-only mode

## Model Configuration (for Evals)

MXCP supports configuring LLM models for evaluation tests. This configuration is used by the `mxcp evals` command to test how AI models interact with your endpoints.

### User Config Model Settings

Add model configuration to your user config file (`~/.mxcp/config.yml`):

```yaml
models:
  default: "claude-3-haiku"  # Default model to use for evals
  models:
    claude-3-opus:
      type: "claude"
      api_key: "${ANTHROPIC_API_KEY}"  # Environment variable containing API key
      timeout: 60  # Request timeout in seconds
      max_retries: 3  # Number of retries on failure
    
    claude-3-sonnet:
      type: "claude"
      api_key: "${ANTHROPIC_API_KEY}"
      timeout: 30
    
    claude-3-haiku:
      type: "claude"
      api_key: "${ANTHROPIC_API_KEY}"
      timeout: 20
    
    gpt-4-turbo:
      type: "openai"
      api_key: "${OPENAI_API_KEY}"
      base_url: "https://api.openai.com/v1"  # Optional custom endpoint
      timeout: 45
    
    gpt-3.5-turbo:
      type: "openai"
      api_key: "${OPENAI_API_KEY}"
      timeout: 20
```

### Model Configuration Options

- **default**: The model to use when not specified in eval suite or CLI
- **models**: Dictionary of model configurations
  - **type**: Either "claude" or "openai"
  - ****: Environment variable containing the API key (recommended)
  - **api_key**: API key (you can use environment variables references)
  - **base_url**: Custom API endpoint (optional, for OpenAI-compatible services)
  - **timeout**: Request timeout in seconds
  - **max_retries**: Number of retries on failure

For more information on using evals, see the [LLM Evaluation section](quality.md#llm-evaluation-evals) in the Quality & Testing Guide.

## Best Practices

1. **Secrets Management**
   - Never commit secrets to version control
   - Use environment variables or Vault for sensitive data
   - Keep secrets in `~/.mxcp/config.yml`

2. **Configuration Organization**
   - Use profiles for different environments
   - Keep SQL in separate files for better version control
   - Use meaningful names for tools and resources

3. **Type Safety**
   - Always define parameter types
   - Use format annotations for strings
   - Provide examples for better documentation

4. **Quality Assurance**
   - **Validate**: Run `mxcp validate` to ensure all endpoints are structurally correct
   - **Test**: Write comprehensive tests for all endpoints and run `mxcp test` regularly
   - **Lint**: Use `mxcp lint` to improve metadata for better LLM understanding
   - **Evals**: Create eval suites to test LLM interactions with `mxcp evals`
   - Include these checks in your CI/CD pipeline

5. **Testing Best Practices**
   - Write tests for all endpoints in the YAML definition
   - Test edge cases and error conditions
   - Use realistic test data
   - Test with different user contexts for policy-protected endpoints
   - Write eval tests to ensure LLMs use your tools safely

6. **Documentation**
   - Add clear descriptions to all endpoints, parameters, and return types
   - Use tags for categorization
   - Include meaningful examples in parameter definitions
   - Document behavioral hints (readOnlyHint, destructiveHint, etc.)
   - Run `mxcp lint` to identify missing documentation

7. **Development Workflow**
   ```bash
   # During development
   mxcp validate              # Check structure
   mxcp test                  # Run tests
   mxcp lint                  # Improve metadata
   
   # Before deployment
   mxcp drift-snapshot        # Create baseline
   mxcp evals                 # Test LLM behavior
   
   # In production
   mxcp drift-check          # Monitor changes
   ``` 
