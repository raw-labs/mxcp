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
mxcp: 1
tool:
  name: get_user
  description: Get user by ID
  parameters:
    - name: user_id
      type: integer
      description: The user's unique identifier
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

    - name: get_user_has_email
      description: Test that user has email field
      arguments:
        - key: user_id
          value: 1
      result_contains:
        email: "alice@example.com"
```

## Running Tests

```bash
# Run all tests
mxcp test

# Run tests for specific endpoint
mxcp test tool get_user
mxcp test resource user-profile
mxcp test prompt my_prompt

# JSON output
mxcp test --json-output

# Verbose output
mxcp test --debug

# Read-only database connection
mxcp test --readonly

# Run with user context (JSON string)
mxcp test --user-context '{"role": "admin"}'

# Run with user context (from file)
mxcp test --user-context @contexts/admin.json

# Run with request headers
mxcp test --request-headers '{"Authorization": "Bearer token123"}'
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

Result must contain these fields/values (partial object match):

```yaml
result_contains:
  name: "Alice"
  department: "Engineering"
```

Note: For checking if an array contains a specific item, use `result_contains_item` instead.

### Excludes

Result must NOT contain these fields:

```yaml
result_not_contains:
  - password
  - ssn
  - internal_id
```

### Null/Empty Check

For endpoints that explicitly return null or empty arrays:

```yaml
# Explicit null result
result: null

# Empty array result
result: []
result_length: 0
```

Note: Endpoints returning `type: object` that find no matching rows will throw a "No results returned" error rather than returning null. Test error conditions via CLI instead.

### Array Item Match

Check if array contains an item matching specific criteria:

```yaml
result_contains_item:
  name: "Alice"
  status: "active"
```

This passes if any item in the result array has `name: "Alice"` AND `status: "active"`.

### Array Contains All

Verify that all specified items exist in the array (in any order):

```yaml
result_contains_all:
  - department: "Engineering"
    role: "head"
  - department: "Sales"
    role: "head"
```

This passes if the result array contains items matching both criteria (partial matches).

### Array Length

Validate the number of items in an array result:

```yaml
result_length: 5
```

Note: `result_length` only supports exact counts. For range validation, use application logic or multiple tests.

### String Contains

For string results, verify they contain a specific substring:

```yaml
tests:
  - name: success_message
    arguments:
      - key: action
        value: "create"
    result_contains_text: "successfully created"

  - name: error_message
    arguments:
      - key: action
        value: "invalid"
    result_contains_text: "error"
```

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

## Testing Resources

Resources can be tested the same way as tools:

```yaml
mxcp: 1
resource:
  uri: "users://{user_id}"
  description: Get user profile by ID
  parameters:
    - name: user_id
      type: string
      description: User identifier
  source:
    code: |
      SELECT id, name, email FROM users WHERE id = $user_id

  tests:
    - name: get_specific_user
      description: Retrieve a specific user profile
      arguments:
        - key: user_id
          value: "alice"
      result_contains:
        id: "alice"
        email: "alice@example.com"
```

## Testing Complex Types

For endpoints returning objects or arrays:

```yaml
tests:
  - name: test_user_with_roles
    description: Test user lookup with nested data
    arguments:
      - key: user_id
        value: 123
    result:
      id: 123
      name: "John Doe"
      roles: ["user", "admin"]
      profile:
        department: "Engineering"
        level: "Senior"
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

```bash
mxcp test

🧪 Test Execution Summary
   Tested 2 endpoints
   • 2 passed

✅ Passed tests:

  ✓ tool/get_user (tools/get_user.yml)
    ✓ get_existing_user (0.05s)
    ✓ get_nonexistent_user (0.03s)

  ✓ tool/search_users (tools/search_users.yml)
    ✓ search_by_department (0.04s)
    ✓ search_with_pagination (0.06s)

🎉 All tests passed!

⏱️  Total time: 0.18s
```

### Failure

```bash
mxcp test

🧪 Test Execution Summary
   Tested 2 endpoints
   • 1 passed
   • 1 failed

❌ Failed tests:

  ✗ tool/get_user (tools/get_user.yml)
    ✓ get_existing_user (0.05s)
    ✗ get_wrong_name (0.03s)
      Error: Expected name='Alice', got name='Bob'

✅ Passed tests:

  ✓ tool/search_users (tools/search_users.yml)
    ✓ search_by_department (0.04s)

💡 Tip: Review the errors above and fix the failing tests

⏱️  Total time: 0.12s
```

### JSON Output

```bash
mxcp test --json-output
```

```json
{
  "status": "ok",
  "result": {
    "status": "failed",
    "tests_run": 2,
    "endpoints": [
      {
        "endpoint": "tool/get_user",
        "path": "tools/get_user.yml",
        "test_results": {
          "status": "failed",
          "tests_run": 2,
          "tests": [
            {
              "name": "get_existing_user",
              "description": "Test fetching an existing user",
              "status": "passed",
              "error": null,
              "time": 0.05
            },
            {
              "name": "get_wrong_name",
              "description": "Test that should fail",
              "status": "failed",
              "error": "Expected name='Alice', got name='Bob'",
              "time": 0.03
            }
          ]
        }
      }
    ]
  }
}
```

Fields:
- `status`: Command execution status (`ok` or `error`)
- `result`: Test results object
  - `status`: Overall test status (`ok`, `failed`, or `error`)
  - `tests_run`: Total number of tests executed
  - `endpoints`: List of endpoint test results
    - `endpoint`: Endpoint identifier (e.g., `tool/get_user`)
    - `path`: Path to endpoint file
    - `test_results`: Test suite results
      - `tests`: Individual test results with `name`, `description`, `status`, `error`, and `time`

## Test Data Setup

### Using Setup SQL

Create test data before running tests:

```sql title="sql/test_setup.sql"
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

### Using Python Scripts

For more complex setup, use a Python script with DuckDB directly:

```python title="scripts/setup_test_data.py"
import duckdb

def setup_test_data():
    conn = duckdb.connect("data/db-default.duckdb")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_users AS
        SELECT * FROM (VALUES
            (1, 'Alice'),
            (2, 'Bob')
        ) AS t(id, name)
    """)
    conn.close()

if __name__ == "__main__":
    setup_test_data()
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
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install mxcp
      - name: Setup test data
        run: |
          duckdb data/db-default.duckdb < sql/test_setup.sql
      - name: Run tests
        run: mxcp test --json-output > test-results.json
      - name: Upload results
        uses: actions/upload-artifact@v4
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

### 1. Choose the Right Assertion Type

- `result` - For stable, predictable outputs
- `result_contains` - For dynamic data with timestamps or generated IDs
- `result_not_contains` - For security/policy testing
- `result_contains_item` / `result_contains_all` - For array endpoints
- `result_length` - When count matters

```yaml
tests:
  # Handle dynamic data - don't check timestamps or auto-generated IDs
  - name: order_created
    result_contains:
      status: "pending"
      customer_id: "c123"
    # Ignores: created_at, order_id

  # Test empty results
  - name: no_matching_results
    arguments:
      - key: filter
        value: "non_existent"
    result: []
    result_length: 0
```

### 2. Test Every Endpoint
Each endpoint should have at least one test.

### 3. Test Edge Cases
- Empty inputs
- Invalid inputs
- Boundary values
- Null handling

### 4. Test Policies
If policies are defined, test all access levels:

```yaml
tests:
  - name: admin_sees_all
    user_context:
      role: admin
    result_contains:
      sensitive_field: "value"

  - name: user_filtered
    user_context:
      role: user
    result_not_contains:
      - sensitive_field
```

### 5. Use Descriptive Names
```yaml
# Good
- name: search_returns_matching_users
- name: admin_can_see_salary

# Bad
- name: test1
- name: search_test
```

### 6. Keep Tests Independent
Tests should not depend on each other.

### 7. Use Realistic Data
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
      description: Department to search in
      enum: ["Engineering", "Sales", "HR"]
    - name: role
      type: string
      description: Filter by role (optional)
      default: null
    - name: limit
      type: integer
      description: Maximum results to return
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
      result_contains_item:
        department: "Engineering"

    - name: search_with_role
      description: Filter by role
      arguments:
        - key: department
          value: "Engineering"
        - key: role
          value: "Senior"
      result_contains_item:
        role: "Senior"

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
