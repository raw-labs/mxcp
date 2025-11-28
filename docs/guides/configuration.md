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

### Dynamic Value Interpolation

The user configuration file supports several methods for injecting values dynamically:

1. **Environment Variables** - Use `$\{ENV_VAR\}` syntax
2. **Vault Secrets** - Use `vault://path/to/secret#key` URLs
3. **File References** - Use `file://path/to/file` URLs

Example:
```yaml
mxcp: 1
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
              database: "${DB_NAME}"               # From environment variable
              username: "${DB_USER}"                # From environment variable
              password: "vault://secret/db#password" # From Vault
              ssl_cert: "file:///etc/ssl/db.crt"    # From file
```

If any referenced value cannot be resolved (missing environment variable, Vault secret, or file), MXCP will raise an error when loading the configuration.

### Schema Version
```yaml
mxcp: 1  # Always use this version
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
mxcp: 1
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

### 1Password Integration (Optional)

MXCP supports 1Password for secure secret management using service accounts. When enabled, you can use `op://` URLs in your configuration to retrieve secrets from 1Password.

```yaml
onepassword:
  enabled: true
  token_env: "OP_SERVICE_ACCOUNT_TOKEN"  # Environment variable containing the service account token
```

#### Using 1Password URLs

Once 1Password is configured, you can use `op://` URLs anywhere in your configuration where you would normally put sensitive values:

```yaml
mxcp: 1
onepassword:
  enabled: true
  token_env: "OP_SERVICE_ACCOUNT_TOKEN"
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
              username: "op://vault/database-creds/username"
              password: "op://vault/database-creds/password"
              totp: "op://vault/database-creds/totp?attribute=otp"
```

**1Password URL Format:** `op://vault/item/field[?attribute=otp]`

- `vault`: The name or ID of the vault in 1Password
- `item`: The name or ID of the item in 1Password
- `field`: The name or ID of the field within the item
- `?attribute=otp`: Optional parameter to retrieve TOTP/OTP value

**Requirements:**
- The `onepassword-sdk` Python library must be installed: `pip install "mxcp[onepassword]"` or `pip install onepassword-sdk`
- 1Password service account must be configured with appropriate vault access
- 1Password must be configured with `enabled: true`
- The service account token must be available in the specified environment variable (default: `OP_SERVICE_ACCOUNT_TOKEN`)

**Examples:**
- Basic field: `op://Private/Login Item/username`
- Password field: `op://Private/Login Item/password`
- TOTP/OTP: `op://Private/Login Item/totp?attribute=otp`
- Using vault ID: `op://hfnjvi6aymbsnfc2gshk5b6o5q/Login Item/password`
- Using item ID: `op://Private/j5hbqmr7nz3uqsw3j5qam2fgji/password`

### File References

MXCP supports reading configuration values from local files using `file://` URLs. This is useful for:
- Loading certificates or keys from files
- Reading API tokens from secure file locations
- Separating sensitive data from configuration files

**File URL Format:**
- Absolute paths: `file:///absolute/path/to/file`
- Relative paths: `file://relative/path/to/file` (relative to current working directory)

**Example:**
```yaml
mxcp: 1
projects:
  my_project:
    profiles:
      dev:
        secrets:
          - name: "ssl_certificates"
            type: "custom"
            parameters:
              cert: "file:///etc/ssl/certs/server.crt"
              key: "file:///etc/ssl/private/server.key"
          - name: "api_config"
            type: "api"
            parameters:
              api_key: "file://secrets/api_key.txt"
              endpoint: "https://api.example.com"
```

**Important Notes:**
- The file content is read when the configuration is loaded
- Whitespace (including newlines) is automatically stripped from the file content
- The file must exist and be readable when the configuration is loaded
- Use appropriate file permissions to protect sensitive files
- Relative paths are resolved from the current working directory, not the config file location

### Combining Interpolation Methods

You can combine environment variables, Vault URLs, 1Password URLs, and file references in the same configuration:

```yaml
mxcp: 1
vault:
  enabled: true
  address: "${VAULT_ADDR}"
  token_env: "VAULT_TOKEN"
onepassword:
  enabled: true
  token_env: "OP_SERVICE_ACCOUNT_TOKEN"
projects:
  my_project:
    profiles:
      dev:
        secrets:
          - name: "app_config"
            type: "custom"
            parameters:
              database_host: "${DB_HOST}"                       # Environment variable
              database_password: "vault://secret/db#password"   # Vault secret
              api_key: "op://Private/api-keys/production"       # 1Password secret
              totp: "op://Private/api-keys/totp?attribute=otp"  # 1Password TOTP
              ssl_cert: "file:///etc/ssl/app.crt"               # File reference
              ssl_key: "file://keys/app.key"                    # Relative file path
```

## Repository Configuration

The repository configuration file (`mxcp-site.yml`) defines project-specific settings.

### Basic Configuration
```yaml
mxcp: 1  # Schema version
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
  enabled: false  # Enable built-in SQL querying tools (disabled by default)
```

## Endpoint Definitions

Endpoints are defined in YAML files and can be of three types: tools, resources, or prompts.

### Tool Definition
```yaml
mxcp: 1
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
mxcp: 1
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
mxcp: 1
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
- `MXCP_DUCKDB_PATH`: Override the DuckDB file location (see below)
- `MXCP_ADMIN_ENABLED`: Enable local admin control socket (set to "1", "true", or "yes")
- `MXCP_ADMIN_SOCKET`: Path to admin socket (default: `/run/mxcp/mxcp.sock`)

### DuckDB Path Override

The `MXCP_DUCKDB_PATH` environment variable allows you to override the DuckDB database file location configured in `mxcp-site.yml`. This is useful for:

- Using a centralized database location across different projects
- Running tests with a temporary database
- Deploying to environments where the configured path isn't writable

**Example:**
```bash
# Override DuckDB location for all commands
export MXCP_DUCKDB_PATH="/tmp/test.duckdb"
mxcp run my_tool

# Or set it for a single command
MXCP_DUCKDB_PATH="/path/to/shared.db" mxcp serve
```

When `MXCP_DUCKDB_PATH` is set, it overrides the path specified in `profiles.<profile>.duckdb.path` for all profiles.

### Configuration Reload

For long-running MCP servers, you can reload external configuration values (secrets from vault://, file://, and environment variables) without restarting the service:

```bash
# Send SIGHUP signal to reload external values
kill -HUP <pid>
```

The reload process:
1. **SIGHUP handler waits synchronously** - up to 60 seconds for the reload to complete
2. **Only external references are refreshed** - the configuration file structure is NOT re-read
3. **Service remains available** - new requests wait while reload completes
4. **Automatic rollback on failure** - if new values cause errors, the server continues with old values

What gets refreshed:
- ✅ Vault secrets (vault://)
- ✅ File contents (file://)
- ✅ Environment variables ($\{VAR\})
- ✅ DuckDB connection (always recreated to pick up any database file changes)
- ✅ Python runtimes with updated configs

What does NOT change:
- ❌ Configuration file structure
- ❌ OAuth provider settings
- ❌ Server host/port settings
- ❌ Registered endpoints

This design ensures that only the values that are meant to be dynamic (secrets, tokens, etc.) are refreshed, while the service structure remains stable. This prevents accidental service disruption from configuration file changes.

**Note on DuckDB Reload**: The DuckDB connection is always recreated during a reload, regardless of whether configuration values have changed. This ensures that any external changes to the DuckDB database file (new tables, data updates, etc.) are visible after the reload.

## Model Configuration (for Evals)

MXCP supports configuring LLM models for evaluation tests. This configuration is used by the `mxcp evals` command to test how AI models interact with your endpoints.

### User Config Model Settings

Add model configuration to your user config file (`~/.mxcp/config.yml`):

```yaml
models:
  default: "claude-4-sonnet"  # Default model to use for evals
  models:
    claude-4-opus:
      type: "claude"
      api_key: "${ANTHROPIC_API_KEY}"  # Environment variable containing API key
      timeout: 60  # Request timeout in seconds
      max_retries: 3  # Number of retries on failure
    
    claude-4-sonnet:
      type: "claude"
      api_key: "${ANTHROPIC_API_KEY}"
      timeout: 30
    
    gpt-4o:
      type: "openai"
      api_key: "${OPENAI_API_KEY}"
      base_url: "https://api.openai.com/v1"  # Optional custom endpoint
      timeout: 45
    
    gpt-4.1:
      type: "openai"
      api_key: "${OPENAI_API_KEY}"
      timeout: 30
```

### Model Configuration Options

- **default**: The model to use when not specified in eval suite or CLI
- **models**: Dictionary of model configurations
  - **type**: Either "claude" or "openai"
  - **api_key**: API key (you can use environment variables references)
- **base_url**: Custom API endpoint (optional, for OpenAI-compatible services)
- **timeout**: Request timeout in seconds
- **max_retries**: Number of retries on failure
- **options**: Extra provider-specific options forwarded to the model (e.g. `thinking: false`)

Example with mixed providers and options:

```yaml
models:
  default: "gpt-4o"
  models:
    gpt-4o:
      type: "openai"
      api_key: "${OPENAI_API_KEY}"
      timeout: 45
      options:
        reasoning: "fast"
    claude-4-sonnet:
      type: "claude"
      api_key: "${ANTHROPIC_API_KEY}"
      timeout: 30
      options:
        thinking: false
```

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
