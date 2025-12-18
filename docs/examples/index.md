---
title: "Examples"
description: "Complete MXCP examples for common use cases. Customer service, analytics, data management, and enterprise patterns."
sidebar:
  order: 1
---

Learn MXCP through complete, working examples that demonstrate real-world patterns and best practices. Each example is a fully functional project you can run locally or use as a starting point for your own applications.

## Getting Started with Examples

Each example follows the same structure and can be run with these commands:

```bash
# Clone or create the project structure
# Initialize the database
mxcp query --file sql/setup.sql

# Validate configuration
mxcp validate

# Run tests
mxcp test

# Start the server
mxcp serve
```

### Prerequisites

Before running any example, ensure you have:

- Python 3.10+ installed
- MXCP installed (`pip install mxcp`)
- An AI client that supports MCP (Claude Code, Claude Desktop, or any MCP-compatible application)

New to MXCP? Start with the [Quickstart guide](/quickstart/) to get up and running in minutes.

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

```yaml title="tools/hello.yml"
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

```yaml title="resources/user.yml"
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

```yaml title="tools/analyze.yml"
mxcp: 1
tool:
  name: analyze_text
  description: Analyze text sentiment
  language: python
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
```

```python title="python/analyze.py"
def analyze_text(text: str) -> dict:
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

```yaml title="tools/delete_user.yml"
mxcp: 1
tool:
  name: delete_user
  description: Delete a user (admin only)
  language: python
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
    file: ../python/delete_user.py
```

```python title="python/delete_user.py"
from mxcp.runtime import db

def delete_user(user_id: int) -> dict:
    """Delete a user by ID."""
    db.execute("DELETE FROM users WHERE id = $id", {"id": user_id})
    return {"deleted": True, "user_id": user_id}
```

### Tool with Filtering

```yaml title="tools/list_users.yml"
mxcp: 1
tool:
  name: list_users
  description: List users with filtering
  parameters:
    - name: department
      type: string
      default: null
      description: Filter by department name
    - name: status
      type: string
      enum: ["active", "inactive", "all"]
      default: "all"
      description: Filter by user status
    - name: limit
      type: integer
      default: 10
      maximum: 100
      description: Maximum number of users to return
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

```yaml title="prompts/summarize.yml"
mxcp: 1
prompt:
  name: summarize
  description: Create a summary of content
  parameters:
    - name: content
      type: string
      description: Content to summarize
    - name: style
      type: string
      enum: ["brief", "detailed", "bullet"]
      default: "brief"
      description: Summary style
  messages:
    - role: user
      type: text
      prompt: |
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

External API calls use Python endpoints for proper secret handling:

```yaml title="tools/weather.yml"
mxcp: 1
tool:
  name: get_weather
  description: Get current weather for a city
  language: python
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
    file: ../python/weather.py
```

```python title="python/weather.py"
from mxcp.runtime import config
import urllib.request
import json

def get_weather(city: str) -> dict:
    # Get API key from user config secrets
    secret = config.get_secret("openweather")
    if not secret:
        return {"city": city, "temperature": 0, "conditions": "API key not configured"}

    api_key = secret.get("api_key", "")
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}"

    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read())

    return {
        "city": city,
        "temperature": data["main"]["temp"],
        "conditions": data["weather"][0]["description"]
    }
```

### Async Operations

For concurrent API calls or I/O operations:

```yaml title="tools/batch_lookup.yml"
mxcp: 1
tool:
  name: batch_lookup
  description: Look up multiple items concurrently
  language: python
  parameters:
    - name: ids
      type: array
      items:
        type: integer
      description: IDs to look up
  return:
    type: array
    items:
      type: object
  source:
    file: ../python/batch.py
```

```python title="python/batch.py"
import asyncio
from mxcp.runtime import db

async def batch_lookup(ids: list[int]) -> list[dict]:
    """Look up multiple items concurrently."""

    async def lookup_one(item_id: int) -> dict:
        # Simulate async operation
        await asyncio.sleep(0.1)
        results = db.execute(
            "SELECT * FROM items WHERE id = $id",
            {"id": item_id}
        )
        return results[0] if results else {"id": item_id, "error": "Not found"}

    # Process all IDs concurrently
    return await asyncio.gather(*[lookup_one(id) for id in ids])
```

### Lifecycle Hooks

Initialize resources (ML models, connections) at startup:

```yaml title="tools/predict.yml"
mxcp: 1
tool:
  name: predict_sentiment
  description: Predict sentiment using ML model
  language: python
  parameters:
    - name: text
      type: string
      description: Text to analyze for sentiment
  return:
    type: object
    properties:
      sentiment:
        type: string
      confidence:
        type: number
  source:
    file: ../python/ml.py
```

```python title="python/ml.py"
from mxcp.runtime import on_init, on_shutdown

# Global model reference
model = None

@on_init
def load_model():
    """Load ML model when server starts."""
    global model
    # model = load_your_model_here()
    model = {"loaded": True}  # Placeholder
    print("ML model loaded")

@on_shutdown
def cleanup():
    """Clean up when server stops."""
    global model
    model = None
    print("ML model unloaded")

def predict_sentiment(text: str) -> dict:
    """Predict sentiment using the loaded model."""
    if not model:
        return {"sentiment": "unknown", "confidence": 0}

    # Use model for prediction (placeholder logic)
    positive_words = ["good", "great", "excellent", "love"]
    negative_words = ["bad", "terrible", "hate", "awful"]

    text_lower = text.lower()
    pos = sum(1 for w in positive_words if w in text_lower)
    neg = sum(1 for w in negative_words if w in text_lower)

    if pos > neg:
        return {"sentiment": "positive", "confidence": 0.8}
    elif neg > pos:
        return {"sentiment": "negative", "confidence": 0.8}
    return {"sentiment": "neutral", "confidence": 0.5}
```

### Test-Driven Endpoint

```yaml title="tools/calculate.yml"
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
