---
title: "SQL Reference"
description: "SQL capabilities in MXCP. DuckDB syntax, built-in authentication functions, and parameter binding."
sidebar:
  order: 3
---

MXCP uses DuckDB SQL syntax with additional built-in functions for authentication and access control.

## DuckDB SQL

MXCP endpoints use [DuckDB SQL](https://duckdb.org/docs/sql/introduction), which extends PostgreSQL syntax with analytical features:

- **PostgreSQL Compatible**: Most PostgreSQL queries work unchanged
- **Column-Store Engine**: Optimized for analytical queries
- **Rich Type System**: Arrays, structs, maps, and more
- **Window Functions**: Full analytical window function support
- **CTEs**: Common Table Expressions with recursive support

## Built-in Functions

### Authentication Functions

When authentication is enabled, these functions provide user information:

| Function | Returns | Description |
|----------|---------|-------------|
| `get_username()` | VARCHAR | Authenticated user's username |
| `get_user_email()` | VARCHAR | User's email address |
| `get_user_provider()` | VARCHAR | OAuth provider (github, atlassian, etc.) |
| `get_user_external_token()` | VARCHAR | User's OAuth token |

All functions return empty string (`""`) when authentication is disabled or user is not authenticated.

### Examples

```sql
-- Filter data by authenticated user
SELECT * FROM projects
WHERE owner = get_username();

-- Access external API with user's token
SELECT *
FROM read_json_auto(
    'https://api.github.com/user/repos',
    headers = MAP {
        'Authorization': 'Bearer ' || get_user_external_token(),
        'User-Agent': 'MXCP-' || get_username()
    }
);

-- Audit logging
INSERT INTO audit_log (user, action, timestamp)
VALUES (get_username(), 'query_executed', NOW());

-- User-specific data
SELECT
    id,
    title,
    CASE
        WHEN owner = get_username() THEN content
        ELSE '[Restricted]'
    END as content
FROM documents;
```

### Request Header Functions

HTTP transport exposes request headers:

| Function | Returns | Description |
|----------|---------|-------------|
| `get_request_header(name)` | VARCHAR | Specific header value |
| `get_request_headers_json()` | VARCHAR | All headers as JSON |

```sql
-- Forward authorization header
SELECT http_post(
    'https://example.internal/audit',
    headers := map {
        'Authorization': get_request_header('Authorization')
    },
    body := json('{"status": "ok"}')
);

-- Access custom headers
SELECT get_request_header('X-Request-ID') as request_id;

-- Get all headers
SELECT get_request_headers_json() as all_headers;
```

## Parameter Binding

Use named parameters with `$` prefix:

```sql
-- Simple parameters
SELECT * FROM users WHERE id = $user_id;

-- Multiple parameters
SELECT * FROM orders
WHERE customer_id = $customer_id
  AND status = $status
  AND created_at > $since;

-- String parameters
SELECT * FROM products
WHERE name LIKE '%' || $search || '%';

-- Array parameters
SELECT * FROM users
WHERE id IN (SELECT unnest($user_ids));
```

### In YAML Endpoints

```yaml
tool:
  name: search_users
  parameters:
    - name: department
      type: string
    - name: min_age
      type: integer
  source:
    code: |
      SELECT * FROM users
      WHERE department = $department
        AND age >= $min_age
```

### From CLI

```bash
mxcp query "SELECT * FROM users WHERE age > $age" --param age=18
mxcp run tool search_users --param department=Engineering --param min_age=25
```

## Common Extensions

MXCP typically loads these DuckDB extensions:

### httpfs

Read from HTTP/S3 endpoints:

```sql
-- HTTP files
SELECT * FROM read_csv('https://example.com/data.csv');

-- S3 files
SELECT * FROM read_parquet('s3://bucket/data.parquet');
```

### json

JSON parsing and manipulation:

```sql
-- Parse JSON
SELECT json_extract(data, '$.name') as name FROM events;

-- JSON arrays
SELECT unnest(json_extract(data, '$.items')) as item FROM orders;
```

### parquet

Parquet file support:

```sql
-- Read Parquet
SELECT * FROM read_parquet('data/*.parquet');

-- Write Parquet
COPY (SELECT * FROM users) TO 'output.parquet';
```

### postgres

PostgreSQL connectivity:

```sql
-- Attach database
ATTACH 'postgresql://user:pass@host:5432/db' AS pg;

-- Query tables
SELECT * FROM pg.public.users;
```

### excel

Excel file support:

```sql
-- Read Excel
SELECT * FROM read_xlsx('report.xlsx', sheet='Data');
```

## Analytical Features

### Window Functions

```sql
-- Running totals
SELECT
    date,
    amount,
    SUM(amount) OVER (ORDER BY date) as running_total
FROM sales;

-- Ranking
SELECT
    name,
    score,
    RANK() OVER (ORDER BY score DESC) as rank
FROM players;

-- Partitioned calculations
SELECT
    department,
    employee,
    salary,
    AVG(salary) OVER (PARTITION BY department) as dept_avg
FROM employees;
```

### Common Table Expressions

```sql
-- Simple CTE
WITH active_users AS (
    SELECT * FROM users WHERE status = 'active'
)
SELECT * FROM active_users WHERE age > 25;

-- Multiple CTEs
WITH
  orders_2024 AS (
    SELECT * FROM orders WHERE year = 2024
  ),
  high_value AS (
    SELECT * FROM orders_2024 WHERE total > 1000
  )
SELECT customer_id, COUNT(*) as high_value_orders
FROM high_value
GROUP BY customer_id;

-- Recursive CTE
WITH RECURSIVE subordinates AS (
    SELECT id, name, manager_id, 1 as level
    FROM employees WHERE id = $root_id

    UNION ALL

    SELECT e.id, e.name, e.manager_id, s.level + 1
    FROM employees e
    JOIN subordinates s ON e.manager_id = s.id
)
SELECT * FROM subordinates;
```

### PIVOT and UNPIVOT

```sql
-- Pivot data
PIVOT sales ON month USING SUM(amount);

-- Unpivot data
UNPIVOT monthly_data ON (jan, feb, mar) INTO
    NAME month
    VALUE amount;
```

### List Aggregations

```sql
-- Collect into arrays
SELECT
    department,
    LIST(name) as employees
FROM users
GROUP BY department;

-- Array operations
SELECT
    department,
    ARRAY_AGG(salary ORDER BY salary DESC) as salaries
FROM employees
GROUP BY department;
```

## Type System

### Basic Types

| Type | Example |
|------|---------|
| `VARCHAR` | `'hello'` |
| `INTEGER` | `42` |
| `DOUBLE` | `3.14` |
| `BOOLEAN` | `true`, `false` |
| `DATE` | `DATE '2024-01-01'` |
| `TIMESTAMP` | `TIMESTAMP '2024-01-01 12:00:00'` |

### Complex Types

```sql
-- Arrays
SELECT [1, 2, 3] as numbers;
SELECT array_agg(name) as names FROM users;

-- Structs
SELECT {'name': 'Alice', 'age': 30} as person;
SELECT struct_pack(name := 'Alice', age := 30);

-- Maps
SELECT MAP {'key1': 'value1', 'key2': 'value2'};
```

### Type Casting

```sql
-- Explicit cast
SELECT CAST(age AS VARCHAR) as age_str FROM users;

-- Cast shorthand
SELECT age::VARCHAR as age_str FROM users;

-- Try cast (returns NULL on failure)
SELECT TRY_CAST(value AS INTEGER) FROM data;
```

## Best Practices

### 1. Use Parameters

Always use parameters for user input:

```sql
-- Good: Parameterized
SELECT * FROM users WHERE id = $user_id;

-- Bad: String concatenation (SQL injection risk)
SELECT * FROM users WHERE id = ''' + user_id + ''';
```

### 2. Limit Results

Always limit large result sets:

```sql
SELECT * FROM logs
ORDER BY timestamp DESC
LIMIT 100;
```

### 3. Use CTEs for Clarity

```sql
-- Clear and readable
WITH recent_orders AS (
    SELECT * FROM orders WHERE date > $since
),
order_totals AS (
    SELECT customer_id, SUM(amount) as total
    FROM recent_orders
    GROUP BY customer_id
)
SELECT * FROM order_totals WHERE total > 1000;
```

### 4. Index-Friendly Queries

```sql
-- Use equality for indexed columns
SELECT * FROM users WHERE id = $user_id;

-- Avoid functions on indexed columns
-- Bad: WHERE LOWER(email) = 'test@example.com'
-- Good: WHERE email = 'test@example.com'
```

## Next Steps

- [Python Reference](python) - Runtime API
- [DuckDB Documentation](https://duckdb.org/docs/sql/introduction) - Full SQL reference
- [Tutorials](/tutorials) - SQL endpoint examples
