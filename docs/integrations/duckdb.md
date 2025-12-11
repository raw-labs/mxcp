---
title: "DuckDB Integration"
description: "MXCP's SQL execution engine. Extensions, data sources, secret management, and performance optimization."
sidebar:
  order: 4
---

DuckDB serves as MXCP's SQL execution engine, providing fast, local-first data access with extensive connectivity options.

## Overview

DuckDB enables:
- **Fast Analytics**: In-process OLAP database
- **Multi-Source**: Connect to S3, HTTP, PostgreSQL, MySQL, and more
- **Extensions**: Rich ecosystem for additional functionality
- **Zero Setup**: No external database server required

## Extensions

### Core Extensions

Built-in extensions for common functionality:

```yaml
# mxcp-site.yml
extensions:
  - httpfs     # HTTP/HTTPS file system
  - parquet    # Parquet file support
  - json       # JSON file support
```

### Community Extensions

Community-maintained extensions:

```yaml
extensions:
  - name: extension_name
    repo: community
```

### Nightly Extensions

Latest development versions:

```yaml
extensions:
  - name: extension_name
    repo: core_nightly
```

### Common Extensions

| Extension | Purpose |
|-----------|---------|
| `httpfs` | Read from HTTP/HTTPS URLs |
| `parquet` | Parquet file support |
| `json` | JSON file handling |
| `postgres` | PostgreSQL connectivity |
| `mysql` | MySQL connectivity |
| `sqlite` | SQLite file access |
| `spatial` | Geospatial functions |
| `fts` | Full-text search |

## Data Sources

### Local Files

Read from local filesystem:

```sql
-- Parquet files
SELECT * FROM read_parquet('data/*.parquet');

-- CSV files
SELECT * FROM read_csv('data/users.csv');

-- JSON files
SELECT * FROM read_json('data/events.json');

-- Glob patterns
SELECT * FROM read_parquet('data/year=*/month=*/*.parquet');
```

### Remote Files (httpfs)

Read from HTTP/HTTPS URLs:

```sql
-- HTTP CSV
SELECT * FROM read_csv('https://example.com/data.csv');

-- HTTPS Parquet
SELECT * FROM read_parquet('https://bucket.s3.amazonaws.com/data.parquet');
```

### S3 (httpfs)

Read from Amazon S3:

```sql
-- S3 with public access
SELECT * FROM read_parquet('s3://public-bucket/data.parquet');

-- S3 with credentials (via secrets)
SELECT * FROM read_parquet('s3://private-bucket/data.parquet');
```

### PostgreSQL

Connect to PostgreSQL databases:

```sql
-- Attach PostgreSQL database
ATTACH 'postgresql://user:pass@host:5432/db' AS pg;

-- Query tables
SELECT * FROM pg.schema.table;

-- Scan specific table
SELECT * FROM postgres_scan('connection_string', 'schema', 'table');
```

### MySQL

Connect to MySQL databases:

```sql
-- Attach MySQL database
ATTACH 'mysql://user:pass@host:3306/db' AS mysql;

-- Query tables
SELECT * FROM mysql.table;

-- Scan specific table
SELECT * FROM mysql_scan('connection_string', 'schema', 'table');
```

### SQLite

Read SQLite databases:

```sql
-- Attach SQLite database
ATTACH 'path/to/database.sqlite' AS sqlite_db;

-- Query tables
SELECT * FROM sqlite_db.users;
```

## Secret Management

### Configuration

Configure secrets in `~/.mxcp/config.yml`:

```yaml
mxcp: 1
projects:
  my_project:
    profiles:
      dev:
        secrets:
          # S3 credentials
          - name: s3_creds
            type: s3
            parameters:
              KEY_ID: "${AWS_ACCESS_KEY_ID}"
              SECRET: "${AWS_SECRET_ACCESS_KEY}"
              REGION: "us-east-1"

          # HTTP authentication
          - name: http_auth
            type: http
            parameters:
              BEARER_TOKEN: "${API_TOKEN}"

          # PostgreSQL connection
          - name: pg_connection
            type: postgres
            parameters:
              HOST: "db.example.com"
              PORT: 5432
              USER: "${DB_USER}"
              PASSWORD: "${DB_PASSWORD}"
              DATABASE: "production"
```

### Reference Secrets

In `mxcp-site.yml`:

```yaml
mxcp: 1
project: my_project
profile: dev

secrets:
  - s3_creds
  - http_auth
  - pg_connection
```

### Secret Types

| Type | Use Case | Parameters |
|------|----------|------------|
| `s3` | AWS S3 access | KEY_ID, SECRET, REGION, ENDPOINT |
| `gcs` | Google Cloud Storage | BUCKET, KEY_FILE |
| `azure` | Azure Blob Storage | CONNECTION_STRING |
| `http` | HTTP authentication | BEARER_TOKEN, EXTRA_HTTP_HEADERS |
| `postgres` | PostgreSQL | HOST, PORT, USER, PASSWORD, DATABASE |
| `mysql` | MySQL | HOST, PORT, USER, PASSWORD, DATABASE |

### HTTP Headers Example

```yaml
secrets:
  - name: custom_api
    type: http
    parameters:
      EXTRA_HTTP_HEADERS:
        Authorization: "Bearer ${API_TOKEN}"
        X-API-Key: "${API_KEY}"
        X-Custom-Header: "custom_value"
```

## MXCP Integration

### SQL Endpoints

Use DuckDB features in MXCP endpoints:

```yaml
# tools/query_remote.yml
mxcp: 1
tool:
  name: query_remote_data
  description: Query remote Parquet files
  parameters:
    - name: year
      type: integer
      description: Year to query
  return:
    type: array
    items:
      type: object
  source:
    code: |
      SELECT *
      FROM read_parquet(
        's3://data-bucket/year=' || $year || '/*.parquet'
      )
      LIMIT 100
```

### Multi-Source Joins

Join data from multiple sources:

```yaml
# tools/cross_source_report.yml
mxcp: 1
tool:
  name: cross_source_report
  description: Join local and remote data
  return:
    type: array
    items:
      type: object
  source:
    code: |
      WITH local_customers AS (
        SELECT * FROM customers
      ),
      remote_orders AS (
        SELECT * FROM read_parquet('s3://orders/*.parquet')
      )
      SELECT
        c.customer_id,
        c.name,
        COUNT(o.order_id) as order_count
      FROM local_customers c
      LEFT JOIN remote_orders o
        ON c.customer_id = o.customer_id
      GROUP BY c.customer_id, c.name
```

## Performance Optimization

### Materialized Views

Pre-compute expensive queries:

```sql
-- Create materialized view
CREATE TABLE customer_stats AS
SELECT
  customer_id,
  COUNT(*) as order_count,
  SUM(total) as total_spent
FROM orders
GROUP BY customer_id;
```

### Partitioned Data

Query partitioned data efficiently:

```sql
-- Only read relevant partitions
SELECT *
FROM read_parquet('s3://bucket/year=*/month=*/*.parquet')
WHERE year = 2024 AND month = 6;
```

### Parallel Processing

DuckDB automatically parallelizes queries:

```sql
-- Configure thread count
SET threads TO 8;

-- Configure memory limit
SET memory_limit TO '4GB';
```

### Query Hints

Optimize specific queries:

```sql
-- Force specific join order
SELECT /*+ MERGE_JOIN(a, b) */ *
FROM table_a a
JOIN table_b b ON a.id = b.a_id;
```

## Common Patterns

### Caching Remote Data

Cache expensive remote queries:

```yaml
# tools/cached_query.yml
mxcp: 1
tool:
  name: cached_analytics
  description: Query cached remote data
  return:
    type: array
    items:
      type: object
  source:
    code: |
      -- Use dbt to materialize this
      SELECT * FROM cached_remote_data
```

With dbt model:

```sql
-- models/marts/cached_remote_data.sql
{{ config(materialized='table') }}

SELECT *
FROM read_parquet('https://example.com/large_dataset.parquet')
```

### Time-Based Filtering

Query by time range:

```sql
SELECT *
FROM read_parquet('s3://logs/*.parquet')
WHERE event_time >= CURRENT_DATE - INTERVAL '7 days';
```

### JSON Processing

Work with JSON data:

```sql
-- Parse JSON fields
SELECT
  id,
  json_extract(data, '$.name') as name,
  json_extract(data, '$.nested.field') as nested_value
FROM read_json('data.json');

-- Unnest arrays
SELECT
  id,
  unnest(json_extract(data, '$.items')) as item
FROM events;
```

### Full-Text Search

Search text columns:

```sql
-- Enable FTS extension
INSTALL fts;
LOAD fts;

-- Create index
PRAGMA create_fts_index('documents', 'doc_id', 'content');

-- Search
SELECT *
FROM documents
WHERE fts_match('documents', 'search query');
```

## Troubleshooting

### "Extension not found"

```yaml
# Ensure extension is listed
extensions:
  - httpfs  # Must be listed to use HTTP URLs
```

### "Access denied"

Check secrets configuration:

```bash
# Verify secrets are loaded
mxcp validate

# Check secret values
mxcp dbt-config --embed-secrets --dry-run
```

### "Connection timeout"

```yaml
# Increase timeout
extensions:
  - name: httpfs
    config:
      http_timeout: 60000  # milliseconds
```

### "Out of memory"

```sql
-- Reduce memory usage
SET memory_limit TO '2GB';

-- Or process in chunks
SELECT * FROM large_table LIMIT 1000 OFFSET 0;
```

## Configuration Reference

### Extension Configuration

```yaml
# mxcp-site.yml
extensions:
  # Simple extension
  - httpfs

  # Extension with configuration
  - name: httpfs
    config:
      http_timeout: 30000

  # Community extension
  - name: spatial
    repo: community

  # Nightly extension
  - name: experimental_feature
    repo: core_nightly
```

### Database Settings

```yaml
# mxcp-site.yml
database:
  path: ":memory:"  # In-memory (default)
  # path: "data.duckdb"  # Persistent

  settings:
    threads: 4
    memory_limit: "4GB"
    temp_directory: "/tmp/duckdb"
```

## Best Practices

### 1. Enable Only Needed Extensions

```yaml
extensions:
  - httpfs      # Only if using HTTP
  - parquet     # Only if using Parquet
```

### 2. Use Secrets for Credentials

Never hardcode credentials:

```yaml
# Good: Use secrets
secrets:
  - s3_creds

# Bad: Hardcoded values
# Never do this!
```

### 3. Materialize Frequent Queries

Use dbt to materialize:

```sql
{{ config(materialized='table') }}
SELECT * FROM expensive_query
```

### 4. Partition Large Datasets

Organize data by query patterns:

```
s3://bucket/
  year=2024/
    month=01/
      data.parquet
    month=02/
      data.parquet
```

### 5. Monitor Query Performance

```sql
-- Enable profiling
PRAGMA enable_progress_bar;
EXPLAIN ANALYZE SELECT * FROM large_table;
```

## Next Steps

- [dbt Integration](dbt) - Data transformation
- [Configuration](/operations/configuration) - Secrets management
- [Monitoring](/operations/monitoring) - Performance tracking
