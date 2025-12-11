---
title: "SQL Reference"
description: "Quick reference for SQL in MXCP including DuckDB syntax and built-in authentication functions."
sidebar:
  order: 4
---

MXCP uses DuckDB SQL syntax with additional built-in functions for authentication and access control. This reference provides a quick lookup of SQL capabilities in MXCP.

## DuckDB SQL Syntax

MXCP endpoints use [DuckDB SQL](https://duckdb.org/docs/sql/introduction), which extends PostgreSQL syntax with analytical features. Key highlights:

- **PostgreSQL Compatible**: Most PostgreSQL queries work unchanged
- **Column-Store Engine**: Optimized for analytical queries
- **Rich Type System**: Supports arrays, structs, maps, and more
- **Window Functions**: Full support for analytical window functions
- **CTEs**: Common Table Expressions with recursive support

## MXCP Built-in Functions

When authentication is enabled, MXCP provides these SQL functions:

### User Authentication Functions

| Function | Returns | Description |
|----------|---------|-------------|
| `get_username()` | VARCHAR | Authenticated user's username |
| `get_user_email()` | VARCHAR | User's email address |
| `get_user_provider()` | VARCHAR | OAuth provider name (e.g., 'github', 'atlassian') |
| `get_user_external_token()` | VARCHAR | User's OAuth token from external provider |

**Note**: All functions return empty string (`""`) when authentication is disabled or user is not authenticated.

### Usage Examples

```sql
-- Access user's GitHub repositories
SELECT *
FROM read_json_auto(
    'https://api.github.com/user/repos',
    headers = MAP {
        'Authorization': 'Bearer ' || get_user_external_token(),
        'User-Agent': 'MXCP-' || get_username()
    }
);

-- Filter data by authenticated user
SELECT * FROM projects 
WHERE owner = get_username();

-- Audit logging
INSERT INTO audit_log (user, action, timestamp)
VALUES (get_username(), 'query_executed', NOW());
```

### Request Header Functions

Requests coming through HTTP transport expose their headers to DuckDB so you can audit or forward them without extra plumbing.

| Function | Returns | Description |
|----------|---------|-------------|
| `get_request_header(text name)` | VARCHAR | Value of the specified HTTP request header (empty string if missing) |
| `get_request_headers_json()` | VARCHAR | JSON object containing all request headers |

```sql
-- Attach the incoming Authorization header to an outbound API call
SELECT http_post(
    'https://example.internal/audit',
    headers := map {'Authorization': get_request_header('Authorization')},
    body := json('{"status": "ok"}')
);
```

## Common DuckDB Extensions

MXCP typically loads these DuckDB extensions:

- **httpfs**: Read data from HTTP/S3 endpoints
- **json**: JSON parsing and manipulation
- **parquet**: Read/write Parquet files
- **excel**: Read Excel files
- **postgres**: Connect to PostgreSQL databases

## Parameter Binding

Use named parameters with `$` prefix:

```sql
-- In SQL file
SELECT * FROM users 
WHERE age > $min_age 
  AND city = $city;
```

## See Also

- [DuckDB Documentation](https://duckdb.org/docs/sql/introduction)
- [Authentication Guide](../guides/authentication)
- [SQL Endpoints](../features/overview) 
