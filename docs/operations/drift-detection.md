---
title: "Drift Detection"
description: "Track schema and endpoint changes across environments. Generate snapshots, detect drift, and integrate with CI/CD."
sidebar:
  order: 5
---

> **Related Topics:** [Testing](/quality/testing) (endpoint tests) | [Configuration](/operations/configuration) (profiles) | [Deployment](/operations/deployment) (CI/CD)

MXCP's drift detection system helps you track changes to your database schema and endpoint definitions across different environments and over time. This is crucial for maintaining consistency, catching unintended changes, and ensuring your AI applications work reliably across development, staging, and production environments.

## What is Drift Detection?

Drift detection compares the current state of your MXCP repository against a previously captured baseline snapshot to identify:

- **Database Schema Changes**: Added, removed, or modified tables and columns
- **Endpoint Changes**: Added, removed, or modified tools, resources, and prompts
- **Validation Changes**: Changes in endpoint validation results
- **Test Changes**: Changes in test results or test definitions

## Why Use Drift Detection?

### Environment Consistency
Ensure your development, staging, and production environments stay in sync:
```bash
# Generate baseline from production
mxcp drift-snapshot --profile prod

# Check if staging matches production
mxcp drift-check --profile staging --baseline prod-snapshot.json
```

### Change Monitoring
Detect unintended changes before they cause issues:
- Schema modifications that break existing endpoints
- Endpoint parameter changes that affect LLM integrations
- Test failures that indicate breaking changes

### Deployment Validation
Verify deployments haven't introduced unexpected changes:
```bash
# Before deployment
mxcp drift-snapshot --profile staging

# After deployment
mxcp drift-check --profile staging
```

### Compliance and Auditing
Track all changes for compliance and debugging:
- Maintain audit trails of schema evolution
- Identify when and what changed between versions
- Ensure changes follow approval processes

## Configuration

Add drift configuration to your `mxcp-site.yml`:

```yaml
mxcp: 1
project: my_project
profile: default

profiles:
  default:
    duckdb:
      path: "db-default.duckdb"
    drift:
      path: "drift-default.json"

  staging:
    duckdb:
      path: "db-staging.duckdb"
    drift:
      path: "drift-staging.json"

  production:
    duckdb:
      path: "db-production.duckdb"
    drift:
      path: "drift-production.json"
```

## Create Baseline

```bash
# Create snapshot for current state
mxcp drift-snapshot --profile production

# Overwrite existing snapshot
mxcp drift-snapshot --profile production --force

# Preview without writing
mxcp drift-snapshot --dry-run
```

This creates a JSON file with:
- Database schema (tables, columns)
- Endpoint definitions
- Validation results
- Test results

## Check for Drift

```bash
# Compare current state to baseline
mxcp drift-check --profile production

# With custom baseline
mxcp drift-check --baseline snapshots/v1.0.0.json

# JSON output for automation
mxcp drift-check --json-output

# Get detailed output
mxcp drift-check --debug

# Read-only database access
mxcp drift-check --readonly
```

Exit codes:
- `0` - No drift detected
- `1` - Drift detected

## Snapshot Structure

A drift snapshot contains comprehensive information about your MXCP repository state:

```json
{
  "version": "1",
  "generated_at": "2025-01-27T10:30:00.000Z",
  "tables": [
    {
      "name": "users",
      "columns": [
        {
          "name": "id",
          "type": "INTEGER",
          "nullable": false
        },
        {
          "name": "email",
          "type": "VARCHAR",
          "nullable": false
        }
      ]
    }
  ],
  "resources": [
    {
      "validation_results": {
        "status": "ok",
        "path": "tools/get_user.yml"
      },
      "test_results": {
        "status": "ok",
        "tests_run": 2,
        "tests": [...]
      },
      "definition": {
        "mxcp": "1",
        "tool": {
          "name": "get_user",
          "description": "Get user by ID"
        }
      }
    }
  ]
}
```

## Drift Report Structure

When drift is detected, you get a detailed report:

```json
{
  "version": "1",
  "generated_at": "2025-01-27T10:35:00.000Z",
  "baseline_snapshot_path": "drift-default.json",
  "has_drift": true,
  "summary": {
    "tables_added": 1,
    "tables_removed": 0,
    "tables_modified": 1,
    "resources_added": 2,
    "resources_removed": 0,
    "resources_modified": 1
  },
  "table_changes": [
    {
      "name": "orders",
      "change_type": "added",
      "columns_added": [...]
    },
    {
      "name": "users",
      "change_type": "modified",
      "columns_added": [
        {
          "name": "created_at",
          "type": "TIMESTAMP",
          "nullable": true
        }
      ]
    }
  ],
  "resource_changes": [
    {
      "path": "tools/new_tool.yml",
      "endpoint": "tool/new_tool",
      "change_type": "added"
    },
    {
      "path": "tools/existing_tool.yml",
      "endpoint": "tool/existing_tool",
      "change_type": "modified",
      "validation_changed": true,
      "test_results_changed": false,
      "definition_changed": true
    }
  ]
}
```

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/drift-check.yml
name: Drift Detection
on: [push, pull_request]

jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install mxcp
      - name: Check for drift
        run: mxcp drift-check --baseline baseline.json
```

The command exits with code 1 if drift is detected, failing the CI check.

### GitLab CI

```yaml
drift-check:
  image: python:3.11
  script:
    - pip install mxcp
    - mxcp drift-check --baseline baseline.json
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

## Use Cases

### Environment Synchronization

Keep multiple environments in sync:

```bash
# Generate production baseline
mxcp drift-snapshot --profile production

# Check if development matches production
mxcp drift-check --profile development --baseline drift-production.json

# Check if staging matches production
mxcp drift-check --profile staging --baseline drift-production.json
```

### Pre-Deployment Validation

Validate changes before deploying:

```bash
# Before making changes
mxcp drift-snapshot --profile staging

# After making changes, check what changed
mxcp drift-check --profile staging

# If drift is acceptable, update baseline
mxcp drift-snapshot --profile staging --force
```

### Schema Evolution Tracking

Track how your schema evolves over time:

```bash
# Tag snapshots with versions
mxcp drift-snapshot --profile production
cp drift-production.json snapshots/v1-snapshot.json

# Later, compare against historical snapshots
mxcp drift-check --baseline snapshots/v1-snapshot.json
```

## JSON Output for Automation

Get machine-readable output for automation:

```bash
# Get JSON output
mxcp drift-check --json-output > drift-report.json

# Process with jq
mxcp drift-check --json-output | jq '.summary'

# Check if drift exists in scripts
if mxcp drift-check --json-output | jq -r '.has_drift' | grep -q true; then
  echo "Drift detected!"
  exit 1
fi
```

## CLI Reference

### drift-snapshot

```
mxcp drift-snapshot [OPTIONS]

Options:
  --profile TEXT    Profile name to use
  --force           Overwrite existing snapshot file
  --dry-run         Show what would be done without writing
  --json-output     Output in JSON format
  --debug           Show detailed debug information
```

### drift-check

```
mxcp drift-check [OPTIONS]

Options:
  --profile TEXT    Profile name to use
  --baseline TEXT   Path to baseline snapshot file
  --json-output     Output in JSON format
  --debug           Show detailed debug information
  --readonly        Open database in read-only mode
```

## Security Considerations

- **Sensitive Data**: Snapshots may contain schema information; store securely
- **Access Control**: Limit who can generate and modify baseline snapshots
- **Encryption**: Encrypt snapshots if they contain sensitive metadata
- **Audit Trails**: Log all drift detection activities for security auditing

## Performance Considerations

- **Large Schemas**: Drift detection time increases with schema size
- **Frequent Checks**: Consider caching for frequently run drift checks
- **CI/CD Optimization**: Run drift checks only on relevant file changes

## Next Steps

- [Testing](/quality/testing) - Endpoint testing
- [Deployment](/operations/deployment) - Production deployment with CI/CD
- [Configuration](/operations/configuration) - Profile configuration
