---
title: "CLI Reference"
description: "Complete command-line interface reference for MXCP. All commands, options, and usage examples."
sidebar:
  order: 2
---

> **Related Topics:** [Quickstart](/getting-started/quickstart) (first commands) | [Common Tasks](common-tasks) (quick how-to) | [Quality](/quality/) (validation, testing, linting)

Complete reference for all MXCP command-line interface commands.

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
└── drift/               # Drift detection snapshots
    └── snapshot.json
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

## Commands

### mxcp init

Initialize a new MXCP project.

```bash
mxcp init [FOLDER] [OPTIONS]
```

**Arguments:**
- `FOLDER`: Target directory (default: current directory)

**Options:**
- `--project`: Project name (defaults to folder name)
- `--profile`: Profile name (defaults to 'default')
- `--bootstrap`: Create example hello world endpoint

**Examples:**
```bash
mxcp init                     # Initialize in current directory
mxcp init my-project          # Initialize in new directory
mxcp init --bootstrap         # Include example endpoint
mxcp init --project=analytics # Custom project name
```

### mxcp serve

Start the MCP server.

```bash
mxcp serve [OPTIONS]
```

**Options:**
- `--transport`: Protocol (streamable-http, sse, stdio)
- `--port`: Port for HTTP transport
- `--sql-tools`: Enable/disable SQL tools (true/false)
- `--stateless`: Enable stateless HTTP mode
- `--readonly`: Open database in read-only mode

**Examples:**
```bash
mxcp serve                              # Default transport
mxcp serve --transport stdio            # For Claude Desktop
mxcp serve --transport streamable-http  # HTTP API
mxcp serve --port 9000                  # Custom port
mxcp serve --sql-tools true             # Enable SQL tools
mxcp serve --stateless                  # Stateless mode (HTTP)
```

### mxcp run

Execute an endpoint.

```bash
mxcp run ENDPOINT_TYPE NAME [OPTIONS]
```

**Arguments:**
- `ENDPOINT_TYPE`: tool, resource, or prompt
- `NAME`: Endpoint name

**Options:**
- `--param`, `-p`: Parameter (name=value or name=@file.json)
- `--skip-output-validation`: Skip return type validation

**Examples:**
```bash
mxcp run tool get_user --param user_id=123
mxcp run tool search --param filters=@query.json
mxcp run resource users://alice
mxcp run prompt analyze --param data="sample"
```

### mxcp query

Execute SQL directly.

```bash
mxcp query [SQL] [OPTIONS]
```

**Arguments:**
- `SQL`: SQL query (optional if --file provided)

**Options:**
- `--file`: Path to SQL file
- `--param`, `-p`: Parameter (name=value or name=@file.json)

**Examples:**
```bash
mxcp query "SELECT * FROM users"
mxcp query "SELECT * FROM users WHERE age > $age" --param age=18
mxcp query --file reports/monthly.sql
mxcp query --file query.sql --param start=@dates.json
```

### mxcp validate

Validate endpoint definitions.

```bash
mxcp validate [ENDPOINT] [OPTIONS]
```

**Arguments:**
- `ENDPOINT`: Specific endpoint to validate (optional)

**Examples:**
```bash
mxcp validate                  # Validate all
mxcp validate get_user         # Validate specific endpoint
mxcp validate --json-output    # JSON output
```

### mxcp test

Run endpoint tests.

```bash
mxcp test [ENDPOINT_TYPE] [NAME] [OPTIONS]
```

**Arguments:**
- `ENDPOINT_TYPE`: tool, resource, or prompt (optional)
- `NAME`: Endpoint name (optional)

**Options:**
- `--user-context`, `-u`: User context JSON or @file.json

**Examples:**
```bash
mxcp test                                    # Run all tests
mxcp test tool get_user                      # Test specific endpoint
mxcp test --user-context '{"role":"admin"}'  # Test with user context
mxcp test --user-context @admin.json         # Context from file
mxcp test --debug                            # Verbose output
```

### mxcp lint

Check metadata quality.

```bash
mxcp lint [OPTIONS]
```

**Options:**
- `--severity`: Minimum level (all, warning, info)

**Examples:**
```bash
mxcp lint                      # Check all endpoints
mxcp lint --severity warning   # Only warnings
mxcp lint --json-output        # JSON output
```

**Checks Performed:**
- Missing descriptions
- Missing test cases
- Missing parameter examples
- Missing type descriptions
- Missing tags
- Missing behavioral annotations

### mxcp evals

Run LLM evaluations.

```bash
mxcp evals [SUITE_NAME] [OPTIONS]
```

**Arguments:**
- `SUITE_NAME`: Specific eval suite (optional)

**Options:**
- `--user-context`, `-u`: User context JSON or @file.json
- `--model`, `-m`: Override model for evaluation

**Examples:**
```bash
mxcp evals                           # Run all evals
mxcp evals customer_service          # Run specific suite
mxcp evals --model gpt-4-turbo       # Use specific model
mxcp evals --user-context @user.json # With user context
```

### mxcp list

List available endpoints.

```bash
mxcp list [OPTIONS]
```

**Examples:**
```bash
mxcp list                 # List all endpoints
mxcp list --json-output   # JSON format
mxcp list --profile prod  # From specific profile
```

### mxcp drift-snapshot

Create drift detection baseline.

```bash
mxcp drift-snapshot [OPTIONS]
```

**Options:**
- `--force`: Overwrite existing snapshot
- `--dry-run`: Show what would be done

**Examples:**
```bash
mxcp drift-snapshot                # Create snapshot
mxcp drift-snapshot --force        # Overwrite existing
mxcp drift-snapshot --dry-run      # Preview only
mxcp drift-snapshot --profile prod # From specific profile
```

**Captures:**
- Database schema (tables, columns)
- Endpoint definitions
- Validation results
- Test results

### mxcp drift-check

Check for drift from baseline.

```bash
mxcp drift-check [OPTIONS]
```

**Options:**
- `--baseline`: Path to baseline snapshot file

**Examples:**
```bash
mxcp drift-check                            # Check default baseline
mxcp drift-check --baseline prod-snapshot   # Specific baseline
mxcp drift-check --json-output              # JSON output
```

**Exit Codes:**
- `0`: No drift detected
- `1`: Drift detected

### mxcp log

Query audit logs.

```bash
mxcp log [OPTIONS]
```

**Options:**
- `--tool`: Filter by tool name
- `--resource`: Filter by resource URI
- `--prompt`: Filter by prompt name
- `--type`: Filter by type (tool, resource, prompt)
- `--policy`: Filter by decision (allow, deny, warn)
- `--status`: Filter by status (success, error)
- `--since`: Time range (10m, 2h, 1d)
- `--limit`: Maximum results (default: 100)
- `--export-csv`: Export to CSV file
- `--export-duckdb`: Export to DuckDB file
- `--json`: JSON output

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

**Time Formats:**
- `10s` - 10 seconds
- `5m` - 5 minutes
- `2h` - 2 hours
- `1d` - 1 day

### mxcp log-cleanup

Apply audit retention policies.

```bash
mxcp log-cleanup [OPTIONS]
```

**Options:**
- `--dry-run`: Show what would be deleted

**Examples:**
```bash
mxcp log-cleanup                # Apply retention
mxcp log-cleanup --dry-run      # Preview only
mxcp log-cleanup --profile prod # Specific profile
```

### mxcp dbt-config

Generate dbt configuration files.

```bash
mxcp dbt-config [OPTIONS]
```

**Options:**
- `--dry-run`: Show what would be written
- `--force`: Overwrite existing files
- `--embed-secrets`: Embed secrets in profiles.yml

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

**Examples:**
```bash
mxcp dbt run                      # Run all models
mxcp dbt run --select my_model    # Specific model
mxcp dbt test                     # Run tests
mxcp dbt docs generate            # Generate docs
mxcp dbt docs serve               # Serve docs
```

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

- [SQL Reference](sql) - SQL capabilities
- [Python Reference](python) - Runtime API
- [Plugin Reference](plugins) - Plugin development
