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
    default: "dev"
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

### Projects Configuration
```yaml
projects:
  my_project:  # Project name
    default: "dev"  # Default profile
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
    default: "dev"
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
base_url: "demo"  # Optional base URL for serving endpoints
enabled: true  # Whether this repo is enabled
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
  models: "models"  # Path to dbt models directory
  manifest_path: "target/manifest.json"  # Path to dbt manifest
```

> **Note:** While MXCP doesn't provide built-in caching, you can implement caching strategies using:
> - dbt materializations (tables, incremental models)
> - DuckDB persistent tables
> - External caching layers

### Python Configuration
```yaml
python:
  path: "bootstrap.py"  # Path to Python bootstrap file
```

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

For more details on drift detection, see the [Drift Detection Guide](drift-detection.md).

### Cloud Settings
```yaml
cloud:
  github:
    prefix_with_branch_name: true
    skip_prefix_for_branches:
      - "main"
      - "master"
```

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
```

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

MXCP uses a comprehensive type system for input validation and output conversion. See the [Type System](type-system.md) documentation for details.

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

4. **Testing**
   - Write tests for all endpoints
   - Test edge cases and error conditions
   - Use realistic test data

5. **Documentation**
   - Add descriptions to all parameters
   - Use tags for categorization
   - Include examples in parameter definitions 