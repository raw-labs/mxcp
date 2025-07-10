---
sidebar_position: 7
---

# Lifecycle Commands

Standardize and automate your development workflows with MXCP's lifecycle management commands.

## Overview

Lifecycle commands provide a unified interface for common development tasks like setup, testing, and deployment. Instead of maintaining scattered scripts across your project, you can define all workflows in your `mxcp-site.yml` and run them with simple commands.

## Benefits

- **Consistency**: All team members use the same commands
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Self-documenting**: Commands are defined with descriptions
- **Discoverable**: List all available commands with `mxcp dev list`
- **Safe**: Preview commands with `--dry-run` before executing

## Quick Start

1. Add a `lifecycle` section to your `mxcp-site.yml`:

```yaml
lifecycle:
  setup:
    description: "Initialize project"
    commands:
      - "pip install -r requirements.txt"
      - "dbt deps"
```

2. Run the setup:

```bash
mxcp dev setup
```

## Command Structure

### Setup Command

Initialize your project environment:

```yaml
lifecycle:
  setup:
    description: "Initialize project dependencies and environment"
    commands:
      - command: "pip install -r requirements.txt"
        name: "Install Python dependencies"
      - command: "dbt deps"
        name: "Install dbt packages"
        condition: "if_not_exists:dbt_packages"
```

Run with:
```bash
mxcp dev setup [--dry-run] [--verbose] [--debug]
```

### Test Commands

Define multiple test levels:

```yaml
lifecycle:
  test:
    light:
      description: "Quick validation tests (< 1 minute)"
      commands:
        - "mxcp test"
        - "dbt test --select tag:quick"
    
    full:
      description: "Comprehensive test suite"
      commands:
        - "mxcp test"
        - "dbt test"
        - "python -m pytest"
    
    unit:
      description: "Unit tests only"
      commands:
        - "python -m pytest tests/unit"
```

Run with:
```bash
mxcp dev test [--level light|full|unit] [--dry-run] [--verbose]
```

### Deploy Commands

Configure deployment targets:

```yaml
lifecycle:
  deploy:
    targets:
      local:
        description: "Deploy locally with Docker"
        commands:
          - "docker build -t myapp ."
          - "docker run -p 8000:8000 myapp"
      
      production:
        description: "Deploy to AWS"
        commands:
          - "./scripts/deploy.sh"
        environment:
          required: ["AWS_REGION", "AWS_ACCOUNT_ID"]
```

Run with:
```bash
mxcp dev deploy --target local|production [--dry-run] [--verbose]
```

### Custom Commands

Define project-specific workflows:

```yaml
lifecycle:
  custom:
    generate-data:
      description: "Generate test data"
      commands:
        - "python scripts/generate_data.py"
    
    clean:
      description: "Clean temporary files"
      commands:
        - "rm -rf target/ logs/"
        - "find . -name __pycache__ -delete"
```

Run with:
```bash
mxcp dev run generate-data [--dry-run] [--verbose]
```

## Advanced Features

### Conditional Execution

Skip commands based on file/directory existence:

```yaml
commands:
  - command: "dbt seed"
    name: "Load seed data"
    condition: "if_not_exists:seeds/.loaded"
```

### Named Commands

Provide friendly names for better progress reporting:

```yaml
commands:
  - command: "aws ecr get-login-password | docker login"
    name: "Login to ECR"
```

### Environment Variable Validation

Ensure required variables are set before deployment:

```yaml
deploy:
  targets:
    production:
      environment:
        required: ["AWS_REGION", "API_KEY"]
```

## Command Line Options

All lifecycle commands support these options:

- `--dry-run`: Preview commands without executing them
- `--verbose` or `-v`: Show command output in real-time
- `--debug`: Enable debug logging

## Example Configuration

Here's a complete example:

```yaml
lifecycle:
  setup:
    description: "Initialize development environment"
    commands:
      - command: "pip install -r requirements.txt"
        name: "Install Python dependencies"
      - command: "dbt deps"
        name: "Install dbt dependencies"
        condition: "if_not_exists:dbt_packages"
      - command: "dbt seed"
        name: "Load seed data"
  
  test:
    light:
      description: "Run quick tests"
      commands:
        - "mxcp test"
    full:
      description: "Run all tests"
      commands:
        - "mxcp test"
        - "dbt test"
        - "python -m pytest"
  
  deploy:
    targets:
      staging:
        description: "Deploy to staging"
        commands:
          - "docker build -t app:staging ."
          - "docker push app:staging"
        environment:
          required: ["DOCKER_REGISTRY"]
  
  custom:
    validate:
      description: "Validate configuration"
      commands:
        - "mxcp lint"
        - "dbt compile"
```

## Best Practices

1. **Start Simple**: Begin with basic setup and test commands
2. **Use Descriptions**: Make commands self-documenting
3. **Name Complex Commands**: Use the `name` field for clarity
4. **Test with Dry Run**: Always preview deployments first
5. **Document Requirements**: List required environment variables
6. **Make Commands Idempotent**: Use conditions to skip unnecessary work

## Cross-Platform Compatibility

The lifecycle commands automatically handle platform differences:

- **Windows**: Uses `cmd.exe` or PowerShell
- **macOS/Linux**: Uses `/bin/bash` if available
- **Path Separators**: Handled automatically

## Troubleshooting

### No lifecycle configuration found
Add a `lifecycle:` section to your `mxcp-site.yml`

### Command not found
Check that the command exists and is in your PATH

### Missing environment variables
Set required variables or use a `.env` file

### Command fails
Use `--verbose` and `--debug` flags for more information

## Migration from Scripts

Replace scattered scripts with lifecycle commands:

**Before:**
```bash
./scripts/setup.sh
./scripts/run-tests.sh
./deploy/deploy-prod.sh
```

**After:**
```bash
mxcp dev setup
mxcp dev test
mxcp dev deploy --target production
```

## See Also

- [Configuration Guide](/docs/guides/configuration) - Learn about MXCP configuration
- [CLI Reference](/docs/reference/cli) - Complete CLI documentation
- Example: [lifecycle-example](/examples/lifecycle-example) 