---
title: "Validation"
description: "Validate MXCP endpoint structure and syntax. Check YAML correctness, required fields, type definitions, and file references."
sidebar:
  order: 2
---

> **Related Topics:** [Testing](/quality/testing) (run assertions) | [Linting](/quality/linting) (metadata quality) | [Type System](/concepts/type-system) (type definitions) | [YAML Schemas](/schemas/) (field reference)

Validation ensures your endpoint definitions are structurally correct before execution. It catches errors early in development.

## Running Validation

```bash
# Validate all endpoints
mxcp validate

# JSON output for automation
mxcp validate --json-output

# Debug mode for detailed errors
mxcp validate --debug
```

## What Gets Validated

### YAML Syntax
- Correct YAML formatting
- Proper indentation
- Valid characters

### Required Fields
- `mxcp: 1` version field
- Endpoint type (`tool`, `resource`, or `prompt`)
- `name` or `uri` identifier
- `description` field
- `source` specification

### Type Definitions
- Valid type names (`string`, `number`, etc.)
- Correct format annotations
- Valid constraints (`minimum`, `maximum`, etc.)
- Nested type structures

### File References
- Source files exist
- Paths are resolvable
- Files are readable

### SQL/Python Syntax
- Basic SQL parsing
- Python module loading
- Function existence check

## Validation Output

### Success

```
$ mxcp validate

✓ tools/get_user.yml (tool/get_user)
✓ tools/search_users.yml (tool/search_users)
✓ resources/user-profile.yml (resource/users://{id})

Validation complete: 3 passed, 0 failed
```

### Failure

```
$ mxcp validate

✓ tools/get_user.yml (tool/get_user)
✗ tools/broken.yml
  Error: Missing required field 'description'
  Line 3: tool:
    name: broken_tool
✗ tools/invalid_type.yml
  Error: Invalid type 'strng', did you mean 'string'?
  Line 8: type: strng

Validation complete: 1 passed, 2 failed
```

### JSON Output

```bash
mxcp validate --json-output
```

```json
{
  "status": "error",
  "results": [
    {
      "path": "tools/get_user.yml",
      "endpoint": "tool/get_user",
      "status": "ok"
    },
    {
      "path": "tools/broken.yml",
      "endpoint": null,
      "status": "error",
      "error": "Missing required field 'description'",
      "line": 3
    }
  ],
  "summary": {
    "passed": 1,
    "failed": 1,
    "total": 2
  }
}
```

## Common Validation Errors

### Missing Required Fields

```yaml
# Error: Missing required field 'description'
tool:
  name: my_tool
  source:
    code: "SELECT 1"
```

Fix:
```yaml
tool:
  name: my_tool
  description: A tool that does something  # Added
  source:
    code: "SELECT 1"
```

### Invalid Type

```yaml
# Error: Invalid type 'strng'
parameters:
  - name: id
    type: strng  # Typo
```

Fix:
```yaml
parameters:
  - name: id
    type: string  # Corrected
```

### Invalid Format

```yaml
# Error: Invalid format 'datetime' for type 'string'
parameters:
  - name: created
    type: string
    format: datetime  # Wrong
```

Fix:
```yaml
parameters:
  - name: created
    type: string
    format: date-time  # Correct format
```

### File Not Found

```yaml
# Error: Source file not found: ../sql/missing.sql
source:
  file: ../sql/missing.sql
```

Fix: Create the file or correct the path.

### Invalid Constraint

```yaml
# Error: minimum cannot be greater than maximum
parameters:
  - name: count
    type: integer
    minimum: 100
    maximum: 10  # Invalid
```

Fix:
```yaml
parameters:
  - name: count
    type: integer
    minimum: 10
    maximum: 100  # Corrected
```

### Duplicate Names

```yaml
# Error: Duplicate parameter name 'id'
parameters:
  - name: id
    type: integer
  - name: id  # Duplicate
    type: string
```

Fix: Use unique parameter names.

### Missing Return Type

```yaml
# Error: Return type required for tools
tool:
  name: my_tool
  description: Returns data
  source:
    code: "SELECT * FROM data"
  # Missing return type
```

Fix:
```yaml
tool:
  name: my_tool
  description: Returns data
  return:
    type: array
    items:
      type: object
  source:
    code: "SELECT * FROM data"
```

## Validation Strictness

MXCP validates with different strictness levels:

### Required (Always Checked)
- YAML syntax
- Required fields
- Type validity
- File existence

### Recommended (Warnings)
- Description quality
- Example presence
- Type completeness

Use `mxcp lint` for recommended checks.

## CI/CD Integration

### GitHub Actions

```yaml
name: Validate
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install mxcp
      - run: mxcp validate
```

### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

mxcp validate
if [ $? -ne 0 ]; then
    echo "Validation failed. Please fix errors before committing."
    exit 1
fi
```

### GitLab CI

```yaml
validate:
  stage: test
  script:
    - pip install mxcp
    - mxcp validate
```

## Best Practices

### 1. Validate During Development
Run `mxcp validate` after every change.

### 2. Use Editor Integration
Many editors validate YAML syntax automatically.

### 3. Fix Errors Immediately
Don't let validation errors accumulate.

### 4. Include in CI/CD
Block merges on validation failures.

### 5. Use Debug Mode
When errors are unclear:
```bash
mxcp validate --debug
```

## Troubleshooting

### "File not found" but file exists
- Check relative path from YAML file
- Verify case sensitivity
- Check file permissions

### "Invalid YAML" with no details
- Run YAML through online validator
- Check for tabs vs spaces
- Look for special characters

### Validation passes but tool fails
- Validation checks structure, not logic
- Run `mxcp test` for functional testing
- Check SQL/Python syntax separately

## Next Steps

- [Testing](/quality/testing) - Functional testing
- [Linting](/quality/linting) - Metadata quality
- [Type System](/concepts/type-system) - Type reference
