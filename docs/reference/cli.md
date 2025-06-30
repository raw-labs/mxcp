---
title: "CLI Reference"
description: "Complete command-line interface reference for MXCP. All commands, options, and usage examples for the mxcp CLI tool."
keywords:
  - mxcp cli
  - command line interface
  - cli commands
  - mxcp serve
  - mxcp run
  - mxcp validate
sidebar_position: 1
slug: /reference/cli
---

# MXCP CLI Reference

This document provides a comprehensive reference for all MXCP command-line interface (CLI) commands and their options.

## Directory Structure Requirements

MXCP enforces an organized directory structure to improve project maintainability and developer experience. All commands expect your project to follow this structure:

```
mxcp-project/
├── mxcp-site.yml       # Project configuration (required)
├── tools/              # MCP tool definitions (.yml files)
├── resources/          # MCP resource definitions (.yml files)  
├── prompts/            # MCP prompt definitions (.yml files)
├── evals/              # Evaluation definitions (.yml files)
├── python/             # Python endpoints and shared code
├── plugins/            # MXCP plugins for DuckDB
├── sql/                # SQL implementation files
├── drift/              # Schema drift detection snapshots
├── audit/              # Audit logs (when enabled)
├── models/             # dbt models (if using dbt)
└── target/             # dbt target directory (if using dbt)
```

**Key Rules:**
- **Tools** must be defined in `tools/*.yml` files
- **Resources** must be defined in `resources/*.yml` files
- **Prompts** must be defined in `prompts/*.yml` files
- **SQL implementations** should be in `sql/*.sql` files and referenced via relative paths
- Files in wrong directories are ignored by discovery commands

Use `mxcp init --bootstrap` to create a properly structured project.

## Common Options

Most commands support these common options:

- `--profile`: Override the profile name from mxcp-site.yml
- `--json-output`: Output results in JSON format
- `--debug`: Show detailed debug information
- `--readonly`: Open database connection in read-only mode

## Commands

### `mxcp init`

Initialize a new MXCP repository.

```bash
mxcp init [FOLDER] [OPTIONS]
```

**Arguments:**
- `FOLDER`: Target directory (default: current directory)

**Options:**
- `--project`: Project name (defaults to folder name)
- `--profile`: Profile name (defaults to 'default')
- `--bootstrap`: Create example hello world endpoint
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp init                    # Initialize in current directory
mxcp init my-project        # Initialize in my-project directory
mxcp init --project=test    # Initialize with specific project name
mxcp init --bootstrap       # Initialize with example endpoint
```

### `mxcp serve`

Start the MXCP MCP server to expose endpoints via HTTP or stdio.

```bash
mxcp serve [OPTIONS]
```

**Options:**
- `--profile`: Profile name to use
- `--transport`: Transport protocol to use (streamable-http, sse, or stdio) - defaults to user config setting
- `--port`: Port number for HTTP transport - defaults to user config setting
- `--debug`: Show detailed debug information
- `--sql-tools`: Enable or disable built-in SQL querying and schema exploration tools (true/false)
- `--readonly`: Open database connection in read-only mode
- `--stateless`: Enable stateless HTTP mode for Claude.ai and serverless deployments

**Examples:**
```bash
mxcp serve                   # Use transport settings from user config
mxcp serve --port 9000       # Override port from user config
mxcp serve --transport stdio # Override transport from user config
mxcp serve --profile dev     # Use the 'dev' profile configuration
mxcp serve --sql-tools true  # Enable built-in SQL querying tools
mxcp serve --sql-tools false # Disable built-in SQL querying tools
mxcp serve --readonly        # Open database connection in read-only mode
mxcp serve --stateless       # Enable stateless HTTP mode
```

### `mxcp run`

Run an endpoint (tool, resource, or prompt).

```bash
mxcp run ENDPOINT_TYPE NAME [OPTIONS]
```

**Arguments:**
- `ENDPOINT_TYPE`: Type of endpoint (tool, resource, or prompt)
- `NAME`: Name of the endpoint to run

**Options:**
- `--param`, `-p`: Parameter in format name=value or name=@file.json for complex values
- `--profile`: Profile name to use
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information
- `--skip-output-validation`: Skip output validation against the return type definition
- `--readonly`: Open database connection in read-only mode

**Examples:**
```bash
mxcp run tool my_tool --param name=value
mxcp run tool my_tool --param complex=@data.json
mxcp run tool my_tool --readonly
```

### `mxcp query`

Execute a SQL query directly against the database.

```bash
mxcp query [SQL] [OPTIONS]
```

**Arguments:**
- `SQL`: SQL query to execute (optional if --file is provided)

**Options:**
- `--file`: Path to SQL file
- `--param`, `-p`: Parameter in format name=value or name=@file.json for complex values
- `--profile`: Profile name to use
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information
- `--readonly`: Open database connection in read-only mode

**Examples:**
```bash
mxcp query "SELECT * FROM users WHERE age > 18" --param age=18
mxcp query --file complex_query.sql --param start_date=@dates.json
mxcp query "SELECT * FROM sales" --profile production --json-output
mxcp query "SELECT * FROM users" --readonly
```

### `mxcp validate`

Validates endpoint YAML files for correctness.

> 📖 For comprehensive validation, testing, and quality best practices, see the [Quality & Testing Guide](../guides/quality.md).

**Usage:**
```bash
mxcp validate [ENDPOINT] [OPTIONS]
```

**Arguments:**
- `ENDPOINT`: Name of endpoint to validate (optional)

**Options:**
- `--profile`: Profile name to use
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information
- `--readonly`: Open database connection in read-only mode

**Examples:**
```bash
mxcp validate                    # Validate all endpoints
mxcp validate my_endpoint       # Validate specific endpoint
mxcp validate --json-output     # Output results in JSON format
mxcp validate --readonly        # Open database connection in read-only mode
```

### `mxcp test`

Runs tests for endpoints to verify they work correctly.

> 📖 Learn how to write comprehensive tests and use assertion types in the [Quality & Testing Guide](../guides/quality.md#testing).

**Usage:**
```bash
mxcp test [ENDPOINT_TYPE] [NAME] [OPTIONS]
```

**Arguments:**
- `ENDPOINT_TYPE`: Type of endpoint to test (tool, resource, or prompt)
- `NAME`: Name of the specific endpoint to test

**Options:**
- `--user-context, -u`: User context as JSON string or @file.json for testing policy-protected endpoints
- `--profile`: Profile name to use
- `--json-output`: Output results in JSON format
- `--debug`: Show detailed debug information
- `--readonly`: Open database connection in read-only mode

**Examples:**

```bash
# Run all tests
mxcp test

# Test a specific endpoint
mxcp test tool my_tool

# Test with user context for policy testing
mxcp test tool employee_info --user-context '{"role": "admin", "user_id": "admin123"}'

# Test with context from file
mxcp test --user-context @contexts/hr_user.json

# Run tests with debugging
mxcp test --debug

# Run all tests in JSON output
mxcp test --json-output

# Test specific endpoint with user override
mxcp test resource user_list --user-context '{"permissions": ["user.read", "user.write"]}'
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

### `mxcp lint`

Checks endpoints for metadata quality issues and suggests improvements for better LLM performance.

> 📖 See the [Quality & Testing Guide](../guides/quality.md#linting) for metadata best practices and LLM optimization tips.

**Usage:**
```bash
mxcp lint [OPTIONS]
```

**Options:**
- `--profile`: Profile name to use
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information
- `--severity`: Minimum severity level to report (all, warning, info) - default: all

**Examples:**
```bash
mxcp lint                    # Check all endpoints for metadata issues
mxcp lint --severity warning # Show only warnings (skip info-level suggestions)
mxcp lint --json-output      # Output results in JSON format
```

**Description:**
The lint command analyzes your endpoints and suggests improvements to make them more effective for LLM usage. It checks for:

- **Missing descriptions** on endpoints, parameters, and return types
- **Missing test cases** to ensure endpoint reliability
- **Missing parameter examples** to guide LLM usage
- **Missing type descriptions** in nested structures
- **Missing tags** for better categorization

### `mxcp evals`

Runs LLM evaluation tests to verify how AI models interact with your endpoints.

> 📖 Learn about writing and running evals in the [Quality & Testing Guide](../guides/quality.md#llm-evaluation-evals).

**Usage:**
```bash
mxcp evals [SUITE_NAME] [OPTIONS]
```

**Arguments:**
- `SUITE_NAME`: Name of the eval suite to run (optional)

**Options:**
- `--user-context, -u`: User context as JSON string or @file.json
- `--model, -m`: Override model to use for evaluation
- `--profile`: Profile name to use
- `--json-output`: Output results in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
# Run all eval suites
mxcp evals

# Run specific eval suite
mxcp evals customer_analysis

# Override model for testing
mxcp evals --model gpt-4-turbo

# Run with user context
mxcp evals --user-context '{"role": "admin", "permissions": ["read:all"]}'

# Load context from file
mxcp evals --user-context @contexts/analyst.json

# JSON output for CI/CD
mxcp evals --json-output
```

**Description:**
The evals command executes evaluation tests that verify LLM behavior. Unlike regular tests that execute endpoints directly, evals:

1. Send prompts to an LLM
2. Verify the LLM calls appropriate tools
3. Check that responses contain expected information
4. Ensure safety by verifying destructive operations aren't called inappropriately

Eval files should have the suffix `-evals.yml` or `.evals.yml` and are automatically discovered in your repository.
- **Missing default values** on optional parameters
- **Missing behavioral annotations** on tools

The command reports issues at three severity levels:
- **Warning**: Important metadata that significantly improves LLM understanding
- **Info**: Nice-to-have metadata that further enhances the experience

Good metadata is crucial for LLM performance because it helps the model understand:
- What each endpoint does and when to use it
- Valid parameter values and formats
- Expected output structures
- Safety considerations (e.g., read-only vs destructive operations)

### `mxcp list`

List all available endpoints.

```bash
mxcp list [OPTIONS]
```

**Options:**
- `--profile`: Profile name to use
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp list                    # List all endpoints
mxcp list --json-output     # Output in JSON format
mxcp list --profile dev     # List endpoints in dev profile
```

### `mxcp drift-snapshot`

Generate a drift snapshot of the current state for change detection.

```bash
mxcp drift-snapshot [OPTIONS]
```

**Options:**
- `--profile`: Profile name to use
- `--force`: Overwrite existing snapshot file
- `--dry-run`: Show what would be done without writing the snapshot file
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp drift-snapshot                    # Generate snapshot using default profile
mxcp drift-snapshot --profile prod     # Generate snapshot using prod profile
mxcp drift-snapshot --force           # Overwrite existing snapshot
mxcp drift-snapshot --dry-run         # Show what would be done
mxcp drift-snapshot --json-output     # Output results in JSON format
```

**Description:**
Creates a snapshot of the current state of your MXCP repository, including:
- Database schema (tables and columns)
- Endpoint definitions (tools, resources, prompts)
- Validation results
- Test results

The snapshot is used as a baseline to detect drift between different environments or over time. For more information, see the [Drift Detection Guide](../features/drift-detection.md).

### `mxcp drift-check`

Check for drift between current state and baseline snapshot.

```bash
mxcp drift-check [OPTIONS]
```

**Options:**
- `--profile`: Profile name to use
- `--baseline`: Path to baseline snapshot file (defaults to profile drift path)
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information
- `--readonly`: Open database connection in read-only mode

**Examples:**
```bash
mxcp drift-check                           # Check against default baseline
mxcp drift-check --baseline path/to/snap   # Check against specific baseline
mxcp drift-check --json-output             # Output results in JSON format
mxcp drift-check --debug                   # Show detailed change information
mxcp drift-check --readonly                # Open database in read-only mode
```

**Description:**
Compares the current state of your database and endpoints against a previously generated baseline snapshot to detect any changes. Reports:
- Added, removed, or modified database tables and columns
- Added, removed, or modified endpoints
- Changes in validation or test results

Exit code is 1 if drift is detected, 0 if no drift. For more information, see the [Drift Detection Guide](../features/drift-detection.md).

### `mxcp log`

Query MXCP audit logs for tool, resource, and prompt executions.

```bash
mxcp log [OPTIONS]
```

**Options:**
- `--profile`: Profile name to use
- `--tool`: Filter by specific tool name
- `--resource`: Filter by specific resource URI
- `--prompt`: Filter by specific prompt name
- `--type`: Filter by event type (tool, resource, or prompt)
- `--policy`: Filter by policy decision (allow, deny, warn, or n/a)
- `--status`: Filter by execution status (success or error)
- `--since`: Show logs since specified time (e.g., 10m, 2h, 1d)
- `--limit`: Maximum number of results (default: 100)
- `--export-csv`: Export results to CSV file
- `--export-duckdb`: Export all logs to DuckDB database file
- `--json`: Output in JSON format
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp log                           # Show recent logs
mxcp log --tool my_tool            # Filter by specific tool
mxcp log --policy denied           # Show blocked executions
mxcp log --since 10m               # Logs from last 10 minutes
mxcp log --since 2h --status error # Errors from last 2 hours
mxcp log --export-csv audit.csv    # Export to CSV file
mxcp log --export-duckdb audit.db  # Export to DuckDB database
mxcp log --json                    # Output as JSON
```

**Time Formats:**
- `10s` - 10 seconds
- `5m` - 5 minutes
- `2h` - 2 hours
- `1d` - 1 day

**Description:**
Queries the audit logs to show execution history for tools, resources, and prompts. Audit logging must be enabled in your profile configuration. The command displays results in a tabular format by default, showing timestamp, type, name, status, policy decision, duration, and caller. 

Audit logs are stored in JSONL (JSON Lines) format, which allows concurrent reading while the server is running - no database locking issues. The `--export-duckdb` option allows you to convert the logs to a DuckDB database for complex SQL analysis.

For more information, see the [Audit Logging Guide](../features/auditing.md).

### `mxcp dbt-config`

Generate or patch dbt side-car files (dbt_project.yml + profiles.yml).

```bash
mxcp dbt-config [OPTIONS]
```

**Options:**
- `--profile`: Override the profile name from mxcp-site.yml
- `--dry-run`: Show what would be written without making changes
- `--force`: Overwrite existing profile without confirmation
- `--embed-secrets`: Embed secrets directly in profiles.yml
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp dbt-config                    # Generate dbt configuration files
mxcp dbt-config --dry-run         # Show what would be written
mxcp dbt-config --embed-secrets   # Embed secrets in profiles.yml
```

### `mxcp dbt`

Wrapper for dbt CLI that injects secrets as environment variables.

```bash
mxcp dbt [DBT_COMMAND] [OPTIONS]
```

**Arguments:**
- `DBT_COMMAND`: Any valid dbt command and its options

**Options:**
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp dbt run --select my_model
mxcp dbt test
mxcp dbt docs generate
```

## Output Formats

### JSON Output

When using `--json-output`, commands return structured JSON with the following format:

```json
{
  "status": "ok" | "error",
  "result": <command-specific result>,
  "error": <error message if status is "error">,
  "traceback": <traceback if debug is enabled>
}
```

### Human-Readable Output

By default, commands output results in a human-readable format:

- Success messages are shown in standard output
- Error messages are shown in standard error
- Debug information (when enabled) includes detailed error traces
- Lists and tables are formatted for easy reading

## Error Handling

All commands handle errors consistently:

1. Invalid arguments or options show usage information
2. Runtime errors show descriptive messages
3. With `--debug`, full tracebacks are included
4. With `--json-output`, errors are returned in JSON format

## Environment Variables

The following environment variables can be used to configure MXCP:

- `MXCP_DEBUG`: Enable debug logging (equivalent to --debug)
- `MXCP_PROFILE`: Set default profile (equivalent to --profile)
- `MXCP_READONLY`: Enable read-only mode (equivalent to --readonly)
- `MXCP_DUCKDB_PATH`: Override the DuckDB file location from configuration

For more details on environment variables and their usage, see the [Configuration Guide](../guides/configuration.md#environment-variables). 