---
title: "Endpoints"
description: "Learn about MXCP endpoint types: tools, resources, and prompts. How to define them, when to use each type, and best practices."
sidebar:
  order: 2
---

> **Related Topics:** [Type System](type-system) (parameter/return types) | [YAML Schema](/reference/yaml-schema) (complete field reference) | [SQL Endpoints](/tutorials/sql-endpoints) (SQL tutorial) | [Python Endpoints](/tutorials/python-endpoints) (Python tutorial)

MXCP supports three types of MCP endpoints, each serving different purposes. Understanding when to use each type helps you design better AI integrations.

## Tools

Tools are functions that AI can call to perform actions or retrieve data. They're the most common endpoint type.

### When to Use Tools
- **Data queries** - Fetch information from databases
- **Calculations** - Perform computations
- **Actions** - Create, update, or delete data
- **Integrations** - Call external APIs

### Tool Definition

```yaml
mxcp: 1
tool:
  name: get_sales_report
  description: Get sales report for a date range
  enabled: true
  tags: ["sales", "reporting"]

  annotations:
    title: "Sales Report"
    readOnlyHint: true
    destructiveHint: false
    idempotentHint: true
    openWorldHint: false

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
    - name: region
      type: string
      description: Region to filter by
      enum: ["North", "South", "East", "West"]
      default: "North"

  return:
    type: object
    description: Sales report summary
    properties:
      total_sales:
        type: number
        description: Total sales amount
      transaction_count:
        type: integer
        description: Number of transactions
      average_sale:
        type: number
        description: Average sale amount

  source:
    file: ../sql/sales_report.sql

  tests:
    - name: basic_report
      description: Test basic report generation
      arguments:
        - key: start_date
          value: "2024-01-01"
        - key: end_date
          value: "2024-01-31"
        - key: region
          value: "North"
      result_contains:
        total_sales: true
```

### Tool Annotations

Annotations help LLMs understand tool behavior:

| Annotation | Description |
|------------|-------------|
| `title` | Human-readable title |
| `readOnlyHint` | Tool doesn't modify data |
| `destructiveHint` | Tool may delete/modify data permanently |
| `idempotentHint` | Multiple calls produce same result |
| `openWorldHint` | Tool interacts with external systems |

### SQL vs Python Tools

**SQL Tools** - Best for:
- Database queries
- Data aggregations
- Simple transformations

**Python Tools** - Best for:
- Complex business logic
- External API calls
- ML model inference
- File processing

## Resources

Resources are data sources that can be read by AI. They use URI templates to identify specific data.

### When to Use Resources
- **Static data** - Configuration, reference data
- **Document access** - Read files or documents
- **Hierarchical data** - Data organized by path/ID

### Resource Definition

```yaml
mxcp: 1
resource:
  uri: "employee://{employee_id}/profile"
  description: Employee profile information
  mime_type: application/json
  tags: ["hr", "employee"]

  parameters:
    - name: employee_id
      type: string
      description: Employee ID
      examples: ["EMP001"]

  return:
    type: object
    properties:
      id:
        type: string
      name:
        type: string
      department:
        type: string
      hire_date:
        type: string
        format: date

  source:
    file: ../sql/employee_profile.sql
```

### URI Templates

Resource URIs support parameter substitution:

```
users://{user_id}           # Single parameter
orders://{customer_id}/{order_id}  # Multiple parameters
reports://sales/{year}/{month}     # Hierarchical
```

Parameters are extracted from the URI and available in your SQL or Python code.

## Prompts

Prompts are reusable message templates for AI conversations. They support Jinja2 templating.

### When to Use Prompts
- **Consistent instructions** - Standard analysis prompts
- **Complex workflows** - Multi-step conversations
- **Parameterized templates** - Dynamic prompt generation

### Prompt Definition

```yaml
mxcp: 1
prompt:
  name: data_analysis
  description: Prompt for structured data analysis
  tags: ["analysis", "reporting"]

  parameters:
    - name: data_type
      type: string
      description: Type of data to analyze
      enum: ["sales", "inventory", "customers"]
    - name: time_period
      type: string
      description: Time period for analysis
      examples: ["Q1 2024", "Last 30 days"]

  messages:
    - role: system
      type: text
      prompt: |
        You are a data analyst specializing in {{ data_type }} data.
        Provide clear, actionable insights.

    - role: user
      type: text
      prompt: |
        Analyze the {{ data_type }} data for {{ time_period }}.

        Focus on:
        1. Key trends
        2. Anomalies
        3. Recommendations
```

### Jinja2 Templating

Prompts support full Jinja2 syntax:

```yaml
prompt: |
  {% if role == "admin" %}
  You have full access to all data.
  {% else %}
  You have limited access.
  {% endif %}

  Available metrics:
  {% for metric in metrics %}
  - {{ metric }}
  {% endfor %}
```

### Message Roles

| Role | Description |
|------|-------------|
| `system` | System-level instructions |
| `user` | User message |
| `assistant` | Assistant response |

## Source Options

All endpoint types support two source options:

### Inline Code

```yaml
source:
  code: |
    SELECT *
    FROM users
    WHERE id = $user_id
```

### External File

```yaml
source:
  file: ../sql/get_user.sql
```

External files are recommended for:
- Better version control diffs
- Syntax highlighting in editors
- Reusable SQL/Python code

## Language Options

Specify the implementation language:

```yaml
# SQL (default)
language: sql
source:
  file: ../sql/query.sql

# Python
language: python
source:
  file: ../python/handler.py
```

## Enabling/Disabling Endpoints

Use `enabled` to control whether an endpoint is loaded:

```yaml
tool:
  name: experimental_tool
  enabled: false  # Won't be loaded
```

This is useful for:
- Work-in-progress endpoints
- Feature flags
- Environment-specific endpoints

## Tags

Tags help organize and categorize endpoints:

```yaml
tool:
  name: sales_report
  tags: ["sales", "reporting", "finance"]
```

Tags are useful for:
- Documentation organization
- Filtering in large projects
- Client-side categorization

## Best Practices

### Naming
- Use `snake_case` for names
- Be descriptive but concise
- Use consistent prefixes (e.g., `get_`, `create_`, `update_`)

### Descriptions
- Write clear, actionable descriptions
- Include what the tool does, not how
- Mention any side effects

### Parameters
- Provide examples for all parameters
- Use appropriate types and formats
- Set sensible defaults for optional parameters

### Return Types
- Define complete return schemas
- Mark sensitive fields appropriately
- Include descriptions for complex objects

### Testing
- Write tests for all endpoints
- Test edge cases
- Test with realistic data

## Next Steps

- [Type System](type-system) - Parameter and return type details
- [Project Structure](project-structure) - File organization
- [SQL Endpoints Tutorial](/tutorials/sql-endpoints) - Build SQL tools
- [Python Endpoints Tutorial](/tutorials/python-endpoints) - Build Python tools
