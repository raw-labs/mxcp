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
- `--transport`: Transport protocol to use (streamable-http, sse, or stdio)
- `--port`: Port number for HTTP transport (default: 8000)
- `--debug`: Show detailed debug information
- `--no-sql-tools`: Disable built-in SQL querying and schema exploration tools
- `--readonly`: Open database connection in read-only mode

**Examples:**
```bash
mxcp serve                   # Start HTTP server on default port 8000
mxcp serve --port 9000       # Start HTTP server on port 9000
mxcp serve --transport stdio # Use stdio transport instead of HTTP
mxcp serve --profile dev     # Use the 'dev' profile configuration
mxcp serve --no-sql-tools    # Disable built-in SQL querying tools
mxcp serve --readonly        # Open database connection in read-only mode
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
mxcp test [ENDPOINT] [OPTIONS]
```

**Arguments:**
- `ENDPOINT`: Name of endpoint to test (optional)

**Options:**
- `--profile`: Profile name to use
- `--json-output`: Output in JSON format
- `--debug`: Show detailed debug information
- `--readonly`: Open database connection in read-only mode

**Examples:**
```bash
mxcp test                    # Test all endpoints
mxcp test my_endpoint       # Test specific endpoint
mxcp test --json-output     # Output results in JSON format
mxcp test --readonly        # Open database connection in read-only mode
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