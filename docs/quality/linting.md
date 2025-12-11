---
title: "Linting"
description: "Improve MXCP endpoint quality for LLM comprehension. Check descriptions, examples, and metadata best practices."
sidebar:
  order: 4
---

> **Related Topics:** [Validation](validation) (structural checks) | [Testing](testing) (functional tests) | [Endpoints](/concepts/endpoints) (definition best practices) | [Common Tasks](/reference/common-tasks#how-do-i-check-for-linting-issues) (quick how-to)

The MXCP linter checks your endpoint metadata quality, ensuring AI tools can understand and use your endpoints effectively.

## Running Linter

```bash
# Lint all endpoints
mxcp lint

# Lint specific endpoint
mxcp lint --tool get_user
mxcp lint --resource user-profile

# JSON output
mxcp lint --json-output
```

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

```
$ mxcp lint

✓ tools/get_user.yml
✓ tools/search_users.yml

Lint complete: 2 passed, 0 warnings, 0 errors
```

### Warnings

```
$ mxcp lint

tools/get_user.yml:
  ⚠ Parameter 'user_id' missing description
  ⚠ No examples provided for parameter 'user_id'
  ⚠ Consider adding tags for categorization

tools/dangerous_delete.yml:
  ⚠ Destructive operation should set destructiveHint: true
  ⚠ Consider adding idempotentHint annotation

Lint complete: 0 passed, 4 warnings, 0 errors
```

### JSON Output

```bash
mxcp lint --json-output
```

```json
{
  "status": "warning",
  "results": [
    {
      "path": "tools/get_user.yml",
      "endpoint": "tool/get_user",
      "issues": [
        {
          "severity": "warning",
          "code": "missing-description",
          "message": "Parameter 'user_id' missing description",
          "line": 8
        },
        {
          "severity": "warning",
          "code": "missing-examples",
          "message": "No examples provided for parameter 'user_id'",
          "line": 8
        }
      ]
    }
  ]
}
```

## Lint Rules

### Required Rules (Errors)

| Code | Description |
|------|-------------|
| `no-description` | Endpoint missing description |
| `empty-description` | Description is empty or whitespace |
| `invalid-type` | Type annotation is invalid |

### Recommended Rules (Warnings)

| Code | Description |
|------|-------------|
| `missing-description` | Parameter/return missing description |
| `missing-examples` | Parameter missing examples |
| `missing-tags` | Endpoint has no tags |
| `missing-annotations` | Missing behavioral annotations |
| `short-description` | Description too short (< 10 chars) |
| `generic-description` | Description is too generic |

### Best Practice Rules (Suggestions)

| Code | Description |
|------|-------------|
| `destructive-no-hint` | Destructive operation without hint |
| `readonly-no-hint` | Read-only operation without hint |
| `sensitive-no-mark` | Potentially sensitive field not marked |
| `parameter-naming` | Non-standard parameter naming |

## Fixing Common Issues

### Missing Description

```yaml
# Before (warning)
parameters:
  - name: user_id
    type: integer

# After (fixed)
parameters:
  - name: user_id
    type: integer
    description: Unique identifier for the user
```

### Missing Examples

```yaml
# Before (warning)
parameters:
  - name: status
    type: string
    enum: ["active", "inactive", "pending"]

# After (fixed)
parameters:
  - name: status
    type: string
    enum: ["active", "inactive", "pending"]
    examples: ["active", "pending"]
```

### Missing Tags

```yaml
# Before (warning)
tool:
  name: get_user

# After (fixed)
tool:
  name: get_user
  tags: ["users", "read"]
```

### Missing Annotations

```yaml
# Before (warning)
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

### Short Description

```yaml
# Before (warning)
tool:
  name: get_user
  description: Gets user

# After (fixed)
tool:
  name: get_user
  description: Retrieve user information by their unique identifier. Returns profile, contact, and role data.
```

### Sensitive Fields

```yaml
# Before (warning)
return:
  type: object
  properties:
    ssn:
      type: string
    password_hash:
      type: string

# After (fixed)
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
> "Search for users by department and role. Returns paginated results with user profiles including name, email, and team information."

**Bad:**
> "Searches users"

### Parameter Descriptions

**Good:**
> "Maximum number of results to return. Use with offset for pagination. Default is 10, maximum is 100."

**Bad:**
> "The limit"

### Return Descriptions

**Good:**
> "List of matching users sorted by relevance. Each user object includes id, name, email, and department."

**Bad:**
> "User data"

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

### GitHub Actions

```yaml
name: Lint
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install mxcp
      - name: Run linter
        run: mxcp lint --json-output > lint-results.json
      - name: Check for errors
        run: |
          if jq -e '.results[].issues[] | select(.severity == "error")' lint-results.json > /dev/null; then
            echo "Lint errors found"
            exit 1
          fi
```

### Quality Gate

```bash
#!/bin/bash
# Block on errors, warn on warnings

RESULT=$(mxcp lint --json-output)

ERRORS=$(echo $RESULT | jq '[.results[].issues[] | select(.severity == "error")] | length')
WARNINGS=$(echo $RESULT | jq '[.results[].issues[] | select(.severity == "warning")] | length')

echo "Errors: $ERRORS, Warnings: $WARNINGS"

if [ "$ERRORS" -gt 0 ]; then
    exit 1
fi

if [ "$WARNINGS" -gt 10 ]; then
    echo "Too many warnings"
    exit 1
fi
```

## Best Practices

### 1. Fix Errors First
Errors indicate real problems that will affect functionality.

### 2. Address Warnings
Warnings improve AI comprehension significantly.

### 3. Be Specific
Generic descriptions don't help AI understand your tools.

### 4. Provide Examples
Examples help AI understand expected input formats.

### 5. Use Tags
Tags help organize and categorize endpoints.

### 6. Set Annotations
Behavioral hints prevent AI from misusing tools.

## Next Steps

- [Evals](evals) - Test AI behavior
- [Testing](testing) - Functional testing
- [Endpoints](/concepts/endpoints) - Endpoint structure
