---
title: "SQL Endpoints Tutorial"
description: "Build data query tools with SQL. Learn parameter binding, complex queries, aggregations, and DuckDB features."
sidebar:
  order: 3
---

> **Related Topics:** [Type System](/concepts/type-system) (parameter types) | [DuckDB Integration](/integrations/duckdb) (extensions, features) | [dbt Integration](/integrations/dbt) (data modeling) | [SQL Reference](/reference/sql) (built-in functions)

SQL endpoints are ideal for data queries and aggregations. In this tutorial, you'll learn to build increasingly complex SQL tools, from simple queries to sophisticated analytics.

## Goal

Build SQL tools that:
- Query data with parameters
- Perform aggregations and joins
- Use DuckDB's analytical features
- Read from various data sources

## Prerequisites

- Completed the [Hello World Tutorial](/tutorials/hello-world)
- Basic SQL knowledge
- A project directory with `mxcp init`

## Step 1: Simple Query with Parameters

Create a tool that fetches user data by ID.

**Create sample data** (`sql/setup.sql`):
```sql
-- Run this manually to set up test data
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    email VARCHAR,
    department VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO users (id, name, email, department) VALUES
    (1, 'Alice Smith', 'alice@example.com', 'Engineering'),
    (2, 'Bob Johnson', 'bob@example.com', 'Sales'),
    (3, 'Carol Williams', 'carol@example.com', 'Engineering'),
    (4, 'David Brown', 'david@example.com', 'Marketing');
```

Initialize the database:
```bash
mxcp query --file sql/setup.sql
```

**Tool definition** (`tools/get-user.yml`):
```yaml
mxcp: 1
tool:
  name: get_user
  description: Get user information by ID
  parameters:
    - name: user_id
      type: integer
      description: User's unique identifier
      minimum: 1
      examples: [1, 2, 3]

  return:
    type: object
    properties:
      id:
        type: integer
      name:
        type: string
      email:
        type: string
      department:
        type: string

  source:
    file: ../sql/get-user.sql

  tests:
    - name: get_alice
      arguments:
        - key: user_id
          value: 1
      result_contains:
        name: "Alice Smith"
```

**SQL implementation** (`sql/get-user.sql`):
```sql
SELECT
    id,
    name,
    email,
    department
FROM users
WHERE id = $user_id
```

Test it:
```bash
mxcp run tool get_user --param user_id=1
```

## Step 2: Filtering with Multiple Parameters

Create a tool that searches users with filters.

**Tool definition** (`tools/search-users.yml`):
```yaml
mxcp: 1
tool:
  name: search_users
  description: Search users by department and name pattern
  parameters:
    - name: department
      type: string
      description: Department to filter by (Engineering, Sales, Marketing, HR)
      default: null

    - name: name_pattern
      type: string
      description: Name pattern to search (case insensitive)
      default: "%"

    - name: limit
      type: integer
      description: Maximum number of results
      minimum: 1
      maximum: 100
      default: 10

  return:
    type: array
    items:
      type: object
      properties:
        id:
          type: integer
        name:
          type: string
        department:
          type: string

  source:
    file: ../sql/search-users.sql
```

**SQL implementation** (`sql/search-users.sql`):
```sql
SELECT
    id,
    name,
    department
FROM users
WHERE
    (department = $department OR $department IS NULL)
    AND name ILIKE $name_pattern
ORDER BY name
LIMIT $limit
```

Test different filters:
```bash
# All Engineering users
mxcp run tool search_users --param department=Engineering

# Users with 'a' in name
mxcp run tool search_users --param name_pattern='%a%'

# Combined filters
mxcp run tool search_users --param department=Engineering --param name_pattern='%a%'
```

## Step 3: Aggregations

Create a tool that generates department statistics.

**Tool definition** (`tools/department-stats.yml`):
```yaml
mxcp: 1
tool:
  name: department_stats
  description: Get statistics by department
  parameters:
    - name: department
      type: string
      description: Specific department (optional, omit for all)
      default: null

  return:
    type: array
    items:
      type: object
      properties:
        department:
          type: string
        user_count:
          type: integer
        emails_configured:
          type: integer

  source:
    file: ../sql/department-stats.sql
```

**SQL implementation** (`sql/department-stats.sql`):
```sql
SELECT
    department,
    COUNT(*) AS user_count,
    COUNT(email) AS emails_configured
FROM users
WHERE department = $department OR $department IS NULL
GROUP BY department
ORDER BY user_count DESC
```

Test:
```bash
mxcp run tool department_stats
mxcp run tool department_stats --param department=Engineering
```

## Step 4: Joins and Complex Queries

Add orders data and create analytics tools.

**Add orders table** (`sql/setup-orders.sql`):
```sql
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    amount DECIMAL(10,2),
    status VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO orders (id, user_id, amount, status) VALUES
    (1, 1, 150.00, 'completed'),
    (2, 1, 75.50, 'completed'),
    (3, 2, 200.00, 'pending'),
    (4, 2, 50.00, 'completed'),
    (5, 3, 300.00, 'completed');
```

Initialize:
```bash
mxcp query --file sql/setup-orders.sql
```

**Tool definition** (`tools/user-orders.yml`):
```yaml
mxcp: 1
tool:
  name: user_orders_summary
  description: Get order summary for a user
  parameters:
    - name: user_id
      type: integer
      description: User ID
      minimum: 1

  return:
    type: object
    properties:
      user_id:
        type: integer
      user_name:
        type: string
      total_orders:
        type: integer
      total_amount:
        type: number
      average_order:
        type: number
      completed_orders:
        type: integer

  source:
    file: ../sql/user-orders.sql
```

**SQL implementation** (`sql/user-orders.sql`):
```sql
SELECT
    u.id AS user_id,
    u.name AS user_name,
    COUNT(o.id) AS total_orders,
    COALESCE(SUM(o.amount), 0) AS total_amount,
    COALESCE(AVG(o.amount), 0) AS average_order,
    COUNT(CASE WHEN o.status = 'completed' THEN 1 END) AS completed_orders
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE u.id = $user_id
GROUP BY u.id, u.name
```

Test:
```bash
mxcp run tool user_orders_summary --param user_id=1
mxcp run tool user_orders_summary --param user_id=2
```

## Step 5: Date Handling

Create a tool with date parameters.

**Tool definition** (`tools/orders-by-date.yml`):
```yaml
mxcp: 1
tool:
  name: orders_by_date_range
  description: Get orders within a date range
  parameters:
    - name: start_date
      type: string
      format: date
      description: Start date (YYYY-MM-DD)
      examples: ["2024-01-01"]

    - name: end_date
      type: string
      format: date
      description: End date (YYYY-MM-DD)
      examples: ["2024-12-31"]

    - name: status
      type: string
      description: Filter by status
      enum: ["pending", "completed", "cancelled"]
      default: null

  return:
    type: array
    items:
      type: object
      properties:
        order_id:
          type: integer
        user_name:
          type: string
        amount:
          type: number
        status:
          type: string
        created_at:
          type: string
          format: date-time

  source:
    file: ../sql/orders-by-date.sql
```

**SQL implementation** (`sql/orders-by-date.sql`):
```sql
SELECT
    o.id AS order_id,
    u.name AS user_name,
    o.amount,
    o.status,
    o.created_at
FROM orders o
JOIN users u ON o.user_id = u.id
WHERE
    o.created_at >= $start_date::DATE
    AND o.created_at < ($end_date::DATE + INTERVAL '1 day')
    AND (o.status = $status OR $status IS NULL)
ORDER BY o.created_at DESC
```

## Step 6: Reading External Data

DuckDB can read data directly from files and URLs.

**Tool definition** (`tools/read-csv.yml`):
```yaml
mxcp: 1
tool:
  name: analyze_csv
  description: Analyze a CSV file
  parameters:
    - name: file_path
      type: string
      description: Path to CSV file
      examples: ["data/sales.csv"]

    - name: column
      type: string
      description: Column to aggregate
      examples: ["amount", "quantity"]

  return:
    type: object
    properties:
      row_count:
        type: integer
      sum:
        type: number
      average:
        type: number
      min:
        type: number
      max:
        type: number

  source:
    code: |
      SELECT
          COUNT(*) AS row_count,
          SUM(CAST(column_value AS DOUBLE)) AS sum,
          AVG(CAST(column_value AS DOUBLE)) AS average,
          MIN(CAST(column_value AS DOUBLE)) AS min,
          MAX(CAST(column_value AS DOUBLE)) AS max
      FROM (
          SELECT $column AS column_value
          FROM read_csv_auto($file_path)
      )
```

**Reading from URLs** (requires `httpfs` extension):
```yaml
# In mxcp-site.yml
extensions:
  - httpfs
```

```sql
SELECT *
FROM read_csv_auto('https://example.com/data.csv')
WHERE date >= $start_date
```

## Step 7: Window Functions

Create analytics with window functions.

**Tool definition** (`tools/user-ranking.yml`):
```yaml
mxcp: 1
tool:
  name: user_spending_ranking
  description: Rank users by total spending
  parameters:
    - name: top_n
      type: integer
      description: Number of top users to return
      minimum: 1
      maximum: 100
      default: 10

  return:
    type: array
    items:
      type: object
      properties:
        rank:
          type: integer
        user_name:
          type: string
        total_spent:
          type: number
        order_count:
          type: integer

  source:
    file: ../sql/user-ranking.sql
```

**SQL implementation** (`sql/user-ranking.sql`):
```sql
WITH user_totals AS (
    SELECT
        u.name AS user_name,
        COALESCE(SUM(o.amount), 0) AS total_spent,
        COUNT(o.id) AS order_count
    FROM users u
    LEFT JOIN orders o ON u.id = o.user_id AND o.status = 'completed'
    GROUP BY u.id, u.name
)
SELECT
    ROW_NUMBER() OVER (ORDER BY total_spent DESC) AS rank,
    user_name,
    total_spent,
    order_count
FROM user_totals
ORDER BY rank
LIMIT $top_n
```

## Verification

Run all validations:

```bash
# Validate all tools
mxcp validate

# Run all tests
mxcp test

# List available tools
mxcp list
```

## Best Practices

### 1. Use Named Parameters
Always use `$param_name` for parameters:
```sql
-- Good
WHERE id = $user_id

-- Avoid (not supported)
WHERE id = ?
```

### 2. Handle NULL Parameters
Use `OR $param IS NULL` for optional filters:
```sql
WHERE department = $department OR $department IS NULL
```

### 3. Use COALESCE for Defaults
Handle missing data gracefully:
```sql
COALESCE(SUM(amount), 0) AS total
```

### 4. Type Cast When Needed
Ensure types match:
```sql
WHERE created_at >= $start_date::DATE
```

### 5. Limit Results
Always limit unbounded queries:
```sql
ORDER BY created_at DESC
LIMIT $limit
```

## Next Steps

- [Python Endpoints Tutorial](/tutorials/python-endpoints) - Add Python logic
- [dbt Integration](/integrations/dbt) - Use dbt for data modeling
- [SQL Reference](/reference/sql) - Complete SQL features
