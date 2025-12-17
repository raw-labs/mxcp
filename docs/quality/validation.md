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

# Validate a specific endpoint (use file path)
mxcp validate tools/my_tool.yml

# JSON output for automation
mxcp validate --json-output

# Debug mode for detailed errors
mxcp validate --debug

# Read-only database connection
mxcp validate --readonly
```

## What Gets Validated

### YAML Syntax
- Correct YAML formatting
- Proper indentation
- Valid characters

### Required Fields
- `mxcp: 1` version field
- Endpoint type (`tool`, `resource`, or `prompt`)
- `name` for tools/prompts, `uri` for resources
- `source` specification (for tools and resources)
- `description` for each parameter

### Type Definitions
- Valid type names (`string`, `number`, `integer`, `boolean`, `array`, `object`)
- Valid format annotations (`email`, `uri`, `date`, `time`, `date-time`, `duration`, `timestamp`)
- Valid language (`sql`, `python`)
- Nested type structures

### Parameter Names
- Must match pattern `^[a-zA-Z_][a-zA-Z0-9_]*$`
- Start with letter or underscore
- Only alphanumeric and underscores allowed

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

```bash
mxcp validate

🔍 Validation Results
   Validated 3 endpoint files
   • 3 passed

✅ Passed validation:
  ✓ tools/get_user.yml
  ✓ tools/search_users.yml
  ✓ resources/user-profile.yml

🎉 All endpoints are valid!
```

### Failure

```bash
mxcp validate

🔍 Validation Results
   Validated 3 endpoint files
   • 1 passed
   • 2 failed

❌ Failed validation:
  ✗ tools/broken.yml
    Error: tool.parameters.0: 'description' is a required property

  ✗ tools/invalid_type.yml
    Error: tool.parameters.0.type: 'strng' is not one of ['string', 'number', 'integer', 'boolean', 'array', 'object']

✅ Passed validation:
  ✓ tools/get_user.yml

💡 Tip: Fix validation errors to ensure endpoints work correctly
```

### JSON Output

```bash
mxcp validate --json-output
```

```json
{
  "status": "ok",
  "result": {
    "status": "error",
    "validated": [
      {
        "status": "ok",
        "path": "tools/get_user.yml"
      },
      {
        "status": "error",
        "path": "tools/broken.yml",
        "message": "tool.parameters.0: 'description' is a required property"
      }
    ]
  }
}
```

Fields:
- `status`: Command execution status (`ok` or `error`)
- `result`: Validation results object
  - `status`: Overall validation status (`ok` or `error`)
  - `validated`: List of validation results
    - `status`: Individual result (`ok` or `error`)
    - `path`: Path to endpoint file
    - `message`: Error message (only present on errors)

## Common Validation Errors

### Missing Endpoint Type

```yaml
# Error: Endpoint definition must include a tool, resource, or prompt definition
mxcp: 1
# Missing: tool, resource, or prompt definition
```

Fix:
```yaml
mxcp: 1
tool:
  name: my_tool
  source:
    code: "SELECT 1"
```

### Missing Source Specification

```yaml
# Error: tool.source: {} is not valid under any of the given schemas
tool:
  name: my_tool
  source: {}  # Missing code or file
```

Fix:
```yaml
tool:
  name: my_tool
  source:
    code: "SELECT 1"
```

### Invalid Type

```yaml
# Error: 'strng' is not one of ['string', 'number', 'integer', 'boolean', 'array', 'object']
parameters:
  - name: id
    type: strng  # Typo
    description: User ID
```

Fix:
```yaml
parameters:
  - name: id
    type: string  # Corrected
    description: User ID
```

Common mistake - using `map` instead of `object`:
```yaml
# Error: 'map' is not one of ['string', 'number', 'integer', 'boolean', 'array', 'object']
return:
  type: map  # Wrong - use 'object'
```

Fix:
```yaml
return:
  type: object  # Correct
```

### Invalid Parameter Name

```yaml
# Error: 'user-name' does not match '^[a-zA-Z_][a-zA-Z0-9_]*$'
parameters:
  - name: user-name  # Hyphens not allowed
    type: string
    description: Username
```

Fix:
```yaml
parameters:
  - name: user_name  # Use underscores
    type: string
    description: Username
```

Parameter names must start with a letter or underscore and contain only alphanumeric characters and underscores.

### Invalid Format

```yaml
# Error: 'datetime' is not one of ['email', 'uri', 'date', 'time', 'date-time', 'duration', 'timestamp']
parameters:
  - name: created
    type: string
    format: datetime  # Wrong
    description: Creation date
```

Fix:
```yaml
parameters:
  - name: created
    type: string
    format: date-time  # Correct (with hyphen)
    description: Creation date
```

### File Not Found

```yaml
# Error: Source file not found: ../sql/missing.sql
source:
  file: ../sql/missing.sql
```

Fix: Create the file or correct the path.

### Missing Parameter Description

```yaml
# Error: 'description' is a required property
parameters:
  - name: user_id
    type: string
    # Missing description
```

Fix:
```yaml
parameters:
  - name: user_id
    type: string
    description: The unique user identifier
```

### Invalid Source

Source must specify exactly one of `code` or `file`:

```yaml
# Error: tool.source: {'code': 'SELECT 1', 'file': 'query.sql'} is not valid under any of the given schemas
tool:
  name: my_tool
  source:
    code: "SELECT 1"
    file: "query.sql"  # Can't have both
```

Fix:
```yaml
tool:
  name: my_tool
  source:
    code: "SELECT 1"  # Use either code or file
```

### Invalid Language

```yaml
# Error: 'javascript' is not one of ['sql', 'python']
tool:
  name: my_tool
  language: javascript  # Invalid
  source:
    code: "console.log('hello')"
```

Fix:
```yaml
tool:
  name: my_tool
  language: python  # Use 'sql' or 'python'
  source:
    code: "print('hello')"
```

## Validation vs Linting

MXCP separates structural checks from quality checks:

### Validation (`mxcp validate`)
Checks structural correctness - fails on errors:
- Valid YAML syntax
- Valid endpoint type (tool, resource, or prompt)
- Valid type and format values
- Valid parameter names
- Source file existence
- Required parameter descriptions

### Linting (`mxcp lint`)
Checks metadata quality - provides suggestions:
- Missing endpoint descriptions
- Missing return type descriptions
- Missing examples on parameters
- Missing default values
- Missing test cases
- Missing tags
- Missing behavioral annotations (for tools)

Use both: `mxcp validate && mxcp lint`

## CI/CD Integration

### GitHub Actions

```yaml
name: Validate
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
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
