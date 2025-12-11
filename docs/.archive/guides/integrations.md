---
title: "Integrations"
description: "Integrate MXCP with AI platforms, dbt, and data sources. Connect with Claude Desktop, OpenAI, and other LLM providers. Access diverse data sources through DuckDB."
sidebar:
  order: 3
---

MXCP provides seamless integration with AI platforms and data tools to create powerful, production-ready AI applications. This guide covers how to connect MXCP with LLMs, transform data with dbt, and access diverse data sources through DuckDB.

## Table of Contents

- [LLM Integration](#llm-integration) — Connect with Claude Desktop, OpenAI, and other AI platforms
- [dbt Integration](#dbt-integration) — Transform and prepare data for AI consumption
- [DuckDB Integration](#duckdb-integration) — Access diverse data sources with powerful SQL capabilities

## LLM Integration

MXCP implements the Model Context Protocol (MCP), making it compatible with various AI platforms and tools. This section covers how to integrate MXCP with different LLM providers and clients.

### Claude Desktop

Claude Desktop has native MCP support, making it the easiest way to get started with MXCP.

#### Configuration

1. **Locate Claude's Configuration File**:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

2. **Add Your MXCP Server**:

   For global installations:
   ```json
   {
     "mcpServers": {
       "my-project": {
         "command": "mxcp",
         "args": ["serve", "--transport", "stdio"],
         "cwd": "/absolute/path/to/your/mxcp/project"
       }
     }
   }
   ```

   For virtual environment installations:
   ```json
   {
     "mcpServers": {
       "my-project": {
         "command": "bash",
         "args": [
           "-c",
           "cd /absolute/path/to/your/project && source /path/to/.venv/bin/activate && mxcp serve --transport stdio"
         ]
       }
     }
   }
   ```

3. **Restart Claude Desktop** to load the new configuration.

#### Best Practices

- Use descriptive server names that reflect your project's purpose
- Test your configuration with simple queries first
- Monitor Claude's developer console for connection issues

### OpenAI and Other Providers

While MXCP uses the MCP protocol, you can integrate with OpenAI and other providers using MCP adapters or custom implementations.

#### Custom Integration

For custom integrations, you can:

1. **Use MXCP's HTTP mode**:
   ```bash
   mxcp serve --transport http --port 8000
   ```

2. **Call endpoints directly**:
   ```python
   import requests
   
   response = requests.post("http://localhost:8000/tools/call", json={
       "name": "get_earthquakes",
       "arguments": {"magnitude_min": 5.0}
   })
   ```

### Command Line Tools

#### mcp-cli

A command-line interface for interacting with MCP servers:

```bash
# Install
pip install mcp-cli

# Configure (same server config as Claude Desktop)
echo '{
  "mcpServers": {
    "local": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/path/to/your/project"
    }
  }
}' > server_config.json

# Use
mcp-cli tools list
mcp-cli tools call get_earthquakes --magnitude_min 5.0
```

#### Direct stdio Integration

For custom scripts, you can interact directly with MXCP's stdio interface:

```python
import subprocess
import json

# Start MXCP server
process = subprocess.Popen(
    ["mxcp", "serve", "--transport", "stdio"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd="/path/to/your/project"
)

# Send MCP request
request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "get_earthquakes",
        "arguments": {"magnitude_min": 5.0}
    }
}

process.stdin.write(json.dumps(request) + "\n")
process.stdin.flush()

# Read response
response = process.stdout.readline()
result = json.loads(response)
```

#### Debugging

Enable debug logging:
```bash
# Set environment variable
export MXCP_LOG_LEVEL=DEBUG

# Or use CLI flag
mxcp serve --log-level DEBUG
```

Check server status:
```bash
mxcp list
mxcp validate
mxcp test
```

## dbt Integration

dbt (data build tool) is a critical component of MXCP's production methodology. It's not just an optional integration - it's **the foundation** for building reliable MCP servers with high-quality data.

### Why dbt is Essential

In the MXCP methodology, dbt serves as your data quality layer:

1. **Data Modeling**: Transform raw data into well-structured models
2. **Quality Testing**: Ensure data meets your requirements before it reaches AI
3. **Performance**: Create materialized views for fast query response
4. **Documentation**: Generate clear documentation for your data models
5. **Version Control**: Track all data transformations in Git

### The dbt + MXCP Workflow

```
Raw Data → dbt Models → DuckDB Tables → MXCP Endpoints → AI Tools
         ↓
    Quality Tests
    Data Contracts
    Documentation
```

This approach ensures that:
- Your AI tools work with clean, validated data
- Performance is optimized through proper materialization
- Changes are tracked and tested before deployment
- Data quality issues are caught early, not in production

### Configuration

Enable dbt in your `mxcp-site.yml`:

```yaml
dbt:
  enabled: true
```

For more details on dbt configuration, see the [Configuration Guide](configuration).

### Commands

MXCP provides two main commands for working with dbt:

1. `mxcp dbt-config`: Generates and manages dbt configuration files
   ```bash
   # Generate dbt configuration files
   mxcp dbt-config
   
   # Show what would be written without making changes
   mxcp dbt-config --dry-run
   
   # Embed secrets directly in profiles.yml (requires --force)
   mxcp dbt-config --embed-secrets --force
   ```

2. `mxcp dbt`: A wrapper around the dbt CLI that injects secrets
   ```bash
   # Run dbt models
   mxcp dbt run --select my_model
   
   # Run tests
   mxcp dbt test
   
   # Generate documentation
   mxcp dbt docs generate
   ```

### Use Cases

dbt integration is particularly useful for:

1. **Data Preparation**: Transform raw data into LLM-friendly formats
   ```sql
   -- models/llm_ready/customer_summary.sql
   SELECT 
     customer_id,
     name,
     email,
     -- Format complex data for LLM consumption
     json_object(
       'total_orders', COUNT(orders.id),
       'last_order_date', MAX(orders.created_at),
       'favorite_category', (
         SELECT category
         FROM (
           SELECT category, COUNT(*) as cnt
           FROM orders
           WHERE orders.customer_id = customers.id
           GROUP BY category
           ORDER BY cnt DESC
           LIMIT 1
         )
       )
     ) as customer_context
   FROM customers
   LEFT JOIN orders ON customers.id = orders.customer_id
   GROUP BY customer_id, name, email
   ```

2. **Performance Optimization**: Create materialized views for frequently accessed data
   ```sql
   -- models/llm_ready/remote_data_cache.sql
   {{ config(materialized='table') }}
   SELECT 
     date,
     -- Cache remote data locally for faster access
     COUNT(*) as record_count,
     AVG(value) as avg_value
   FROM read_parquet('https://example.com/data/*.parquet')
   GROUP BY date
   ```

## DuckDB Integration

DuckDB serves as MXCP's execution engine, providing fast, local-first data access with extensive connectivity options.

### Extensions

DuckDB's power comes from its extensibility. MXCP supports three types of extensions:

1. **Core Extensions**: Built-in extensions
   ```yaml
   extensions:
     - "httpfs"  # HTTP/HTTPS file system
     - "parquet" # Parquet file support
     - "json"    # JSON file support
   ```

2. **Community Extensions**: Community-maintained extensions
   ```yaml
   extensions:
     - name: "extension_name"
       repo: "community"
   ```

3. **Nightly Extensions**: Latest development versions
   ```yaml
   extensions:
     - name: "extension_name"
       repo: "core_nightly"
   ```

### Data Sources

DuckDB extensions enable access to various data sources. Note that you need to enable the appropriate extension before using its functions. The following are just some examples - consult the [DuckDB documentation](https://duckdb.org/docs/extensions/overview) for a complete list of available data sources and their requirements.

1. **Remote Files** (requires `httpfs` extension)
   ```sql
   -- Read from S3
   SELECT * FROM read_parquet('s3://bucket/path/file.parquet');
   
   -- Read from HTTP
   SELECT * FROM read_csv('https://example.com/data.csv');
   ```

2. **Databases** (requires specific database extensions)
   ```sql
   -- Read from PostgreSQL (requires postgres extension)
   SELECT * FROM postgres_scan('connection_string', 'schema.table');
   
   -- Read from MySQL (requires mysql extension)
   SELECT * FROM mysql_scan('connection_string', 'schema.table');
   ```

3. **Local Files**
   ```sql
   -- Read Parquet
   SELECT * FROM read_parquet('data/*.parquet');
   
   -- Read CSV
   SELECT * FROM read_csv('data/*.csv');
   ```

### Secret Management

To use secure connections, configure secrets in `~/.mxcp/config.yml`. Here's an example for the `httpfs` extension:

```yaml
mxcp: 1
projects:
  my_project:
    profiles:
      dev:
        secrets:
          - name: http_auth_token
            type: http
            parameters:
              BEARER_TOKEN: "your_bearer_token"
          - name: http_headers_token
            type: http
            parameters:
              EXTRA_HTTP_HEADERS:
                Authorization: "Bearer your_token"
                X-Custom-Header: "custom_value"
```

Then reference these secrets in `mxcp-site.yml`:

```yaml
mxcp: 1
project: my_project
profile: dev
secrets:
  - http_auth_token
  - http_headers_token
```

For more details on secret management, see the [Configuration Guide](configuration#secrets).

### Best Practices

1. **Extension Management**
   - Only enable extensions you need
   - Use community extensions for specialized functionality
   - Keep core extensions up to date
   - Check extension documentation for required configuration

2. **Secret Security**
   - Never commit secrets to version control
   - Use environment variables or Vault for sensitive data
   - Rotate credentials regularly

3. **Performance**
   - Use materialized views for frequently accessed data
   - Leverage DuckDB's parallel processing capabilities

4. **Data Quality**
   - Use tests to ensure data consistency
   - Implement data validation in your models
   - Monitor for schema drift using MXCP's [drift detection](../features/drift-detection)
