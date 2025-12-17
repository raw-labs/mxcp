---
title: "Analytics Example"
description: "Build a sales analytics system with MXCP. Reports, dashboards, KPIs, and AI-assisted analysis."
sidebar:
  order: 3
---

Build a sales analytics system that lets AI assistants generate reports, analyze products, and access real-time dashboards.

## What You'll Learn

- Creating parameterized report tools
- Building dashboard resources
- When to use tools vs resources for analytics
- AI-assisted data analysis with prompts

## Project Structure

```
analytics/
├── mxcp-site.yml
├── sql/
│   ├── setup.sql
│   └── sales_report.sql
├── tools/
│   ├── sales_report.yml
│   ├── product_performance.yml
│   └── daily_trends.yml
├── resources/
│   ├── dashboard.yml
│   └── kpis.yml
└── prompts/
    └── analyst.yml
```

## Configuration

```yaml title="mxcp-site.yml"
mxcp: 1
project: analytics
profile: default

profiles:
  default:
    duckdb:
      path: data/analytics.duckdb

extensions:
  - json
```

## Schema Setup

```sql title="sql/setup.sql"
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    price DECIMAL(10, 2) NOT NULL
);

CREATE TABLE sales (
    id INTEGER PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    total DECIMAL(10, 2) NOT NULL,
    region VARCHAR NOT NULL,
    sale_date DATE NOT NULL
);

-- Sample data
INSERT INTO products (id, name, category, price) VALUES
    (1, 'Widget Pro', 'Hardware', 99.99),
    (2, 'Widget Basic', 'Hardware', 49.99),
    (3, 'Software Suite', 'Software', 199.99),
    (4, 'Support Plan', 'Services', 29.99);

INSERT INTO sales (id, product_id, quantity, unit_price, total, region, sale_date) VALUES
    (1, 1, 10, 99.99, 999.90, 'North', '2024-01-15'),
    (2, 2, 25, 49.99, 1249.75, 'South', '2024-01-16'),
    (3, 3, 5, 199.99, 999.95, 'East', '2024-01-17'),
    (4, 1, 15, 99.99, 1499.85, 'West', '2024-01-18'),
    (5, 4, 50, 29.99, 1499.50, 'North', '2024-01-19'),
    (6, 2, 30, 49.99, 1499.70, 'East', '2024-01-20'),
    (7, 3, 8, 199.99, 1599.92, 'South', '2024-01-21');
```

## Tools vs Resources for Analytics

| Pattern | Type | Example | Why |
|---------|------|---------|-----|
| Reports with date ranges | **Tool** | Sales report | Requires input parameters |
| Current state data | **Resource** | Dashboard | No parameters, always current |
| Parameterized lookups | **Resource** | KPIs by period | URI-based access pattern |

**Rule of thumb:** If users need to specify *what* data they want, use a tool. If they're accessing a *known data point*, use a resource.

## Tools

### Sales Report

Generate sales reports with flexible grouping.

```yaml title="tools/sales_report.yml"
mxcp: 1
tool:
  name: sales_report
  description: Generate sales report for a date range, grouped by dimension
  tags: ["sales", "reports"]
  annotations:
    readOnlyHint: true

  parameters:
    - name: start_date
      type: string
      format: date
      description: Start date (YYYY-MM-DD)
    - name: end_date
      type: string
      format: date
      description: End date (YYYY-MM-DD)
    - name: group_by
      type: string
      enum: ["day", "region", "category"]
      default: "day"
      description: How to group results

  return:
    type: array
    items:
      type: object
      properties:
        dimension:
          type: string
        revenue:
          type: number
        orders:
          type: integer
        units:
          type: number

  source:
    file: ../sql/sales_report.sql

  tests:
    - name: january_report
      arguments:
        - key: start_date
          value: "2024-01-01"
        - key: end_date
          value: "2024-01-31"
      result_length: 7

    - name: group_by_region
      arguments:
        - key: start_date
          value: "2024-01-01"
        - key: end_date
          value: "2024-01-31"
        - key: group_by
          value: "region"
      result_contains_item:
        dimension: "North"
```

```sql title="sql/sales_report.sql"
SELECT
  CASE $group_by
    WHEN 'day' THEN strftime(sale_date, '%Y-%m-%d')
    WHEN 'region' THEN region
    WHEN 'category' THEN p.category
  END as dimension,
  ROUND(SUM(s.total), 2) as revenue,
  COUNT(*) as orders,
  SUM(s.quantity) as units
FROM sales s
JOIN products p ON s.product_id = p.id
WHERE s.sale_date >= $start_date::DATE
  AND s.sale_date <= $end_date::DATE
GROUP BY 1
ORDER BY revenue DESC
```

### Product Performance

Analyze which products are performing best.

```yaml title="tools/product_performance.yml"
mxcp: 1
tool:
  name: product_performance
  description: Analyze product sales performance, optionally filtered by category
  tags: ["products", "analysis"]
  annotations:
    readOnlyHint: true

  parameters:
    - name: category
      type: string
      default: null
      description: Filter by category (optional)
    - name: limit
      type: integer
      default: 10
      minimum: 1
      maximum: 100
      description: Number of products to return

  return:
    type: array
    items:
      type: object
      properties:
        product_name:
          type: string
        category:
          type: string
        total_revenue:
          type: number
        units_sold:
          type: number

  source:
    code: |
      SELECT
        p.name as product_name,
        p.category,
        ROUND(COALESCE(SUM(s.total), 0), 2) as total_revenue,
        COALESCE(SUM(s.quantity), 0) as units_sold
      FROM products p
      LEFT JOIN sales s ON p.id = s.product_id
      WHERE $category IS NULL OR p.category = $category
      GROUP BY p.id, p.name, p.category
      ORDER BY total_revenue DESC
      LIMIT $limit

  tests:
    - name: all_products
      arguments: []
      result_length: 4

    - name: hardware_only
      arguments:
        - key: category
          value: "Hardware"
      result_contains_item:
        category: "Hardware"
      result_length: 2
```

## Resources

### Dashboard

Real-time dashboard data. No parameters needed - always returns current state.

```yaml title="resources/dashboard.yml"
mxcp: 1
resource:
  uri: analytics://dashboard
  name: Analytics Dashboard
  description: Current sales metrics and recent activity

  return:
    type: object
    properties:
      total_revenue:
        type: number
      total_orders:
        type: integer
      avg_order_value:
        type: number
      top_region:
        type: string

  source:
    code: |
      SELECT
        ROUND(SUM(total), 2) as total_revenue,
        COUNT(*) as total_orders,
        ROUND(AVG(total), 2) as avg_order_value,
        (
          SELECT region FROM sales
          GROUP BY region
          ORDER BY SUM(total) DESC
          LIMIT 1
        ) as top_region
      FROM sales

  tests:
    - name: dashboard_loads
      arguments: []
      result_contains:
        total_orders: 7
```

### KPIs by Period

Parameterized resource - access KPIs via URI pattern.

```yaml title="resources/kpis.yml"
mxcp: 1
resource:
  uri: analytics://kpis/{period}
  name: KPI Metrics
  description: Key performance indicators for daily, weekly, or monthly periods

  parameters:
    - name: period
      type: string
      enum: ["daily", "weekly", "monthly"]
      description: Time period for KPIs

  return:
    type: object
    properties:
      period:
        type: string
      revenue:
        type: number
      orders:
        type: integer

  source:
    code: |
      WITH latest AS (SELECT MAX(sale_date) as ref_date FROM sales)
      SELECT
        $period as period,
        ROUND(SUM(total), 2) as revenue,
        COUNT(*) as orders
      FROM sales, latest
      WHERE sale_date >= CASE $period
        WHEN 'daily' THEN ref_date
        WHEN 'weekly' THEN ref_date - INTERVAL '7 days'
        WHEN 'monthly' THEN ref_date - INTERVAL '30 days'
      END

  tests:
    - name: monthly_kpis
      arguments:
        - key: period
          value: "monthly"
      result_contains:
        period: "monthly"
        orders: 7
```

### Daily Trends

Time-series data showing sales by day.

```yaml title="tools/daily_trends.yml"
mxcp: 1
tool:
  name: daily_trends
  description: Get daily sales trend for a date range
  tags: ["trends", "time-series"]
  annotations:
    readOnlyHint: true

  parameters:
    - name: start_date
      type: string
      format: date
      description: Start date (YYYY-MM-DD)
    - name: end_date
      type: string
      format: date
      description: End date (YYYY-MM-DD)

  return:
    type: array
    items:
      type: object
      properties:
        date:
          type: string
        revenue:
          type: number
        orders:
          type: integer

  source:
    code: |
      SELECT
        strftime(sale_date, '%Y-%m-%d') as date,
        ROUND(SUM(total), 2) as revenue,
        COUNT(*) as orders
      FROM sales
      WHERE sale_date >= $start_date::DATE
        AND sale_date <= $end_date::DATE
      GROUP BY sale_date
      ORDER BY sale_date

  tests:
    - name: january_trend
      arguments:
        - key: start_date
          value: "2024-01-15"
        - key: end_date
          value: "2024-01-21"
      result_length: 7
```

For more advanced time-series patterns (date generation, gap filling), see [DuckDB documentation](https://duckdb.org/docs/sql/functions/timestamp).

## Prompt

Guide the AI to use analytics tools effectively.

```yaml title="prompts/analyst.yml"
mxcp: 1
prompt:
  name: analyst
  description: Sales analytics assistant

  parameters:
    - name: question
      type: string
      description: The analytics question to answer

  messages:
    - role: user
      type: text
      prompt: |
        You are a sales analytics assistant. Answer the user's question using the available tools.

        **Available tools:**
        - `sales_report`: Generate reports for date ranges, grouped by day/region/category
        - `product_performance`: See which products sell best
        - `daily_trends`: Get time-series data for trend analysis
        - `analytics://dashboard`: Get current overall metrics
        - `analytics://kpis/{period}`: Get KPIs for daily/weekly/monthly

        **Approach:**
        1. Start with the dashboard for context
        2. Use specific tools to drill down
        3. Summarize findings clearly

        **User question:** {{question}}
```

## Running the Example

```bash
# Setup
mxcp query --file sql/setup.sql
mxcp validate
mxcp test

# Try the tools
mxcp run tool sales_report \
  --param start_date=2024-01-01 \
  --param end_date=2024-01-31 \
  --param group_by=region

mxcp run tool product_performance --param category=Hardware

mxcp run tool daily_trends \
  --param start_date=2024-01-15 \
  --param end_date=2024-01-21

# Access resources
mxcp run resource analytics://dashboard
mxcp run resource "analytics://kpis/{period}" --param period=monthly

# Start server
mxcp serve
```

## Next Steps

- [Customer Service Example](/examples/customer-service) - Policies and access control
- [Data Management Example](/examples/data-management) - CRUD operations
- [dbt Integration](/integrations/dbt) - Add data transformations to this project
