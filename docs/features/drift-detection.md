---
title: "Drift Detection"
description: "Monitor and track changes to database schema and endpoints across environments with MXCP's drift detection system. Maintain consistency and catch unintended changes."
keywords:
  - mxcp drift detection
  - schema monitoring
  - database changes
  - endpoint changes
  - environment consistency
  - change tracking
sidebar_position: 3
slug: /features/drift-detection
---

# Drift Detection

MXCP's drift detection system helps you monitor and track changes to your database schema and endpoint definitions across different environments and over time. This is crucial for maintaining consistency, catching unintended changes, and ensuring your AI applications work reliably across development, staging, and production environments.

## What is Drift Detection?

Drift detection compares the current state of your MXCP repository against a previously captured baseline snapshot to identify:

- **Database Schema Changes**: Added, removed, or modified tables and columns
- **Endpoint Changes**: Added, removed, or modified tools, resources, and prompts
- **Validation Changes**: Changes in endpoint validation results
- **Test Changes**: Changes in test results or test definitions

## Why is Drift Detection Important?

### 1. Environment Consistency
Ensure your development, staging, and production environments stay in sync:
```bash
# Generate baseline from production
mxcp drift-snapshot --profile prod

# Check if staging matches production
mxcp drift-check --profile staging --baseline prod-snapshot.json
```

### 2. Change Monitoring
Detect unintended changes before they cause issues:
- Schema modifications that break existing endpoints
- Endpoint parameter changes that affect LLM integrations
- Test failures that indicate breaking changes

### 3. Deployment Validation
Verify deployments haven't introduced unexpected changes:
```bash
# Before deployment
mxcp drift-snapshot --profile staging

# After deployment
mxcp drift-check --profile staging
```

### 4. Compliance and Auditing
Track all changes for compliance and debugging:
- Maintain audit trails of schema evolution
- Identify when and what changed between versions
- Ensure changes follow approval processes

## Getting Started

### 1. Configure Drift Detection

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

### 2. Generate Your First Snapshot

Create a baseline snapshot of your current state:

```bash
# Generate snapshot for default profile
mxcp drift-snapshot

# Generate snapshot for specific profile
mxcp drift-snapshot --profile production
```

This creates a JSON file containing:
- Complete database schema (tables, columns, types)
- All endpoint definitions
- Validation results for each endpoint
- Test results for each endpoint

### 3. Check for Drift

Compare current state against the baseline:

```bash
# Check against default baseline
mxcp drift-check

# Check against specific baseline file
mxcp drift-check --baseline path/to/baseline.json

# Get detailed output
mxcp drift-check --debug
```

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
          "description": "Get user by ID",
          ...
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

## Common Use Cases

### 1. Environment Synchronization

Keep multiple environments in sync:

```bash
# Generate production baseline
mxcp drift-snapshot --profile production

# Check if development matches production
mxcp drift-check --profile development --baseline drift-production.json

# Check if staging matches production
mxcp drift-check --profile staging --baseline drift-production.json
```

### 2. Pre-Deployment Validation

Validate changes before deploying:

```bash
# Before making changes
mxcp drift-snapshot --profile staging

# After making changes, check what changed
mxcp drift-check --profile staging

# If drift is acceptable, update baseline
mxcp drift-snapshot --profile staging --force
```

### 3. Continuous Integration

Integrate drift detection into your CI/CD pipeline:

```yaml
# .github/workflows/drift-check.yml
name: Drift Detection
on: [push, pull_request]

jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - name: Install MXCP
        run: pip install mxcp
      - name: Check for drift
        run: |
          mxcp drift-check --baseline baseline-snapshot.json
          if [ $? -eq 1 ]; then
            echo "Drift detected! Review changes before merging."
            exit 1
          fi
```

### 4. Schema Evolution Tracking

Track how your schema evolves over time:

```bash
# Tag snapshots with versions
mxcp drift-snapshot --profile production
cp drift-production.json snapshots/v1-snapshot.json

# Later, compare against historical snapshots
mxcp drift-check --baseline snapshots/v1-snapshot.json
```

## Advanced Features

### 1. Custom Baseline Paths

Use different baselines for different comparisons:

```bash
# Compare against a specific environment
mxcp drift-check --baseline environments/production-baseline.json

# Compare against a specific version
mxcp drift-check --baseline versions/v2.1.0-baseline.json

# Compare against a feature branch baseline
mxcp drift-check --baseline feature-baselines/new-feature.json
```

### 2. JSON Output for Automation

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

## Security Considerations

- **Sensitive Data**: Snapshots may contain schema information; store securely
- **Access Control**: Limit who can generate and modify baseline snapshots
- **Encryption**: Encrypt snapshots if they contain sensitive metadata
- **Audit Trails**: Log all drift detection activities for security auditing

## Performance Considerations

- **Large Schemas**: Drift detection time increases with schema size
- **Frequent Checks**: Consider caching for frequently run drift checks
