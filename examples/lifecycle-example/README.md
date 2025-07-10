# MXCP Lifecycle Commands Example

This example demonstrates the new lifecycle management commands in MXCP, which help standardize and simplify common development workflows.

## Overview

The lifecycle commands feature allows you to define common development tasks in your `mxcp-site.yml` file and run them with simple commands. This eliminates the need for scattered scripts and provides a consistent interface for all team members.

## Available Commands

### Setup Commands

Initialize your project with all required dependencies:

```bash
# Run all setup commands
mxcp dev setup

# Preview what would be executed
mxcp dev setup --dry-run

# Show command output in real-time
mxcp dev setup --verbose
```

### Test Commands

Run tests at different levels:

```bash
# Run quick tests (default)
mxcp dev test

# Run full test suite
mxcp dev test --level full

# Run only unit tests
mxcp dev test --level unit

# Preview test commands
mxcp dev test --level full --dry-run
```

### Deploy Commands

Deploy to different environments:

```bash
# Deploy locally
mxcp dev deploy --target local

# Deploy to staging (requires STAGING_HOST and DOCKER_REGISTRY env vars)
mxcp dev deploy --target staging

# Deploy to production (requires AWS credentials)
mxcp dev deploy --target production

# Preview deployment steps
mxcp dev deploy --target production --dry-run
```

### Custom Commands

Run project-specific commands:

```bash
# Generate synthetic test data
mxcp dev run generate-data

# Download and anonymize production data
mxcp dev run download-data

# Generate test coverage report
mxcp dev run coverage

# Clean up temporary files
mxcp dev run clean

# Validate project configuration
mxcp dev run validate

# List all available commands
mxcp dev list
```

## Configuration Structure

The lifecycle configuration in `mxcp-site.yml` has the following structure:

```yaml
lifecycle:
  setup:
    description: "Description of setup process"
    commands:
      - command: "command to execute"
        name: "Human-friendly name"
        condition: "if_not_exists:path/to/file"  # Optional
  
  test:
    light:
      description: "Quick tests"
      commands: [...]
    full:
      description: "All tests"
      commands: [...]
    unit:
      description: "Unit tests only"
      commands: [...]
  
  deploy:
    targets:
      target_name:
        description: "Deployment description"
        commands: [...]
        environment:
          required: ["ENV_VAR1", "ENV_VAR2"]  # Required env vars
  
  custom:
    command_name:
      description: "Custom command description"
      commands: [...]
```

## Features

### 1. Cross-Platform Compatibility
Commands work on Windows, macOS, and Linux. The tool automatically handles shell differences.

### 2. Conditional Execution
Use `condition: "if_not_exists:path"` to skip commands if certain files/directories exist:

```yaml
- command: "dbt deps"
  name: "Install dbt dependencies"
  condition: "if_not_exists:dbt_packages"
```

### 3. Environment Variable Validation
Specify required environment variables for deployment targets:

```yaml
environment:
  required: ["AWS_REGION", "AWS_ACCOUNT_ID"]
```

### 4. Progress Reporting
Commands show progress with clear output:

```
Initialize project dependencies and environment

[1/4] Install Python dependencies
Running... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%

[2/4] Install dbt dependencies - Skipped (condition: dbt_packages exists)

[3/4] Load seed data
Running... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%
```

### 5. Dry Run Mode
Preview commands without executing them:

```bash
mxcp dev deploy --target production --dry-run
```

Output:
```
Deploy to AWS App Runner

[1/5] Pre-deployment checks
[DRY RUN] Would execute: ./scripts/pre_deploy_checks.sh

[2/5] Login to ECR
[DRY RUN] Would execute: aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_REGISTRY
```

## Best Practices

1. **Use descriptive names**: Give each command a clear `name` field for better progress reporting
2. **Group related commands**: Use the `custom` section for project-specific workflows
3. **Document requirements**: Always specify required environment variables
4. **Add conditions**: Use conditions to make commands idempotent
5. **Test with dry-run**: Always preview deployment commands before executing

## Migration Guide

If you have existing scripts, migrate them to lifecycle commands:

### Before (scattered scripts):
```bash
./scripts/setup.sh
./scripts/test-light.sh
./deploy/deploy-prod.sh
```

### After (unified interface):
```bash
mxcp dev setup
mxcp dev test --level light
mxcp dev deploy --target production
```

## Troubleshooting

### Command not found
```
Error: No lifecycle configuration found in mxcp-site.yml
```
**Solution**: Add a `lifecycle:` section to your `mxcp-site.yml`

### Missing environment variables
```
Error: Missing required environment variables: AWS_REGION, AWS_ACCOUNT_ID
```
**Solution**: Set the required environment variables before running the command

### Command fails
Check the error output and use `--verbose` flag for more details:
```bash
mxcp dev setup --verbose --debug
```

## Example Project Structure

```
my-mxcp-project/
├── mxcp-site.yml          # Contains lifecycle configuration
├── requirements.txt       # Python dependencies
├── dbt_project.yml       # dbt configuration
├── scripts/
│   ├── setup_database.py
│   ├── generate_synthetic_data.py
│   └── validate_config.py
├── tests/
│   ├── unit/
│   └── integration/
└── tools/
    └── example_tool.py
```

## Next Steps

1. Copy the lifecycle configuration from this example's `mxcp-site.yml`
2. Adapt the commands to your project's needs
3. Run `mxcp dev list` to see all available commands
4. Use `--dry-run` to preview commands before executing
5. Share the configuration with your team for consistent workflows 