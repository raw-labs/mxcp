---
title: "Examples"
description: "Complete MXCP examples for common use cases. Customer service, analytics, data management, and enterprise patterns."
sidebar:
  order: 1
---

Learn MXCP through complete, working examples that demonstrate real-world patterns and best practices.

## Example Projects

### [Customer Service](/examples/customer-service)
AI-powered customer support tools:
- Customer lookup and search
- Order history and tracking
- Ticket management
- Policy-protected sensitive data

### [Analytics Dashboard](/examples/analytics)
Business intelligence endpoints:
- Sales reports and metrics
- Time-series analysis
- Aggregations and rollups
- Real-time dashboards

### [Data Management](/examples/data-management)
CRUD operations and data handling:
- User management
- Document storage
- File processing
- Batch operations

## Quick Examples

### Basic Tool

```yaml
# tools/hello.yml
mxcp: 1
tool:
  name: hello
  description: Say hello to someone
  parameters:
    - name: name
      type: string
      description: Name to greet
  return:
    type: string
  source:
    code: "SELECT 'Hello, ' || $name || '!'"
```

### Resource with URI Template

```yaml
# resources/user.yml
mxcp: 1
resource:
  uri: users://{id}
  name: User Profile
  description: Get user by ID
  parameters:
    - name: id
      type: integer
      description: User ID
  return:
    type: object
    properties:
      id:
        type: integer
      name:
        type: string
      email:
        type: string
  source:
    code: |
      SELECT id, name, email
      FROM users
      WHERE id = $id
```

### Python Endpoint

```yaml
# tools/analyze.yml
mxcp: 1
tool:
  name: analyze_text
  description: Analyze text sentiment
  parameters:
    - name: text
      type: string
      description: Text to analyze
  return:
    type: object
    properties:
      sentiment:
        type: string
      confidence:
        type: number
  source:
    file: ../python/analyze.py
    function: analyze
```

```python
# python/analyze.py
from mxcp.runtime import db

def analyze(text: str) -> dict:
    # Simple sentiment analysis
    positive_words = ["good", "great", "excellent", "happy"]
    negative_words = ["bad", "poor", "terrible", "sad"]

    text_lower = text.lower()
    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)

    if pos_count > neg_count:
        sentiment = "positive"
        confidence = pos_count / (pos_count + neg_count + 1)
    elif neg_count > pos_count:
        sentiment = "negative"
        confidence = neg_count / (pos_count + neg_count + 1)
    else:
        sentiment = "neutral"
        confidence = 0.5

    return {"sentiment": sentiment, "confidence": confidence}
```

### Tool with Policy

```yaml
# tools/delete_user.yml
mxcp: 1
tool:
  name: delete_user
  description: Delete a user (admin only)
  annotations:
    destructiveHint: true
  parameters:
    - name: user_id
      type: integer
      description: User ID to delete
  return:
    type: object
    properties:
      deleted:
        type: boolean
      user_id:
        type: integer
  policies:
    input:
      - condition: "user.role != 'admin'"
        action: deny
        reason: "Only admins can delete users"
  source:
    code: |
      DELETE FROM users WHERE id = $user_id
      RETURNING true as deleted, $user_id as user_id
```

### Resource with Filtering

```yaml
# resources/users.yml
mxcp: 1
resource:
  uri: users://list
  name: User List
  description: List users with filtering
  parameters:
    - name: department
      type: string
      default: null
    - name: status
      type: string
      enum: ["active", "inactive", "all"]
      default: "all"
    - name: limit
      type: integer
      default: 10
      maximum: 100
  return:
    type: array
    items:
      type: object
  source:
    code: |
      SELECT id, name, email, department, status
      FROM users
      WHERE ($department IS NULL OR department = $department)
        AND ($status = 'all' OR status = $status)
      ORDER BY name
      LIMIT $limit
```

### Prompt Template

```yaml
# prompts/summarize.yml
mxcp: 1
prompt:
  name: summarize
  description: Create a summary of content
  arguments:
    - name: content
      type: string
      description: Content to summarize
    - name: style
      type: string
      enum: ["brief", "detailed", "bullet"]
      default: "brief"
  template: |
    Please summarize the following content in a {{style}} style:

    {{content}}

    {% if style == "brief" %}
    Keep the summary to 2-3 sentences.
    {% elif style == "bullet" %}
    Use bullet points for key takeaways.
    {% else %}
    Provide a comprehensive summary with context.
    {% endif %}
```

### External API Integration

```yaml
# tools/weather.yml
mxcp: 1
tool:
  name: get_weather
  description: Get current weather for a city
  parameters:
    - name: city
      type: string
      description: City name
  return:
    type: object
    properties:
      city:
        type: string
      temperature:
        type: number
      conditions:
        type: string
  source:
    code: |
      SELECT
        $city as city,
        main.temp as temperature,
        weather[1].description as conditions
      FROM read_json_auto(
        'https://api.openweathermap.org/data/2.5/weather?q=' || $city || '&appid=' || get_secret('openweather')
      )
```

### Test-Driven Endpoint

```yaml
# tools/calculate.yml
mxcp: 1
tool:
  name: calculate_total
  description: Calculate order total with tax
  parameters:
    - name: subtotal
      type: number
      description: Order subtotal
    - name: tax_rate
      type: number
      default: 0.08
      description: Tax rate (default 8%)
  return:
    type: object
    properties:
      subtotal:
        type: number
      tax:
        type: number
      total:
        type: number
  source:
    code: |
      SELECT
        $subtotal as subtotal,
        ROUND($subtotal * $tax_rate, 2) as tax,
        ROUND($subtotal * (1 + $tax_rate), 2) as total

  tests:
    - name: basic_calculation
      arguments:
        - key: subtotal
          value: 100.00
      result_contains:
        subtotal: 100.0
        tax: 8.0
        total: 108.0

    - name: custom_tax_rate
      arguments:
        - key: subtotal
          value: 100.00
        - key: tax_rate
          value: 0.1
      result_contains:
        total: 110.0
```

## Common Patterns

### Pagination

```yaml
parameters:
  - name: page
    type: integer
    default: 1
    minimum: 1
  - name: page_size
    type: integer
    default: 20
    maximum: 100

source:
  code: |
    SELECT *
    FROM items
    ORDER BY created_at DESC
    LIMIT $page_size
    OFFSET ($page - 1) * $page_size
```

### Search

```yaml
parameters:
  - name: query
    type: string
    description: Search term

source:
  code: |
    SELECT *
    FROM products
    WHERE name ILIKE '%' || $query || '%'
       OR description ILIKE '%' || $query || '%'
    ORDER BY
      CASE WHEN name ILIKE $query || '%' THEN 0 ELSE 1 END,
      name
    LIMIT 20
```

### Date Filtering

```yaml
parameters:
  - name: start_date
    type: string
    format: date
  - name: end_date
    type: string
    format: date

source:
  code: |
    SELECT *
    FROM events
    WHERE event_date >= $start_date::DATE
      AND event_date <= $end_date::DATE
    ORDER BY event_date
```

### Conditional Joins

```yaml
source:
  code: |
    SELECT
      o.id,
      o.total,
      c.name as customer_name,
      COALESCE(s.name, 'Unshipped') as shipment_status
    FROM orders o
    JOIN customers c ON o.customer_id = c.id
    LEFT JOIN shipments s ON o.id = s.order_id
    WHERE o.id = $order_id
```

### Aggregations

```yaml
source:
  code: |
    SELECT
      department,
      COUNT(*) as employee_count,
      AVG(salary) as avg_salary,
      MIN(salary) as min_salary,
      MAX(salary) as max_salary
    FROM employees
    WHERE status = 'active'
    GROUP BY department
    ORDER BY employee_count DESC
```

## Project Structure Example

```
my-mxcp-project/
├── mxcp-site.yml
├── tools/
│   ├── user_lookup.yml
│   ├── order_search.yml
│   └── report_generator.yml
├── resources/
│   ├── user.yml
│   ├── order.yml
│   └── product.yml
├── prompts/
│   ├── summarize.yml
│   └── analyze.yml
├── python/
│   ├── analytics.py
│   └── integrations.py
├── sql/
│   ├── complex_query.sql
│   └── report_template.sql
├── evals/
│   └── safety-tests.evals.yml
└── models/
    └── dbt models...
```

## Next Steps

- [Customer Service Example](/examples/customer-service)
- [Analytics Example](/examples/analytics)
- [Data Management Example](/examples/data-management)
- [Tutorials](/tutorials) - Step-by-step guides
