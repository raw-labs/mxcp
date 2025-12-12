---
title: "Analytics Example"
description: "Complete MXCP example for business analytics. Sales reports, time-series analysis, aggregations, and real-time dashboards."
sidebar:
  order: 3
---

This example demonstrates a business analytics MXCP project with sales reports, metrics, and time-series analysis.

## Project Structure

```
analytics/
├── mxcp-site.yml
├── tools/
│   ├── sales_report.yml
│   ├── revenue_metrics.yml
│   ├── product_performance.yml
│   └── trend_analysis.yml
├── resources/
│   ├── dashboard.yml
│   └── kpis.yml
├── sql/
│   ├── setup.sql
│   └── queries/
│       ├── sales_summary.sql
│       └── trends.sql
└── models/
    ├── staging/
    │   └── stg_sales.sql
    └── marts/
        └── sales_metrics.sql
```

## Configuration

```yaml
# mxcp-site.yml
mxcp: 1
project: analytics
profile: default

profiles:
  default:
    duckdb:
      path: data/analytics.duckdb

dbt:
  enabled: true

extensions:
  - json
  - parquet
```

## Schema Setup

```sql
-- sql/setup.sql
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
    sale_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    (7, 3, 8, 199.99, 1599.92, 'South', '2024-01-21'),
    (8, 1, 20, 99.99, 1999.80, 'North', '2024-02-01'),
    (9, 4, 100, 29.99, 2999.00, 'West', '2024-02-02');
```

## Tools

### Sales Report

```yaml
# tools/sales_report.yml
mxcp: 1
tool:
  name: sales_report
  description: Generate sales report for a date range
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
      enum: ["day", "week", "month", "region", "category"]
      default: "day"
      description: Grouping dimension

  return:
    type: object
    properties:
      summary:
        type: object
        properties:
          total_revenue:
            type: number
          total_orders:
            type: integer
          avg_order_value:
            type: number
      breakdown:
        type: array
        items:
          type: object

  source:
    code: |
      WITH filtered_sales AS (
        SELECT s.*, p.name as product_name, p.category
        FROM sales s
        JOIN products p ON s.product_id = p.id
        WHERE s.sale_date >= $start_date::DATE
          AND s.sale_date <= $end_date::DATE
      ),
      summary AS (
        SELECT
          ROUND(SUM(total), 2) as total_revenue,
          COUNT(*) as total_orders,
          ROUND(AVG(total), 2) as avg_order_value
        FROM filtered_sales
      ),
      breakdown AS (
        SELECT
          CASE $group_by
            WHEN 'day' THEN strftime(sale_date, '%Y-%m-%d')
            WHEN 'week' THEN strftime(sale_date, '%Y-W%W')
            WHEN 'month' THEN strftime(sale_date, '%Y-%m')
            WHEN 'region' THEN region
            WHEN 'category' THEN category
          END as dimension,
          ROUND(SUM(total), 2) as revenue,
          COUNT(*) as orders,
          SUM(quantity) as units
        FROM filtered_sales
        GROUP BY 1
        ORDER BY 1
      )
      SELECT json_object(
        'summary', (SELECT json_object(
          'total_revenue', total_revenue,
          'total_orders', total_orders,
          'avg_order_value', avg_order_value
        ) FROM summary),
        'breakdown', (SELECT json_group_array(json_object(
          'dimension', dimension,
          'revenue', revenue,
          'orders', orders,
          'units', units
        )) FROM breakdown)
      ) as result

  tests:
    - name: monthly_report
      arguments:
        - key: start_date
          value: "2024-01-01"
        - key: end_date
          value: "2024-01-31"
        - key: group_by
          value: "day"
      result_contains:
        summary:
          total_orders: 7
```

### Revenue Metrics

```yaml
# tools/revenue_metrics.yml
mxcp: 1
tool:
  name: revenue_metrics
  description: Get key revenue metrics and KPIs
  tags: ["revenue", "kpis"]
  annotations:
    readOnlyHint: true

  parameters:
    - name: period
      type: string
      enum: ["today", "week", "month", "quarter", "year"]
      default: "month"
      description: Time period for metrics

  return:
    type: object
    properties:
      period:
        type: string
      revenue:
        type: number
      revenue_change:
        type: number
        description: Percentage change from previous period
      orders:
        type: integer
      avg_order_value:
        type: number
      top_product:
        type: string
      top_region:
        type: string

  source:
    code: |
      WITH period_bounds AS (
        SELECT
          CASE $period
            WHEN 'today' THEN CURRENT_DATE
            WHEN 'week' THEN CURRENT_DATE - INTERVAL '7 days'
            WHEN 'month' THEN CURRENT_DATE - INTERVAL '30 days'
            WHEN 'quarter' THEN CURRENT_DATE - INTERVAL '90 days'
            WHEN 'year' THEN CURRENT_DATE - INTERVAL '365 days'
          END as start_date,
          CURRENT_DATE as end_date
      ),
      current_period AS (
        SELECT
          ROUND(SUM(s.total), 2) as revenue,
          COUNT(*) as orders,
          ROUND(AVG(s.total), 2) as avg_order_value
        FROM sales s, period_bounds pb
        WHERE s.sale_date >= pb.start_date
      ),
      top_product AS (
        SELECT p.name
        FROM sales s
        JOIN products p ON s.product_id = p.id, period_bounds pb
        WHERE s.sale_date >= pb.start_date
        GROUP BY p.name
        ORDER BY SUM(s.total) DESC
        LIMIT 1
      ),
      top_region AS (
        SELECT region
        FROM sales s, period_bounds pb
        WHERE s.sale_date >= pb.start_date
        GROUP BY region
        ORDER BY SUM(total) DESC
        LIMIT 1
      )
      SELECT
        $period as period,
        cp.revenue,
        0.0 as revenue_change,
        cp.orders,
        cp.avg_order_value,
        (SELECT name FROM top_product) as top_product,
        (SELECT region FROM top_region) as top_region
      FROM current_period cp
```

### Product Performance

```yaml
# tools/product_performance.yml
mxcp: 1
tool:
  name: product_performance
  description: Analyze product sales performance
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
      description: Number of products to return

  return:
    type: array
    items:
      type: object
      properties:
        product_id:
          type: integer
        product_name:
          type: string
        category:
          type: string
        total_revenue:
          type: number
        units_sold:
          type: integer
        avg_price:
          type: number
        order_count:
          type: integer

  source:
    code: |
      SELECT
        p.id as product_id,
        p.name as product_name,
        p.category,
        ROUND(SUM(s.total), 2) as total_revenue,
        SUM(s.quantity) as units_sold,
        ROUND(AVG(s.unit_price), 2) as avg_price,
        COUNT(*) as order_count
      FROM products p
      LEFT JOIN sales s ON p.id = s.product_id
      WHERE $category IS NULL OR p.category = $category
      GROUP BY p.id, p.name, p.category
      ORDER BY total_revenue DESC NULLS LAST
      LIMIT $limit

  tests:
    - name: all_products
      arguments: []

    - name: filter_by_category
      arguments:
        - key: category
          value: "Hardware"
      result_contains:
        - category: "Hardware"
```

### Trend Analysis

```yaml
# tools/trend_analysis.yml
mxcp: 1
tool:
  name: trend_analysis
  description: Analyze sales trends over time
  tags: ["trends", "analysis"]
  annotations:
    readOnlyHint: true

  parameters:
    - name: metric
      type: string
      enum: ["revenue", "orders", "units", "avg_order"]
      default: "revenue"
      description: Metric to analyze
    - name: granularity
      type: string
      enum: ["daily", "weekly", "monthly"]
      default: "daily"
      description: Time granularity
    - name: periods
      type: integer
      default: 30
      description: Number of periods to analyze

  return:
    type: object
    properties:
      metric:
        type: string
      granularity:
        type: string
      trend_direction:
        type: string
        enum: ["up", "down", "stable"]
      data_points:
        type: array
        items:
          type: object
          properties:
            period:
              type: string
            value:
              type: number

  source:
    file: ../sql/queries/trends.sql
```

```sql
-- sql/queries/trends.sql
WITH date_series AS (
  SELECT CASE $granularity
    WHEN 'daily' THEN generate_series(
      CURRENT_DATE - ($periods || ' days')::INTERVAL,
      CURRENT_DATE,
      '1 day'::INTERVAL
    )::DATE
    WHEN 'weekly' THEN generate_series(
      CURRENT_DATE - ($periods * 7 || ' days')::INTERVAL,
      CURRENT_DATE,
      '7 days'::INTERVAL
    )::DATE
    WHEN 'monthly' THEN generate_series(
      CURRENT_DATE - ($periods || ' months')::INTERVAL,
      CURRENT_DATE,
      '1 month'::INTERVAL
    )::DATE
  END as period_date
),
aggregated AS (
  SELECT
    CASE $granularity
      WHEN 'daily' THEN sale_date
      WHEN 'weekly' THEN date_trunc('week', sale_date)::DATE
      WHEN 'monthly' THEN date_trunc('month', sale_date)::DATE
    END as period_date,
    CASE $metric
      WHEN 'revenue' THEN SUM(total)
      WHEN 'orders' THEN COUNT(*)
      WHEN 'units' THEN SUM(quantity)
      WHEN 'avg_order' THEN AVG(total)
    END as value
  FROM sales
  GROUP BY 1
),
data_points AS (
  SELECT
    strftime(ds.period_date, '%Y-%m-%d') as period,
    COALESCE(a.value, 0) as value
  FROM date_series ds
  LEFT JOIN aggregated a ON ds.period_date = a.period_date
  ORDER BY ds.period_date
),
trend AS (
  SELECT
    CASE
      WHEN LAST(value) OVER () > FIRST(value) OVER () * 1.05 THEN 'up'
      WHEN LAST(value) OVER () < FIRST(value) OVER () * 0.95 THEN 'down'
      ELSE 'stable'
    END as direction
  FROM data_points
  LIMIT 1
)
SELECT json_object(
  'metric', $metric,
  'granularity', $granularity,
  'trend_direction', (SELECT direction FROM trend),
  'data_points', (SELECT json_group_array(json_object(
    'period', period,
    'value', ROUND(value, 2)
  )) FROM data_points)
) as result
```

## Resources

### Dashboard Resource

```yaml
# resources/dashboard.yml
mxcp: 1
resource:
  uri: analytics://dashboard
  name: Analytics Dashboard
  description: Real-time analytics dashboard data
  mimeType: application/json

  return:
    type: object
    properties:
      timestamp:
        type: string
      kpis:
        type: object
      recent_orders:
        type: array
      top_products:
        type: array

  source:
    code: |
      SELECT json_object(
        'timestamp', strftime(NOW(), '%Y-%m-%d %H:%M:%S'),
        'kpis', (
          SELECT json_object(
            'today_revenue', COALESCE(SUM(CASE WHEN sale_date = CURRENT_DATE THEN total END), 0),
            'mtd_revenue', COALESCE(SUM(CASE WHEN sale_date >= date_trunc('month', CURRENT_DATE) THEN total END), 0),
            'today_orders', COUNT(CASE WHEN sale_date = CURRENT_DATE THEN 1 END),
            'mtd_orders', COUNT(CASE WHEN sale_date >= date_trunc('month', CURRENT_DATE) THEN 1 END)
          )
          FROM sales
        ),
        'recent_orders', (
          SELECT json_group_array(json_object(
            'id', s.id,
            'product', p.name,
            'total', s.total,
            'region', s.region
          ))
          FROM (SELECT * FROM sales ORDER BY created_at DESC LIMIT 5) s
          JOIN products p ON s.product_id = p.id
        ),
        'top_products', (
          SELECT json_group_array(json_object(
            'name', p.name,
            'revenue', ROUND(SUM(s.total), 2)
          ))
          FROM products p
          JOIN sales s ON p.id = s.product_id
          GROUP BY p.id, p.name
          ORDER BY SUM(s.total) DESC
          LIMIT 5
        )
      ) as dashboard
```

### KPI Resource

```yaml
# resources/kpis.yml
mxcp: 1
resource:
  uri: analytics://kpis/{period}
  name: KPI Metrics
  description: Key performance indicators for a period

  parameters:
    - name: period
      type: string
      enum: ["daily", "weekly", "monthly"]

  return:
    type: object

  source:
    code: |
      SELECT json_object(
        'period', $period,
        'revenue', ROUND(SUM(total), 2),
        'orders', COUNT(*),
        'units', SUM(quantity),
        'avg_order', ROUND(AVG(total), 2)
      ) as kpis
      FROM sales
      WHERE sale_date >= CASE $period
        WHEN 'daily' THEN CURRENT_DATE
        WHEN 'weekly' THEN CURRENT_DATE - INTERVAL '7 days'
        WHEN 'monthly' THEN CURRENT_DATE - INTERVAL '30 days'
      END
```

## dbt Models

### Staging Model

```sql
-- models/staging/stg_sales.sql
{{ config(materialized='view') }}

SELECT
    s.id as sale_id,
    s.product_id,
    p.name as product_name,
    p.category,
    s.quantity,
    s.unit_price,
    s.total,
    s.region,
    s.sale_date,
    s.created_at
FROM {{ source('raw', 'sales') }} s
JOIN {{ source('raw', 'products') }} p ON s.product_id = p.id
```

### Mart Model

```sql
-- models/marts/sales_metrics.sql
{{ config(materialized='table') }}

SELECT
    DATE_TRUNC('day', sale_date) as date,
    category,
    region,
    COUNT(*) as order_count,
    SUM(quantity) as units_sold,
    ROUND(SUM(total), 2) as revenue,
    ROUND(AVG(total), 2) as avg_order_value
FROM {{ ref('stg_sales') }}
GROUP BY 1, 2, 3
```

## Running the Example

```bash
# Initialize database
mxcp query --file sql/setup.sql

# Build dbt models (if using dbt)
mxcp dbt run

# Validate endpoints
mxcp validate

# Run tests
mxcp test

# Start server
mxcp serve --transport stdio
```

## Example Queries

```bash
# Get sales report
mxcp run tool sales_report \
  --param start_date=2024-01-01 \
  --param end_date=2024-01-31 \
  --param group_by=region

# Get revenue metrics
mxcp run tool revenue_metrics --param period=month

# Analyze product performance
mxcp run tool product_performance --param category=Hardware

# Get trend analysis
mxcp run tool trend_analysis \
  --param metric=revenue \
  --param granularity=daily \
  --param periods=30
```

## Next Steps

- [Customer Service Example](customer-service) - Support tools
- [Data Management Example](data-management) - CRUD operations
- [dbt Integration](/integrations/dbt) - Data transformation
