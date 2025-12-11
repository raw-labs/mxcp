---
title: "Quality Assurance"
description: "MXCP quality tools: validation, testing, linting, and LLM evaluation. Ensure your endpoints are correct, complete, and AI-friendly."
sidebar:
  order: 1
---

> **Related Topics:** [Quickstart](/getting-started/quickstart#validate-your-project) (first validation) | [CLI Reference](/reference/cli) (command options) | [Common Tasks](/reference/common-tasks#testing--quality) (quick how-to)

MXCP provides a comprehensive 4-layer quality framework to ensure your endpoints are production-ready. This section covers validation, testing, linting, and LLM evaluation.

## Quality Layers

```
┌─────────────────────────────────────────────────────────┐
│                    mxcp validate                         │
│  Structural correctness: YAML syntax, required fields   │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                     mxcp test                           │
│  Functional correctness: Execution, assertions          │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                     mxcp lint                           │
│  Metadata quality: Descriptions, examples, best practices│
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    mxcp evals                           │
│  AI behavior: LLM interaction, safety, correctness      │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Validate all endpoints
mxcp validate

# Run tests
mxcp test

# Check metadata quality
mxcp lint

# Run LLM evaluations
mxcp evals
```

## Topics

### [Validation](validation)
Verify endpoint structure and syntax:
- YAML correctness
- Required fields
- Type definitions
- File references

### [Testing](testing)
Test endpoint functionality:
- Test case definitions
- Assertion types
- Policy testing
- CI/CD integration

### [Linting](linting)
Improve AI comprehension:
- Description quality
- Example coverage
- Best practice checks
- Auto-suggestions

### [Evals](evals)
Test AI behavior:
- LLM tool usage
- Safety verification
- Permission testing
- Multi-model support

## Workflow Integration

### Development

```bash
# After creating/modifying an endpoint
mxcp validate  # Check structure
mxcp test      # Verify functionality
mxcp lint      # Improve metadata
```

### Pre-Commit

```bash
# Run all quality checks
mxcp validate && mxcp test && mxcp lint
```

### CI/CD Pipeline

```yaml
# .github/workflows/quality.yml
name: Quality Checks
on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install mxcp
      - run: mxcp validate
      - run: mxcp test --json-output > test-results.json
      - run: mxcp lint --json-output > lint-results.json
```

### Pre-Production

```bash
# Before deployment
mxcp validate
mxcp test
mxcp lint
mxcp evals  # Test AI behavior
mxcp drift-snapshot  # Create baseline
```

## Best Practices

### 1. Validate Early
Run `mxcp validate` frequently during development.

### 2. Write Tests
Add tests to every endpoint definition.

### 3. Address Lint Issues
Fix warnings to improve AI understanding.

### 4. Test AI Behavior
Use evals for critical endpoints.

### 5. Automate
Include quality checks in CI/CD.

## Command Reference

### Validation

```bash
mxcp validate              # Validate all
mxcp validate --json-output # JSON output
```

### Testing

```bash
mxcp test                  # Run all tests
mxcp test --tool my_tool   # Test specific tool
mxcp test --json-output    # JSON output
```

### Linting

```bash
mxcp lint                  # Check all
mxcp lint --tool my_tool   # Check specific tool
mxcp lint --json-output    # JSON output
```

### Evals

```bash
mxcp evals                 # Run all evals
mxcp evals --suite my-eval # Run specific suite
mxcp evals --model gpt-4   # Use specific model
```

## Next Steps

- [Validation](validation) - Structural checks
- [Testing](testing) - Functional testing
- [Linting](linting) - Metadata quality
- [Evals](evals) - AI behavior testing
