---
title: "CLI Reference"
description: "Complete command-line interface reference for MXCP. All commands, options, and usage examples."
sidebar:
  order: 2
---

> **Related Topics:** [Quickstart](/getting-started/quickstart) (first commands) | [Common Tasks](/reference/common-tasks) (quick how-to) | [Quality](/quality/) (validation, testing, linting)

Complete reference for all MXCP command-line interface commands.

## Quick Reference

| Command | Description | Category |
|---------|-------------|----------|
| [`mxcp init`](#mxcp-init) | Initialize a new MXCP project | Development |
| [`mxcp serve`](#mxcp-serve) | Start the MCP server | Development |
| [`mxcp run`](#mxcp-run) | Execute an endpoint | Development |
| [`mxcp query`](#mxcp-query) | Execute SQL directly | Development |
| [`mxcp validate`](#mxcp-validate) | Validate endpoint definitions | Quality |
| [`mxcp test`](#mxcp-test) | Run endpoint tests | Quality |
| [`mxcp lint`](#mxcp-lint) | Check metadata quality | Quality |
| [`mxcp evals`](#mxcp-evals) | Run LLM evaluations | Quality |
| [`mxcp list`](#mxcp-list) | List available endpoints | Operations |
| [`mxcp drift-snapshot`](#mxcp-drift-snapshot) | Create drift detection baseline | Operations |
| [`mxcp drift-check`](#mxcp-drift-check) | Check for drift from baseline | Operations |
| [`mxcp log`](#mxcp-log) | Query audit logs | Operations |
| [`mxcp log-cleanup`](#mxcp-log-cleanup) | Apply audit retention policies | Operations |
| [`mxcp dbt-config`](#mxcp-dbt-config) | Generate dbt configuration files | dbt Integration |
| [`mxcp dbt`](#mxcp-dbt) | Wrapper for dbt CLI with secret injection | dbt Integration |

## Project Structure

MXCP expects a specific directory structure:

```
my-project/
├── mxcp-site.yml        # Project configuration (required)
├── tools/               # Tool endpoint definitions
│   ├── get_user.yml
│   └── search.yml
├── resources/           # Resource endpoint definitions
│   └── user-profile.yml
├── prompts/             # Prompt endpoint definitions
│   └── analyze.yml
├── sql/                 # SQL source files
│   ├── queries/
│   └── migrations/
├── python/              # Python source files
│   └── handlers.py
├── plugins/             # Custom plugins
│   └── my_plugin/
├── evals/               # LLM evaluation suites
│   └── safety.evals.yml
├── drift/               # Drift detection snapshots
│   └── snapshot.json
├── data/                # DuckDB database files
├── audit/               # Audit logs (when enabled)
├── models/              # dbt models (if using dbt)
└── target/              # dbt target directory (if using dbt)
```

### Directory Requirements

| Directory | Purpose | Auto-discovered |
|-----------|---------|-----------------|
| `tools/` | Tool endpoint YAML files | Yes |
| `resources/` | Resource endpoint YAML files | Yes |
| `prompts/` | Prompt endpoint YAML files | Yes |
| `sql/` | SQL source files (referenced by endpoints) | No |
| `python/` | Python source files (referenced by endpoints) | No |
| `plugins/` | Custom plugin modules | No |
| `evals/` | LLM evaluation suite files (`*.evals.yml`) | Yes |
| `data/` | DuckDB database files | No |
| `audit/` | Audit logs (when auditing enabled) | No |
| `models/` | dbt models (if using dbt integration) | No |
| `target/` | dbt target directory (if using dbt integration) | No |

### Key Rules

1. **mxcp-site.yml** must exist in the project root
2. **Endpoint files** must use `.yml` or `.yaml` extension
3. **Eval files** must use `.evals.yml` suffix
4. **SQL/Python files** are referenced via `source.file` in endpoints
5. **Plugins** are referenced by module name in `mxcp-site.yml`

## Common Options

Most commands support these options:

| Option | Description |
|--------|-------------|
| `--profile` | Override profile from mxcp-site.yml |
| `--json-output` | Output results in JSON format |
| `--debug` | Show detailed debug information |
| `--readonly` | Open database in read-only mode |

---

## Development Commands

### mxcp init

Initialize a new MXCP project.

```bash
mxcp init [FOLDER] [OPTIONS]
```

**Description:**

Creates a new MXCP repository by:
1. Creating a `mxcp-site.yml` file with project and profile configuration
2. Creating standard directory structure (tools/, resources/, prompts/, etc.)
3. Optionally creating example endpoint files with `--bootstrap`
4. Generating a `server_config.json` for Claude Desktop integration

**Arguments:**
- `FOLDER`: Target directory (default: current directory)

**Options:**
- `--project`: Project name (defaults to folder name)
- `--profile`: Profile name (defaults to 'default')
- `--bootstrap`: Create example hello world endpoint
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp init                     # Initialize in current directory
mxcp init my-project          # Initialize in new directory
mxcp init --bootstrap         # Include example endpoint
mxcp init --project=analytics # Custom project name
```

### mxcp serve

Start the MCP server to expose endpoints via HTTP or stdio.

```bash
mxcp serve [OPTIONS]
```

**Description:**

Starts a server that exposes your MXCP endpoints as an MCP-compatible interface. By default, it uses the transport configuration from your user config. The server validates all endpoints at startup and **fails if any endpoints have errors** - use `--ignore-errors` to start anyway with invalid endpoints skipped.

**Options:**
- `--transport`: Protocol (`streamable-http`, `sse`, `stdio`)
- `--port`: Port for HTTP transport
- `--sql-tools`: Enable/disable SQL tools (`true`/`false`)
- `--stateless`: Enable stateless HTTP mode (for serverless deployments)
- `--readonly`: Open database in read-only mode
- `--ignore-errors`: Start server even if some endpoints have validation errors
- `--json-output`: Output startup errors in JSON format (useful for CI/CD)
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp serve                              # Default transport
mxcp serve --transport stdio            # For Claude Desktop
mxcp serve --transport streamable-http  # HTTP API
mxcp serve --port 9000                  # Custom port
mxcp serve --sql-tools true             # Enable SQL tools
mxcp serve --stateless                  # Stateless mode (HTTP)
mxcp serve --ignore-errors              # Start even if endpoints invalid
mxcp serve --json-output                # JSON format for CI/CD
```

### mxcp run

Execute an endpoint (tool, resource, or prompt).

```bash
mxcp run ENDPOINT_TYPE NAME [OPTIONS]
```

**Description:**

Executes a single endpoint with the specified parameters. Supports both simple values and complex JSON values from files. User context can be provided for testing policy-protected endpoints.

**Arguments:**
- `ENDPOINT_TYPE`: `tool`, `resource`, or `prompt`
- `NAME`: Endpoint name

**Options:**
- `--param`, `-p`: Parameter (`name=value` or `name=@file.json`)
- `--user-context`, `-u`: User context JSON or `@file.json`
- `--request-headers`: Request headers JSON or `@file.json`
- `--skip-output-validation`: Skip return type validation
- `--readonly`: Open database in read-only mode
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp run tool get_user --param user_id=123
mxcp run tool search --param query=test --param limit=10
mxcp run resource "users://{id}" --param id=alice
mxcp run prompt analyze --param data="sample"
mxcp run tool my_tool --user-context '{"role": "admin"}'
mxcp run tool my_tool --request-headers '{"Authorization": "Bearer token"}'
mxcp run tool my_tool --param data=@input.json
```

**Note:** For resources, use the full URI template (e.g., `users://{id}`) and provide parameters with `--param`.

### mxcp query

Execute SQL directly against the database.

```bash
mxcp query [SQL] [OPTIONS]
```

**Description:**

Executes a SQL query directly against the database. The query can be provided as an argument or from a file. Parameters can be provided for parameterized queries.

**Arguments:**
- `SQL`: SQL query (optional if `--file` provided)

**Options:**
- `--file`: Path to SQL file
- `--param`, `-p`: Parameter (`name=value` or `name=@file.json`)
- `--readonly`: Open database in read-only mode
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp query "SELECT * FROM users"
mxcp query "SELECT * FROM users WHERE age > \$age" --param age=18
mxcp query --file reports/monthly.sql
mxcp query --file query.sql --param start=@dates.json
```

---

## Quality Commands

> **See Also:** [Quality & Testing Guide](/quality/) for comprehensive testing best practices.

### mxcp validate

Validate endpoint definitions for correctness.

```bash
mxcp validate [ENDPOINT] [OPTIONS]
```

**Description:**

Validates the schema and configuration of endpoints, including YAML syntax, required fields, SQL syntax errors, and parameter/return type definitions. If no endpoint is specified, all endpoints are validated.

**Arguments:**
- `ENDPOINT`: Specific endpoint to validate (optional)

**Options:**
- `--readonly`: Open database in read-only mode
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp validate                        # Validate all
mxcp validate tools/get_user.yml     # Validate specific endpoint
mxcp validate --json-output          # JSON output
```

### mxcp test

Run endpoint tests.

```bash
mxcp test [ENDPOINT_TYPE] [NAME] [OPTIONS]
```

**Description:**

Executes test cases defined in endpoint configurations. If no endpoint type and name are provided, runs all tests. User context can be provided for testing policy-protected endpoints.

**Arguments:**
- `ENDPOINT_TYPE`: `tool`, `resource`, or `prompt` (optional)
- `NAME`: Endpoint name (optional)

**Options:**
- `--user-context`, `-u`: User context JSON or `@file.json`
- `--request-headers`: Request headers JSON or `@file.json`
- `--readonly`: Open database in read-only mode
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp test                                    # Run all tests
mxcp test tool get_user                      # Test specific endpoint
mxcp test --user-context '{"role":"admin"}'  # Test with user context
mxcp test --user-context @admin.json         # Context from file
mxcp test --request-headers '{"Authorization":"Bearer token"}'  # With headers
mxcp test --debug                            # Verbose output
```

**User Context in Tests:**

The `--user-context` flag allows you to test endpoints with policies that depend on user authentication. The command-line context overrides any user_context defined in test specifications.

You can also define user context directly in test specifications:

```yaml
tests:
  - name: Admin can see all fields
    user_context:
      role: admin
      permissions: ["employee:read:all"]
    arguments:
      - key: employee_id
        value: "123"
    result:
      id: "123"
      name: "John Doe"
      salary: 100000  # Admin can see salary
```

### mxcp lint

Check endpoints for metadata quality issues.

```bash
mxcp lint [OPTIONS]
```

**Description:**

Analyzes your endpoints and suggests improvements to make them more effective for LLM usage. Good metadata is crucial for LLM performance - it helps the model understand what each endpoint does, valid parameter values, expected output structures, and safety considerations.

**Checks Performed:**
- Missing descriptions on endpoints, parameters, and return types
- Missing test cases
- Missing parameter examples
- Missing type descriptions in nested structures
- Missing tags for categorization
- Missing behavioral annotations (readOnlyHint, idempotentHint, etc.)
- Missing default values on optional parameters

**Options:**
- `--severity`: Minimum level (`all`, `warning`, `info`)
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp lint                      # Check all endpoints
mxcp lint --severity warning   # Only warnings
mxcp lint --json-output        # JSON output
```

### mxcp evals

Run LLM evaluations.

```bash
mxcp evals [SUITE_NAME] [OPTIONS]
```

**Description:**

Executes evaluation tests that verify LLM behavior with your endpoints. Unlike regular tests that execute endpoints directly, evals:

1. Send prompts to an LLM
2. Verify the LLM calls appropriate tools
3. Check that responses contain expected information
4. Ensure safety by verifying destructive operations aren't called inappropriately

Eval files should have the suffix `-evals.yml` or `.evals.yml` and are automatically discovered.

**Arguments:**
- `SUITE_NAME`: Specific eval suite (optional)

**Options:**
- `--user-context`, `-u`: User context JSON or `@file.json`
- `--model`, `-m`: Override model for evaluation
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp evals                           # Run all evals
mxcp evals customer_service          # Run specific suite
mxcp evals --model gpt-4-turbo       # Use specific model
mxcp evals --user-context @user.json # With user context
```

---

## Operations Commands

### mxcp list

List available endpoints.

```bash
mxcp list [OPTIONS]
```

**Description:**

Discovers and lists all endpoints in the current repository, grouped by type (tools, resources, prompts). Shows both valid endpoints and any files with parsing errors.

**Options:**
- `--profile`: Profile name to use
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp list                 # List all endpoints
mxcp list --json-output   # JSON format
mxcp list --profile prod  # From specific profile
```

### mxcp drift-snapshot

Create a drift detection baseline.

```bash
mxcp drift-snapshot [OPTIONS]
```

**Description:**

Creates a snapshot of the current state of your MXCP repository for change detection. The snapshot is used to detect drift between different environments or over time.

**Captures:**
- Database schema (tables, columns)
- Endpoint definitions (tools, resources, prompts)
- Validation results
- Test results

> **See Also:** [Drift Detection](/operations/drift-detection) for comprehensive guide.

**Options:**
- `--force`: Overwrite existing snapshot
- `--dry-run`: Show what would be done
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp drift-snapshot                # Create snapshot
mxcp drift-snapshot --force        # Overwrite existing
mxcp drift-snapshot --dry-run      # Preview only
mxcp drift-snapshot --profile prod # From specific profile
```

### mxcp drift-check

Check for drift from baseline.

```bash
mxcp drift-check [OPTIONS]
```

**Description:**

Compares the current state of your database and endpoints against a previously generated baseline snapshot to detect any changes. Reports added, removed, or modified tables, columns, and endpoints.

**Options:**
- `--baseline`: Path to baseline snapshot file
- `--readonly`: Open database in read-only mode
- `--json-output`: Output in JSON format
- `--debug`: Show detailed change information

**Exit Codes:**
- `0`: No drift detected
- `1`: Drift detected

**Examples:**
```bash
mxcp drift-check                            # Check default baseline
mxcp drift-check --baseline prod-snapshot   # Specific baseline
mxcp drift-check --json-output              # JSON output
```

### mxcp log

Query audit logs.

```bash
mxcp log [OPTIONS]
```

**Description:**

Queries the audit logs to show execution history for tools, resources, and prompts. Audit logging must be enabled in your profile configuration. Logs are stored in JSONL format for concurrent access while the server is running.

> **See Also:** [Auditing Guide](/security/auditing) for comprehensive guide.

**Options:**
- `--tool`: Filter by tool name
- `--resource`: Filter by resource URI
- `--prompt`: Filter by prompt name
- `--type`: Filter by type (`tool`, `resource`, `prompt`)
- `--policy`: Filter by decision (`allow`, `deny`, `warn`, `n/a`)
- `--status`: Filter by status (`success`, `error`)
- `--since`: Time range (`10m`, `2h`, `1d`)
- `--limit`: Maximum results (default: 100)
- `--export-csv`: Export to CSV file
- `--export-duckdb`: Export to DuckDB file
- `--json`: JSON output
- `--debug`: Show detailed debug information

**Time Formats:**
- `10s` - 10 seconds
- `5m` - 5 minutes
- `2h` - 2 hours
- `1d` - 1 day

**Examples:**
```bash
mxcp log                              # Recent logs
mxcp log --tool get_user              # Filter by tool
mxcp log --policy deny                # Blocked executions
mxcp log --since 1h                   # Last hour
mxcp log --since 1d --status error    # Errors today
mxcp log --export-csv audit.csv       # Export to CSV
mxcp log --export-duckdb audit.duckdb # Export to DuckDB
```

### mxcp log-cleanup

Apply audit retention policies.

```bash
mxcp log-cleanup [OPTIONS]
```

**Description:**

Deletes audit records older than their schema's retention policy. Each audit schema can define a `retention_days` value specifying how long records should be kept. This command is designed to be run periodically via cron or systemd timer.

**Options:**
- `--dry-run`: Show what would be deleted
- `--json`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp log-cleanup                # Apply retention
mxcp log-cleanup --dry-run      # Preview only
mxcp log-cleanup --profile prod # Specific profile

# Schedule with cron (daily at 2 AM)
# 0 2 * * * /usr/bin/mxcp log-cleanup

# Systemd timer example - see mxcp-log-cleanup.service
```

---

## dbt Integration Commands

> **See Also:** [dbt Integration](/integrations/dbt) for comprehensive guide.

### mxcp dbt-config

Generate dbt configuration files.

```bash
mxcp dbt-config [OPTIONS]
```

**Description:**

Generates or patches dbt side-car files (`dbt_project.yml` + `profiles.yml`). Default mode writes `env_var()` templates so secrets stay out of YAML. Use `--embed-secrets` to flatten secrets directly into `profiles.yml` (not recommended for production).

**Options:**
- `--profile`: Override profile from mxcp-site.yml
- `--dry-run`: Show what would be written
- `--force`: Overwrite existing files
- `--embed-secrets`: Embed secrets in profiles.yml
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp dbt-config                         # Generate config
mxcp dbt-config --dry-run               # Preview only
mxcp dbt-config --embed-secrets --force # With secrets
```

### mxcp dbt

Wrapper for dbt CLI with secret injection.

```bash
mxcp dbt [DBT_COMMAND] [OPTIONS]
```

**Description:**

Injects secrets as environment variables then delegates to the real dbt CLI. This allows dbt to access secrets defined in your MXCP configuration without exposing them in `profiles.yml`.

**Options:**
- `--profile`: Override profile from mxcp-site.yml
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp dbt run                      # Run all models
mxcp dbt run --select my_model    # Specific model
mxcp dbt test                     # Run tests
mxcp dbt docs generate            # Generate docs
mxcp dbt docs serve               # Serve docs
mxcp dbt run --profile prod       # Use prod profile
```

---

## Output Formats

### JSON Output

When using `--json-output`:

```json
{
  "status": "ok",
  "result": {},
  "error": null
}
```

With errors:

```json
{
  "status": "error",
  "result": null,
  "error": "Error message",
  "traceback": "..."
}
```

### Human-Readable Output

Default output uses formatted text with:
- Success messages to stdout
- Error messages to stderr
- Tables and lists formatted for readability

## Environment Variables

### Core Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MXCP_DEBUG` | Enable debug logging | false |
| `MXCP_PROFILE` | Default profile | - |
| `MXCP_READONLY` | Read-only mode | false |
| `MXCP_DUCKDB_PATH` | Override DuckDB path | - |
| `MXCP_CONFIG_PATH` | User config path | ~/.mxcp/config.yml |

### Admin Socket

| Variable | Description | Default |
|----------|-------------|---------|
| `MXCP_ADMIN_ENABLED` | Enable admin socket | true |
| `MXCP_ADMIN_SOCKET` | Admin socket path | - |

### Telemetry (OpenTelemetry)

| Variable | Description |
|----------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint |
| `OTEL_SERVICE_NAME` | Service name (default: mxcp) |
| `OTEL_RESOURCE_ATTRIBUTES` | Resource attributes |
| `OTEL_EXPORTER_OTLP_HEADERS` | OTLP headers |
| `MXCP_TELEMETRY_ENABLED` | Enable/disable telemetry |
| `MXCP_TELEMETRY_TRACING_CONSOLE` | Console trace export |
| `MXCP_TELEMETRY_METRICS_INTERVAL` | Metrics interval (seconds) |

## Error Handling

Commands handle errors consistently:

1. Invalid arguments show usage information
2. Runtime errors show descriptive messages
3. `--debug` includes full tracebacks
4. `--json-output` returns errors in JSON format

## Next Steps

- [SQL Reference](/reference/sql) - SQL capabilities
- [Python Reference](/reference/python) - Runtime API
- [Plugin Reference](/reference/plugins) - Plugin development
