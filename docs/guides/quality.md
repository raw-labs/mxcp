---
title: "Quality & Testing Guide"
description: "Best practices for ensuring endpoint quality through validation, testing, and linting in MXCP. Learn how to write tests, validate endpoints, and maintain high-quality metadata."
keywords:
  - mxcp testing
  - endpoint validation
  - mxcp lint
  - quality assurance
  - test cases
  - metadata best practices
sidebar_position: 4
slug: /guides/quality
---

# Quality & Testing Guide

This guide covers best practices for ensuring high-quality endpoints in MXCP through validation, testing, and linting. Well-tested endpoints with comprehensive metadata provide better experiences for both developers and LLMs.

## Overview

MXCP provides three complementary tools for endpoint quality:

1. **Validation** (`mxcp validate`) - Ensures endpoints are structurally correct
2. **Testing** (`mxcp test`) - Verifies endpoints work as expected
3. **Linting** (`mxcp lint`) - Suggests metadata improvements for better LLM performance

## Validation

Validation ensures your endpoints meet the required schema and can be loaded correctly.

### Running Validation

```bash
# Validate all endpoints
mxcp validate

# Validate a specific endpoint
mxcp validate my_endpoint

# Get JSON output for CI/CD
mxcp validate --json-output
```

### What Validation Checks

- YAML syntax correctness
- Required fields presence
- Type definitions validity
- Parameter names and patterns
- SQL syntax (basic checks)
- File references existence

### Common Validation Errors

```yaml
# ❌ Missing required field
tool:
  # name: missing!
  description: "My tool"
  source:
    code: "SELECT 1"

# ❌ Invalid parameter name
tool:
  name: my_tool
  parameters:
    - name: "user-name"  # Must match ^[a-zA-Z_][a-zA-Z0-9_]*$
      type: string
      description: "Username"

# ❌ Invalid type
tool:
  name: my_tool
  return:
    type: map  # Should be 'object'
```

## Testing

Tests verify that your endpoints produce correct results with various inputs.

### Writing Tests

Add tests to your endpoint definition:

```yaml
tool:
  name: calculate_discount
  description: "Calculate discount amount"
  parameters:
    - name: price
      type: number
      description: "Original price"
    - name: discount_percent
      type: number
      description: "Discount percentage (0-100)"
  return:
    type: number
    description: "Discounted price"
  source:
    code: |
      SELECT $price * (1 - $discount_percent / 100.0) as result
  
  tests:
    - name: "10% discount"
      description: "Test 10% discount calculation"
      arguments:
        - key: price
          value: 100
        - key: discount_percent
          value: 10
      result: 90
    
    - name: "No discount"
      description: "Test with 0% discount"
      arguments:
        - key: price
          value: 50
        - key: discount_percent
          value: 0
      result: 50
    
    - name: "Maximum discount"
      description: "Test 100% discount"
      arguments:
        - key: price
          value: 200
        - key: discount_percent
          value: 100
      result: 0
```

### Test Structure

Each test requires:
- `name` - Unique test identifier
- `arguments` - Array of key-value pairs for parameters
- `result` - Expected output

Optional:
- `description` - Explains what the test validates (recommended!)

### Running Tests

```bash
# Run all tests
mxcp test

# Test specific endpoint
mxcp test tool calculate_discount

# Run with detailed output
mxcp test --debug
```

### Testing Complex Types

For endpoints returning objects or arrays:

```yaml
tests:
  - name: "Test user lookup"
    arguments:
      - key: user_id
        value: 123
    result:
      id: 123
      name: "John Doe"
      roles: ["user", "admin"]
```

### Testing Resources

Resources can be tested the same way as tools:

```yaml
resource:
  uri: "users://{user_id}"
  tests:
    - name: "Get specific user"
      arguments:
        - key: user_id
          value: "alice"
      result: |
        {
          "id": "alice",
          "email": "alice@example.com"
        }
```

## Linting

The lint command helps you write better metadata for optimal LLM performance.

### Running Lint

```bash
# Check all endpoints
mxcp lint

# Show only warnings (skip info-level suggestions)
mxcp lint --severity warning

# Get JSON output for automation
mxcp lint --json-output
```

### What Lint Checks

#### Warnings (Important for LLM usage)
- Missing endpoint descriptions
- Missing test cases
- Missing parameter examples
- Missing return type descriptions
- Missing descriptions on nested types

#### Info (Nice to have)
- Missing parameter default values
- Missing test descriptions
- Missing tags
- Missing behavioral annotations

### Example Lint Output

```
🔍 Lint Results
   Checked 5 endpoint files
   • 3 files with suggestions
   • 6 warnings
   • 4 suggestions

📄 endpoints/search_users.yml
  ⚠️  tool.description
     Tool is missing a description
     💡 Add a 'description' field to help LLMs understand what this endpoint does
  
  ⚠️  tool.parameters[0].examples
     Parameter 'query' is missing examples
     💡 Add an 'examples' array to help LLMs understand valid values
  
  ℹ️  tool.tags
     Tool has no tags
     💡 Consider adding tags to help categorize and discover this endpoint
```

## Best Practices

### 1. Comprehensive Descriptions

Good descriptions help LLMs understand when and how to use your endpoints:

```yaml
# ❌ Poor
tool:
  name: get_data
  description: "Gets data"

# ✅ Good
tool:
  name: get_customer_orders
  description: |
    Retrieves order history for a specific customer.
    Returns orders sorted by date (newest first).
    Includes order items, totals, and shipping information.
```

### 2. Meaningful Examples

Examples guide LLMs on valid parameter values:

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
    description: "Start date for filtering orders"
    examples: ["2024-01-01", "2024-06-15"]
```

### 3. Type Descriptions

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

### 4. Behavioral Annotations

Help LLMs use tools safely:

```yaml
tool:
  name: delete_user
  annotations:
    destructiveHint: true  # Warns LLM this is destructive
    idempotentHint: false  # Multiple calls have different effects
    
tool:
  name: get_weather
  annotations:
    readOnlyHint: true     # Safe to call anytime
    openWorldHint: true    # Depends on external data
```

### 5. Edge Case Testing

Test boundary conditions and error cases:

```yaml
tests:
  - name: "Empty input"
    description: "Verify handling of empty string"
    arguments:
      - key: text
        value: ""
    result: null
    
  - name: "Maximum length"
    description: "Test with maximum allowed length"
    arguments:
      - key: text
        value: "x" # Repeated 1000 times
    result: "processed"
    
  - name: "Special characters"
    description: "Ensure special chars are handled"
    arguments:
      - key: text
        value: "Hello @#$%^&* World!"
    result: "Hello World!"
```

## CI/CD Integration

### Validation in CI

```bash
#!/bin/bash
# ci-validate.sh

set -e

echo "Running endpoint validation..."
if ! mxcp validate --json-output > validation-results.json; then
  echo "Validation failed!"
  cat validation-results.json
  exit 1
fi

echo "All endpoints valid!"
```

### Testing in CI

```bash
#!/bin/bash
# ci-test.sh

set -e

echo "Running endpoint tests..."
if ! mxcp test --json-output > test-results.json; then
  echo "Tests failed!"
  cat test-results.json
  exit 1
fi

echo "All tests passed!"
```

### Linting in CI

```bash
#!/bin/bash
# ci-lint.sh

# Run lint and check for warnings
mxcp lint --severity warning --json-output > lint-results.json

# Count warnings
WARNING_COUNT=$(jq 'length' lint-results.json)

if [ "$WARNING_COUNT" -gt 0 ]; then
  echo "Found $WARNING_COUNT lint warnings:"
  cat lint-results.json | jq -r '.[] | "[\(.severity)] \(.path): \(.message)"'
  
  # Optionally fail the build
  # exit 1
fi
```

### GitHub Actions Example

```yaml
name: MXCP Quality Checks

on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install MXCP
        run: pip install mxcp
      
      - name: Validate Endpoints
        run: mxcp validate
      
      - name: Run Tests
        run: mxcp test
      
      - name: Lint Endpoints
        run: |
          mxcp lint --severity warning
          # Or to track but not fail:
          # mxcp lint || true
```

## Quality Metrics

Track endpoint quality over time:

```sql
-- Query to analyze test coverage
WITH endpoint_counts AS (
  SELECT 
    COUNT(*) as total_endpoints,
    COUNT(CASE WHEN has_tests THEN 1 END) as tested_endpoints,
    COUNT(CASE WHEN has_description THEN 1 END) as documented_endpoints
  FROM endpoints
)
SELECT 
  total_endpoints,
  tested_endpoints,
  documented_endpoints,
  ROUND(100.0 * tested_endpoints / total_endpoints, 1) as test_coverage_pct,
  ROUND(100.0 * documented_endpoints / total_endpoints, 1) as doc_coverage_pct
FROM endpoint_counts;
```

## Troubleshooting

### Common Issues

**Tests passing locally but failing in CI:**
- Check for environment-specific data
- Ensure consistent timezone handling
- Verify database state assumptions

**Lint warnings on generated code:**
- Use `.mxcpignore` to exclude generated files
- Focus on hand-written endpoint definitions

**Validation errors after updates:**
- Run `mxcp validate --debug` for detailed errors
- Check the schema version in endpoint files
- Ensure all file references are relative

## Summary

Quality assurance in MXCP involves:

1. **Validate** structure with `mxcp validate`
2. **Test** functionality with `mxcp test`
3. **Improve** metadata with `mxcp lint`

Well-tested endpoints with rich metadata provide:
- Better reliability
- Improved LLM understanding
- Easier maintenance
- Faster debugging

Remember: LLMs perform best when they clearly understand what your endpoints do, how to use them, and what to expect in return! 