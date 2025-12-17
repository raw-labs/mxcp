---
title: "Common Tasks"
description: "Quick reference for common MXCP tasks. How to add authentication, filter data, write tests, configure production, and more."
sidebar:
  order: 2
---

Quick answers to "How do I...?" questions. Each task links to full documentation.

## Getting Started

### How do I create a new project?

```bash
mkdir my-project && cd my-project
mxcp init --bootstrap  # Creates example endpoint
```

[Full guide →](/getting-started/quickstart)

### How do I run my first tool?

```bash
mxcp run tool hello_world --param name=Alice
```

[Hello World tutorial →](/tutorials/hello-world)

### How do I connect to Claude Desktop?

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "my-project": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/path/to/my-project"
    }
  }
}
```

[Full guide →](/integrations/claude-desktop)

## Creating Endpoints

### How do I create a SQL tool?

```yaml
# tools/my-tool.yml
mxcp: 1
tool:
  name: my_tool
  description: What this tool does
  parameters:
    - name: param_name
      type: string
      description: Parameter description
  return:
    type: object
  source:
    file: ../sql/my-tool.sql
```

[SQL endpoints tutorial →](/tutorials/sql-endpoints)

### How do I create a Python tool?

```yaml
# tools/my-tool.yml
mxcp: 1
tool:
  name: my_tool
  description: What this tool does
  language: python
  parameters:
    - name: param_name
      type: string
      description: Parameter description
  return:
    type: object
  source:
    file: ../python/my_module.py
```

```python
# python/my_module.py
from mxcp.runtime import db

def my_tool(param_name: str) -> dict:
    results = db.execute("SELECT * FROM data WHERE name = $name", {"name": param_name})
    return {"data": results}
```

[Python endpoints tutorial →](/tutorials/python-endpoints)

### How do I create a resource?

```yaml
# resources/user.yml
mxcp: 1
resource:
  uri: users://{id}
  description: Get user by ID
  parameters:
    - name: id
      type: integer
      description: User ID
  return:
    type: object
  source:
    code: "SELECT * FROM users WHERE id = $id"
```

[Endpoints concept →](/concepts/endpoints)

## Security

### How do I add authentication?

Add to `~/.mxcp/config.yml`:

```yaml
projects:
  my-project:
    profiles:
      default:
        auth:
          provider: github
          github:
            client_id: your_client_id
            client_secret: your_client_secret
```

[Authentication guide →](/security/authentication)

### How do I restrict access to a tool?

Add input policy:

```yaml
policies:
  input:
    - condition: "user.role != 'admin'"
      action: deny
      reason: "Admin access required"
```

[Policies guide →](/security/policies)

### How do I filter sensitive data?

Add output policy:

```yaml
policies:
  output:
    - condition: "user.role != 'admin'"
      action: filter_fields
      fields: ["salary", "ssn"]
      reason: "Restricted to admins"
```

Or mark fields as sensitive:

```yaml
return:
  type: object
  properties:
    ssn:
      type: string
      sensitive: true
```

[Policies guide →](/security/policies)

### How do I enable audit logging?

Add to `mxcp-site.yml`:

```yaml
profiles:
  default:
    audit:
      enabled: true
      path: audit/logs.jsonl
```

Query logs:

```bash
mxcp log --since 1h
mxcp log --tool my_tool --status error
```

[Auditing guide →](/security/auditing)

## Testing & Quality

### How do I add tests to an endpoint?

Add tests section to your endpoint YAML:

```yaml
tests:
  - name: basic_test
    arguments:
      - key: param_name
        value: "test_value"
    result_contains:
      expected_field: "expected_value"
```

Run tests:

```bash
mxcp test
```

[Testing guide →](/quality/testing)

### How do I test with different user roles?

```bash
mxcp run tool my_tool \
  --param id=123 \
  --user-context '{"role": "admin", "permissions": ["read", "write"]}'
```

Or in YAML tests:

```yaml
tests:
  - name: admin_access
    user_context:
      role: admin
    arguments:
      - key: id
        value: 123
```

[Policies guide →](/security/policies)

### How do I validate my endpoints?

```bash
mxcp validate                        # All endpoints
mxcp validate tools/my_tool.yml      # Specific endpoint
mxcp validate --debug                # Detailed output
```

[Validation guide →](/quality/validation)

### How do I check for linting issues?

```bash
mxcp lint
```

[Linting guide →](/quality/linting)

## Configuration

### How do I use environment-specific settings?

Define profiles in `mxcp-site.yml`:

```yaml
profiles:
  development:
    duckdb:
      path: dev.db
    audit:
      enabled: false

  production:
    duckdb:
      path: /data/prod.db
    audit:
      enabled: true
```

Use profile:

```bash
mxcp serve --profile production
# or
export MXCP_PROFILE=production
```

[Configuration guide →](/operations/configuration)

### How do I use secrets?

Add to `~/.mxcp/config.yml`:

```yaml
projects:
  my-project:
    profiles:
      default:
        secrets:
          - name: api_key
            type: custom
            parameters:
              value: "secret-value"
```

Access in Python:

```python
from mxcp.runtime import config
secret = config.get_secret("api_key")
api_key = secret["value"] if secret else None
```

[Configuration guide →](/operations/configuration)

### How do I use Vault for secrets?

```yaml
# ~/.mxcp/config.yml
vault:
  enabled: true
  address: https://vault.example.com
  token_env: VAULT_TOKEN

projects:
  my-project:
    profiles:
      default:
        secrets:
          - name: db_password
            parameters:
              password: "vault://secret/database#password"
```

[Configuration guide →](/operations/configuration)

## Operations

### How do I deploy to production?

With Docker:

```dockerfile
FROM python:3.11-slim
RUN pip install mxcp
COPY . /app
WORKDIR /app
CMD ["mxcp", "serve", "--transport", "streamable-http", "--port", "8000"]
```

[Deployment guide →](/operations/deployment)

### How do I enable monitoring?

Set OpenTelemetry environment variables:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318
export OTEL_SERVICE_NAME=mxcp-prod
export MXCP_TELEMETRY_ENABLED=true
```

[Monitoring guide →](/operations/monitoring)

### How do I reload configuration without restart?

```bash
# Send SIGHUP
kill -HUP $(pgrep -f "mxcp serve")

# Or use admin socket
curl --unix-socket /run/mxcp/mxcp.sock -X POST http://localhost/reload
```

[Admin socket guide →](/operations/admin-socket)

### How do I check for drift?

```bash
# Create baseline
mxcp drift-snapshot

# Check for changes
mxcp drift-check
```

[Drift detection guide →](/operations/drift-detection)

## Database

### How do I access the database from Python?

```python
from mxcp.runtime import db

# Execute query
results = db.execute(
    "SELECT * FROM users WHERE id = $id",
    {"id": 123}
)

# results is a list of dicts
for row in results:
    print(row["name"])
```

[Python reference →](/reference/python)

### How do I use DuckDB extensions?

Add to `mxcp-site.yml`:

```yaml
extensions:
  - httpfs
  - parquet
  - name: h3
    repo: community
```

[DuckDB integration →](/integrations/duckdb)

### How do I integrate with dbt?

Enable in `mxcp-site.yml`:

```yaml
dbt:
  enabled: true
  model_paths: ["models"]
```

Run dbt through MXCP:

```bash
mxcp dbt run
```

[dbt integration →](/integrations/dbt)

## Troubleshooting

### Tool not found

```bash
mxcp list  # See available endpoints
```

Check that:
- File is in `tools/` directory
- `enabled: true` is set
- YAML is valid (`mxcp validate`)

### Validation errors

```bash
mxcp validate --debug
```

Check YAML indentation and required fields.

### Policy denials

```bash
mxcp run tool my_tool --user-context '{"role": "admin"}' --debug
```

Check policy conditions match user context.

### Python import errors

```bash
# Ensure virtual environment
source .venv/bin/activate

# Debug
mxcp run tool my_tool --debug
```

[Quickstart →](/getting-started/quickstart)
