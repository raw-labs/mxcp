---
title: "Testing"
description: "MXCP test framework: YAML test definitions, result assertions, policy testing with user_context, error handling, CI/CD integration."
sidebar:
  order: 3
---

> **Related Topics:** [Validation](/quality/validation) (check syntax before testing) | [Policies](/security/policies) (test access control) | [Evals](/quality/evals) (AI behavior testing) | [Common Tasks](/reference/common-tasks#how-do-i-add-tests-to-an-endpoint) (quick how-to)

MXCP provides built-in testing capabilities to verify endpoint functionality. Tests are defined directly in endpoint YAML files and run with `mxcp test`.

## Defining Tests

Add tests to your endpoint definition:

```yaml
tool:
  name: get_user
  description: Get user by ID
  parameters:
    - name: user_id
      type: integer
  return:
    type: object
  source:
    file: ../sql/get_user.sql

  tests:
    - name: get_existing_user
      description: Test fetching an existing user
      arguments:
        - key: user_id
          value: 1
      result_contains:
        id: 1
        name: "Alice"

    - name: get_nonexistent_user
      description: Test fetching a non-existent user
      arguments:
        - key: user_id
          value: 99999
      result: null
```

## Running Tests

```bash
# Run all tests
mxcp test

# Run tests for specific endpoint
mxcp test tool get_user
mxcp test resource user-profile

# JSON output
mxcp test --json-output

# Verbose output
mxcp test --debug
```

## Test Structure

Each test has:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique test identifier |
| `description` | No | Human-readable description |
| `arguments` | Yes | Input parameters |
| `result` | No | Expected exact result |
| `user_context` | No | Simulated user for policy testing |
| `result_contains` | No | Partial match - fields/values must exist |
| `result_not_contains` | No | List of field names that must NOT exist |
| `result_contains_item` | No | For arrays - at least one item must match |
| `result_contains_all` | No | For arrays - all items must be present |
| `result_length` | No | For arrays - exact item count |
| `result_contains_text` | No | For strings - must contain substring |

## Argument Specification

### Key-Value Format

```yaml
arguments:
  - key: user_id
    value: 1
  - key: name
    value: "Alice"
  - key: active
    value: true
```

### Complex Values

```yaml
arguments:
  - key: filters
    value:
      status: "active"
      department: "Engineering"
  - key: ids
    value: [1, 2, 3]
```

## Assertion Types

### Exact Match

Test expects exactly this result:

```yaml
result: "Hello, World!"
```

```yaml
result:
  id: 1
  name: "Alice"
```

### Contains

Result must contain these fields/values:

```yaml
result_contains:
  name: "Alice"
  department: "Engineering"
```

For arrays, checks if any item matches:

```yaml
result_contains:
  - name: "Alice"
```

### Excludes

Result must NOT contain these fields:

```yaml
result_not_contains:
  - password
  - ssn
  - internal_id
```

### Null Check

Result should be null/empty:

```yaml
result: null
```

### Array Item Match

Check if array contains an item matching specific criteria:

```yaml
result_contains_item:
  name: "Alice"
  status: "active"
```

This passes if any item in the result array has `name: "Alice"` AND `status: "active"`.

### Array Length

Validate the number of items in an array result:

```yaml
result_length: 5
```

Note: `result_length` only supports exact counts. For range validation, use application logic or multiple tests.

### Combined Assertions

You can combine multiple assertions:

```yaml
result_contains:
  status: "success"
  data:
    id: 1
result_not_contains:
  - error
  - internal_error
result_length: 1
```

## Policy Testing

Test access control policies with user context:

```yaml
tests:
  - name: admin_sees_all
    description: Admin can see all fields including sensitive data
    arguments:
      - key: id
        value: 1
    user_context:
      role: admin
      permissions:
        - data.read
        - pii.view
    result_contains:
      id: 1
      name: "Alice"
      salary: 75000
      ssn: "123-45-6789"

  - name: user_filtered
    description: Regular user sees filtered data (no sensitive fields)
    arguments:
      - key: id
        value: 1
    user_context:
      role: user
      permissions:
        - data.read
    result_contains:
      id: 1
      name: "Alice"
    result_not_contains:
      - salary
      - ssn
```

Note: Policy denial tests (where access is blocked) cannot be tested via YAML test assertions. Use CLI testing with `--user-context` to verify deny policies:

```bash
mxcp run tool my_tool --param id=1 --user-context '{"role": "guest"}'
# Expect: "Policy enforcement failed: ..."
```

## Error Testing

Error conditions (invalid inputs, missing required fields, etc.) cannot be tested via YAML test assertions. Use CLI testing to verify error handling:

```bash
# Test invalid input
mxcp run tool my_tool --param user_id=-1
# Expect validation error

# Test missing required field
mxcp run tool my_tool
# Expect: "Missing required parameter: user_id"
```

For automated error testing, consider using shell scripts or your CI/CD pipeline to check exit codes and error messages.

## Test Output

### Success

```
$ mxcp test

Testing tool/get_user...
  ✓ get_existing_user
  ✓ get_nonexistent_user

Testing tool/search_users...
  ✓ search_by_department
  ✓ search_with_pagination

Tests: 4 passed, 0 failed
```

### Failure

```
$ mxcp test

Testing tool/get_user...
  ✓ get_existing_user
  ✗ get_wrong_name
    Expected: name = "Alice"
    Actual: name = "Bob"

Tests: 1 passed, 1 failed
```

### JSON Output

```bash
mxcp test --json-output
```

```json
{
  "status": "error",
  "results": [
    {
      "endpoint": "tool/get_user",
      "test": "get_existing_user",
      "status": "passed"
    },
    {
      "endpoint": "tool/get_user",
      "test": "get_wrong_name",
      "status": "failed",
      "expected": {"name": "Alice"},
      "actual": {"name": "Bob"}
    }
  ],
  "summary": {
    "passed": 1,
    "failed": 1,
    "total": 2
  }
}
```

## Test Data Setup

### Using Setup SQL

Create test data before running tests:

```sql
-- sql/test_setup.sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name VARCHAR,
    email VARCHAR
);

INSERT OR REPLACE INTO users VALUES
    (1, 'Alice', 'alice@example.com'),
    (2, 'Bob', 'bob@example.com');
```

Run setup:
```bash
duckdb data/db-default.duckdb < sql/test_setup.sql
mxcp test
```

### Using Fixtures

For Python tests, use fixtures in your test module:

```python
# python/test_fixtures.py
from mxcp.runtime import db

def setup_test_data():
    db.execute("""
        CREATE TABLE IF NOT EXISTS test_users AS
        SELECT * FROM (VALUES
            (1, 'Alice'),
            (2, 'Bob')
        ) AS t(id, name)
    """)
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install mxcp
      - name: Setup test data
        run: |
          duckdb data/db-default.duckdb < sql/test_setup.sql
      - name: Run tests
        run: mxcp test --json-output > test-results.json
      - name: Upload results
        uses: actions/upload-artifact@v2
        with:
          name: test-results
          path: test-results.json
```

### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

mxcp validate && mxcp test
if [ $? -ne 0 ]; then
    echo "Tests failed. Fix before committing."
    exit 1
fi
```

## Best Practices

### 1. Test Every Endpoint
Each endpoint should have at least one test.

### 2. Test Edge Cases
- Empty inputs
- Invalid inputs
- Boundary values
- Null handling

### 3. Test Policies
If policies are defined, test all access levels.

### 4. Use Descriptive Names
```yaml
# Good
- name: search_returns_matching_users
- name: admin_can_see_salary

# Bad
- name: test1
- name: search_test
```

### 5. Keep Tests Independent
Tests should not depend on each other.

### 6. Use Realistic Data
Test with data similar to production.

## Complete Example

```yaml
mxcp: 1
tool:
  name: employee_search
  description: Search employees by department and role
  parameters:
    - name: department
      type: string
      enum: ["Engineering", "Sales", "HR"]
    - name: role
      type: string
      default: null
    - name: limit
      type: integer
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
        role:
          type: string
        salary:
          type: number
          sensitive: true

  source:
    file: ../sql/employee_search.sql

  policies:
    output:
      - condition: "user.role != 'hr'"
        action: filter_fields
        fields: ["salary"]

  tests:
    - name: search_engineering
      description: Find Engineering employees
      arguments:
        - key: department
          value: "Engineering"
      result_contains:
        - department: "Engineering"

    - name: search_with_role
      description: Filter by role
      arguments:
        - key: department
          value: "Engineering"
        - key: role
          value: "Senior"
      result_contains:
        - role: "Senior"

    - name: limit_results
      description: Respect limit parameter
      arguments:
        - key: department
          value: "Engineering"
        - key: limit
          value: 2

    - name: hr_sees_salary
      description: HR can see salary field
      arguments:
        - key: department
          value: "Engineering"
      user_context:
        role: hr
      result_contains_item:
        department: "Engineering"
        salary: 95000

    - name: non_hr_no_salary
      description: Non-HR cannot see salary (filtered by policy)
      arguments:
        - key: department
          value: "Engineering"
      user_context:
        role: engineer
      result_contains_item:
        department: "Engineering"
        # salary field is filtered out by policy
```

## Next Steps

- [Linting](/quality/linting) - Metadata quality
- [Evals](/quality/evals) - LLM behavior testing
- [Policies](/security/policies) - Policy configuration
