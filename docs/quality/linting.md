---
title: "Linting"
description: "Improve MXCP endpoint quality for LLM comprehension. Check descriptions, examples, and metadata best practices."
sidebar:
  order: 4
---

> **Related Topics:** [Validation](/quality/validation) (structural checks) | [Testing](/quality/testing) (functional tests) | [Endpoints](/concepts/endpoints) (definition best practices) | [Common Tasks](/reference/common-tasks#how-do-i-check-for-linting-issues) (quick how-to)

The MXCP linter checks your endpoint metadata quality, ensuring AI tools can understand and use your endpoints effectively.

## Running Linter

```bash
# Lint all endpoints
mxcp lint

# Show only warnings (skip suggestions)
mxcp lint --severity warning

# JSON output for automation
mxcp lint --json-output

# Debug mode
mxcp lint --debug
```

Note: The linter checks all endpoints at once. It does not support filtering by specific endpoint.

## What Gets Checked

### Descriptions
- Tool/resource description present and meaningful
- Parameter descriptions present
- Return type descriptions present
- Minimum description length

### Examples
- Parameters have examples
- Examples are realistic
- Multiple examples for clarity

### Tags
- Endpoints have tags
- Tags are categorized
- Consistent tag naming

### Annotations
- Behavioral hints set (readOnlyHint, destructiveHint)
- Title provided
- Appropriate hints for operation type

### Best Practices
- Parameter naming conventions
- Return type completeness
- Sensitive field marking

## Lint Output

### Success

```bash
mxcp lint

🔍 Lint Results
   Checked 2 endpoint files

🎉 All endpoints have excellent metadata!
```

### Issues Found

```bash
mxcp lint

🔍 Lint Results
   Checked 3 endpoint files
   • 2 files with suggestions
   • 5 warnings

📄 tools/get_user.yml
  ⚠️  tool.description
     Tool is missing a description
     💡 Add a 'description' field to help LLMs understand what this endpoint does
  ⚠️  tool.tests
     Tool has no tests defined
     💡 Add at least one test case to ensure the endpoint works correctly
  ℹ️  tool.parameters[0].examples
     Parameter 'user_id' has no examples
     💡 Consider adding an 'examples' array to help LLMs understand valid inputs

📄 tools/delete_user.yml
  ℹ️  tool.tags
     Tool has no tags
     💡 Consider adding tags to help categorize and discover this endpoint
  ℹ️  tool.annotations
     Tool has no behavioral annotations
     💡 Consider adding annotations like readOnlyHint, idempotentHint to help LLMs use the tool safely

📚 Why this matters:
   • Descriptions help LLMs understand your endpoints better
   • Examples show LLMs how to use parameters correctly
   • Tests ensure your endpoints work as expected
   • Good metadata = better LLM performance!
```

Severity levels:
- `⚠️` Warning - Important issues (missing description, missing tests)
- `ℹ️` Info - Suggestions for improvement (missing examples, tags, annotations)

### JSON Output

```bash
mxcp lint --json-output
```

```json
{
  "status": "ok",
  "result": [
    {
      "severity": "warning",
      "path": "tools/get_user.yml",
      "location": "tool.description",
      "message": "Tool is missing a description",
      "suggestion": "Add a 'description' field to help LLMs understand what this endpoint does"
    },
    {
      "severity": "info",
      "path": "tools/get_user.yml",
      "location": "tool.parameters[0].examples",
      "message": "Parameter 'user_id' has no examples",
      "suggestion": "Consider adding an 'examples' array to help LLMs understand valid inputs"
    }
  ]
}
```

Fields:
- `status`: Command execution status (`ok` or `error`)
- `result`: Array of lint issues
  - `severity`: Issue severity (`warning` or `info`)
  - `path`: Path to endpoint file
  - `location`: YAML path to the problematic field
  - `message`: Description of the issue
  - `suggestion`: Recommended fix

## Lint Rules

Note: Structural errors (invalid types, missing required fields) are caught by `mxcp validate`, not the linter. The linter focuses on metadata quality.

### Warning Rules

| Location | Message |
|----------|---------|
| `tool.description` | Tool is missing a description |
| `tool.tests` | Tool has no tests defined |
| `resource.description` | Resource is missing a description |

### Info Rules (Suggestions)

| Location | Message |
|----------|---------|
| `*.parameters[n].examples` | Parameter has no examples |
| `*.parameters[n].default` | Parameter has no default value |
| `*.tags` | Endpoint has no tags |
| `*.annotations` | Endpoint has no behavioral annotations |

## Fixing Common Issues

### Missing Tool Description

```yaml
# Before (warning: tool.description)
mxcp: 1
tool:
  name: get_user
  parameters:
    - name: user_id
      type: integer
      description: User ID
  source:
    code: "SELECT * FROM users WHERE id = $user_id"

# After (fixed)
mxcp: 1
tool:
  name: get_user
  description: Retrieve user information by their unique identifier
  parameters:
    - name: user_id
      type: integer
      description: User ID
  source:
    code: "SELECT * FROM users WHERE id = $user_id"
```

### Missing Tests

```yaml
# Before (warning: tool.tests)
mxcp: 1
tool:
  name: get_user
  description: Get user by ID
  # ... no tests defined

# After (fixed)
mxcp: 1
tool:
  name: get_user
  description: Get user by ID
  # ...
  tests:
    - name: get_existing_user
      arguments:
        - key: user_id
          value: 1
      result_contains:
        id: 1
```

### Missing Examples

```yaml
# Before (info: tool.parameters[0].examples)
parameters:
  - name: status
    type: string
    description: User status filter
    enum: ["active", "inactive", "pending"]

# After (fixed)
parameters:
  - name: status
    type: string
    description: User status filter
    enum: ["active", "inactive", "pending"]
    examples: ["active", "pending"]
```

### Missing Tags

```yaml
# Before (info: tool.tags)
tool:
  name: get_user
  description: Get user by ID

# After (fixed)
tool:
  name: get_user
  description: Get user by ID
  tags: ["users", "read"]
```

### Missing Annotations

```yaml
# Before (info: tool.annotations)
tool:
  name: delete_user
  description: Delete a user permanently

# After (fixed)
tool:
  name: delete_user
  description: Delete a user permanently
  annotations:
    title: "Delete User"
    readOnlyHint: false
    destructiveHint: true
    idempotentHint: false
```

### Sensitive Fields

Mark fields containing sensitive data:

```yaml
return:
  type: object
  properties:
    ssn:
      type: string
      sensitive: true
    password_hash:
      type: string
      sensitive: true
```

## Writing Good Descriptions

### Tool Descriptions

**Good:**
```yaml
tool:
  name: get_customer_orders
  description: |
    Retrieves order history for a specific customer.
    Returns orders sorted by date (newest first).
    Includes order items, totals, and shipping information.
```

**Bad:**
```yaml
tool:
  name: get_data
  description: "Gets data"
```

### Parameter Descriptions

**Good:**
```yaml
parameters:
  - name: status
    type: string
    description: "Order status filter"
    examples: ["pending", "shipped", "delivered", "cancelled"]
    enum: ["pending", "shipped", "delivered", "cancelled"]

  - name: date_from
    type: string
    format: date
    description: "Start date for filtering orders (inclusive)"
    examples: ["2024-01-01", "2024-06-15"]
```

**Bad:**
```yaml
parameters:
  - name: limit
    type: integer
    description: "The limit"
```

### Return Type Descriptions

Describe complex return types thoroughly:

```yaml
return:
  type: object
  description: "Customer order details"
  properties:
    order_id:
      type: string
      description: "Unique order identifier"
    items:
      type: array
      description: "List of items in the order"
      items:
        type: object
        description: "Individual order item"
        properties:
          sku:
            type: string
            description: "Product SKU"
          quantity:
            type: integer
            description: "Number of units ordered"
          price:
            type: number
            description: "Unit price at time of order"
```

## Behavioral Annotations

Use annotations to help AI understand tool behavior:

### readOnlyHint
```yaml
annotations:
  readOnlyHint: true  # Tool doesn't modify data
```

Use for: GET operations, searches, reports

### destructiveHint
```yaml
annotations:
  destructiveHint: true  # Tool permanently changes/deletes data
```

Use for: DELETE, DROP, permanent modifications

### idempotentHint
```yaml
annotations:
  idempotentHint: true  # Multiple calls have same effect
```

Use for: Updates, upserts, idempotent operations

### openWorldHint
```yaml
annotations:
  openWorldHint: true  # Tool accesses external systems
```

Use for: API calls, external services

## CI/CD Integration

### GitHub Actions (Complete Quality Workflow)

```yaml
name: MXCP Quality Checks
on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install mxcp

      - name: Validate Endpoints
        run: mxcp validate

      - name: Run Tests
        run: mxcp test

      - name: Lint Endpoints
        run: mxcp lint --severity warning
```

### Lint-Only Check

```yaml
name: Lint
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install mxcp
      - name: Run linter
        run: mxcp lint --json-output > lint-results.json
      - name: Check for warnings
        run: |
          if jq -e '.result[] | select(.severity == "warning")' lint-results.json > /dev/null; then
            echo "Lint warnings found"
            exit 1
          fi
```

### Quality Gate Script

```bash
#!/bin/bash
# Block on too many warnings

RESULT=$(mxcp lint --json-output)

WARNINGS=$(echo "$RESULT" | jq '[.result[] | select(.severity == "warning")] | length')
INFO=$(echo "$RESULT" | jq '[.result[] | select(.severity == "info")] | length')

echo "Warnings: $WARNINGS, Info: $INFO"

if [ "$WARNINGS" -gt 0 ]; then
    echo "Lint warnings found - please fix before merging"
    exit 1
fi

if [ "$INFO" -gt 20 ]; then
    echo "Too many suggestions - consider improving metadata"
    exit 1
fi
```

## Best Practices

### 1. Fix Warnings First
Warnings indicate important metadata gaps that affect LLM comprehension.

### 2. Address Suggestions
Info-level suggestions improve AI understanding significantly.

### 3. Be Specific
Generic descriptions don't help AI understand your tools.

### 4. Provide Examples
Examples help AI understand expected input formats.

### 5. Use Tags
Tags help organize and categorize endpoints.

### 6. Set Annotations
Behavioral hints prevent AI from misusing tools.

## Next Steps

- [Evals](/quality/evals) - Test AI behavior
- [Testing](/quality/testing) - Functional testing
- [Endpoints](/concepts/endpoints) - Endpoint structure
