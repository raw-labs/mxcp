# MXCP CLI Reference

This document provides a comprehensive reference for all MXCP command-line interface (CLI) commands and their options.

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
- `--no-sql-tools`: Disable built-in SQL querying and schema exploration tools
- `--readonly`: Open database connection in read-only mode
- `--stateless`: Enable stateless HTTP mode for Claude.ai and serverless deployments

**Examples:**
```bash
mxcp serve                   # Use transport settings from user config
mxcp serve --port 9000       # Override port from user config
mxcp serve --transport stdio # Override transport from user config
mxcp serve --profile dev     # Use the 'dev' profile configuration
mxcp serve --no-sql-tools    # Disable built-in SQL querying tools
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

Validate one or all endpoints.

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

Run tests for one or all endpoints.

```bash
mxcp test [ENDPOINT_TYPE] [NAME] [OPTIONS]
```

**Arguments:**
- `ENDPOINT_TYPE`: Type of endpoint (tool, resource, or prompt) (optional)
- `NAME`: Name of endpoint to test (optional)

**Options:**
- `--profile`: Profile name to use
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information
- `--readonly`: Open database connection in read-only mode

**Examples:**
```bash
mxcp test                        # Test all endpoints
mxcp test tool my_tool          # Test specific tool endpoint
mxcp test --json-output         # Output results in JSON format
mxcp test --readonly            # Open database connection in read-only mode
```

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

### `mxcp lsp`

Start the MXCP LSP server for language server features.

```bash
mxcp lsp [OPTIONS]
```

**Options:**
- `--profile`: Profile name to use
- `--port`: Port number for LSP server (defaults to 3000)
- `--debug`: Show detailed debug information
- `--readonly`: Open database connection in read-only mode

**Examples:**
```bash
mxcp lsp                     # Start LSP server on default port 3000
mxcp lsp --port 4000         # Start LSP server on port 4000  
mxcp lsp --profile dev       # Use the 'dev' profile configuration
mxcp lsp --readonly          # Open database connection in read-only mode
mxcp lsp --debug             # Start with detailed debug logging
```

**Description:**
Starts an LSP (Language Server Protocol) server that provides language features like code completion, hover information, and go-to-definition for MXCP endpoints and SQL queries. The server integrates with your DuckDB database to provide context-aware suggestions based on your database schema and available endpoints.

The LSP server can be used with any LSP-compatible editor or IDE to enhance the development experience when working with MXCP projects.

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

The snapshot is used as a baseline to detect drift between different environments or over time. For more information, see the [Drift Detection Guide](drift-detection.md).

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

Exit code is 1 if drift is detected, 0 if no drift. For more information, see the [Drift Detection Guide](drift-detection.md).

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