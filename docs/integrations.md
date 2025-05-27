# MXCP Integrations

MXCP provides seamless integration with two powerful tools: dbt for data transformation and DuckDB for data access. This guide explains how to use these integrations effectively.

## dbt Integration

dbt (data build tool) is a powerful SQL-first transformation tool that helps you transform data in your warehouse. MXCP integrates with dbt to help you prepare and optimize your data for LLM consumption.

### Configuration

Enable dbt in your `mxcp-site.yml`:

```yaml
dbt:
  enabled: true
```

For more details on dbt configuration, see the [Configuration Guide](configuration.md#dbt-integration).

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
mxcp: "1.0.0"
projects:
  my_project:
    default: dev
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
mxcp: "1.0.0"
project: my_project
profile: dev
secrets:
  - http_auth_token
  - http_headers_token
```

For more details on secret management, see the [Configuration Guide](configuration.md#secrets).

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
   - Monitor for schema drift using MXCP's [drift detection](drift-detection.md) 