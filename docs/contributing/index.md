---
title: "Contributing"
description: "Contribute to MXCP development. Setup, coding standards, testing, and pull request process."
sidebar:
  order: 1
---

Welcome to the MXCP development community! This guide helps you contribute to the project.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- GitHub account
- `uv` package manager

### Development Setup

1. **Fork and Clone**:
   ```bash
   git clone https://github.com/raw-labs/mxcp.git
   cd mxcp
   ```

2. **Install Dependencies**:
   ```bash
   # Install uv
   pip install uv

   # Install with dev dependencies
   uv pip install -e ".[dev]"

   # For all optional features
   uv pip install -e ".[all]"
   ```

## Project Structure

```
mxcp/
├── src/mxcp/          # Main package
│   ├── cli/           # CLI commands
│   ├── config/        # Configuration loading
│   ├── engine/        # DuckDB execution
│   ├── endpoints/     # Endpoint handling
│   ├── auth/          # Authentication
│   ├── audit/         # Audit logging
│   ├── drift/         # Drift detection
│   ├── policy/        # Policy enforcement
│   ├── plugins/       # Plugin system
│   └── server/        # MCP server
├── tests/             # Test suite
│   └── fixtures/      # Test repositories
├── docs/              # Documentation
└── examples/          # Example projects
```

## Development Workflow

### 1. Branch Management

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Or bugfix branch
git checkout -b fix/your-bugfix-name

# Keep up to date
git fetch origin
git rebase origin/main
```

### 2. Code Style

MXCP enforces code quality with automated tools:

- **black**: Code formatting (line-length=100)
- **ruff**: Linting and import sorting
- **mypy**: Static type checking

```bash
# Check all
./check-all.sh

# Auto-fix formatting
./format-all.sh

# Individual tools
uv run black .
uv run ruff check . --fix
uv run mypy .
```

### 3. Testing

```bash
# Run all tests
uv run pytest

# Run specific test
uv run pytest tests/test_cli_lint.py

# With coverage
uv run pytest --cov=mxcp

# Verbose output
uv run pytest -v
```

## Architecture Patterns

### Configuration Loading

```python
# Standard pattern for CLI commands
try:
    site_config = load_site_config()
    user_config = load_user_config(site_config)

    # Business logic
    result = do_work()

except Exception as e:
    output_error(e, json_output, debug)
```

**Why this pattern?**
- Site config defines project requirements and structure
- User config provides personal settings and secrets
- Auto-generation allows projects to work out-of-the-box without requiring manual setup
- CLI layer ownership keeps configuration concerns separate from business logic

### DuckDB Connection Management

```python
# Use DuckDBRuntime for connection pooling
runtime = DuckDBRuntime(database_config, plugins, plugin_config, secrets)

with runtime.get_connection() as session:
    result = session.execute_query_to_dict(sql, params)

# Connection returned to pool
runtime.shutdown()  # For graceful shutdown
```

**Connection Management Details:**
- **CLI commands**: Create their own `DuckDBRuntime` instance for the operation
- **Server mode**: Shared `DuckDBRuntime` with connection pool (default size: 2 × CPU cores)
- **Thread safety**: Each request gets its own connection from the pool
- **Initialization**: Extensions, secrets, and plugins loaded once when pool is created
- **Reload behavior**: Pool gracefully drains and refreshes without downtime
- **Zero-downtime updates**: Database changes are visible to new connections without stopping the service

### Object Lifecycle Management

CLI commands follow a consistent pattern for object construction and destruction:

```python
def cli_command():
    try:
        # Create session with context manager
        with DuckDBSession(user_config, site_config) as session:
            # Use session for operations
            result = session.conn.execute(sql)

        # Session automatically cleaned up here

    except Exception as e:
        output_error(e, json_output, debug)
```

**Key Principles:**
1. **CLI owns objects**: Command functions create and manage all objects
2. **Context managers**: Use `with` statements for resources that need cleanup
3. **Exception safety**: Ensure cleanup happens even if exceptions occur
4. **Explicit cleanup**: Don't rely on garbage collection for resource cleanup

### Error Handling Patterns

Consistent error handling across all commands:

```python
from mxcp.cli.utils import output_error, configure_logging

def cli_command(debug: bool, json_output: bool):
    configure_logging(debug)  # Set up logging first

    try:
        # Command logic
        pass
    except Exception as e:
        # Unified error output
        output_error(e, json_output, debug)
        raise click.Abort()  # Exit with error code
```

### Debug and Logging

- **Early setup**: Configure logging before any operations
- **Consistent levels**: Use standard logging levels (DEBUG, INFO, WARNING, ERROR)
- **Structured output**: Debug info includes full tracebacks when `--debug` is enabled
- **Environment support**: `MXCP_DEBUG=1` environment variable support

### CLI Command Pattern

```python
@click.command(name="command_name")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show debug information")
@click.option("--readonly", is_flag=True, help="Read-only mode")
@track_command_with_timing("command_name")
def command_name(profile, json_output, debug, readonly):
    """Command description."""

    # Environment variable fallback
    if not profile:
        profile = get_env_profile()

    configure_logging(debug)

    try:
        site_config = load_site_config()
        user_config = load_user_config(site_config)

        result = do_work()
        output_result(result, json_output, debug)

    except Exception as e:
        output_error(e, json_output, debug)
```

### JSON Output Format

```json
// Success
{
  "status": "ok",
  "result": {}
}

// Error
{
  "status": "error",
  "error": "Error message",
  "traceback": "Full traceback (if --debug)"
}
```

## Test Fixtures

Each test has its own complete repository fixture:

```
tests/
├── fixtures/
│   ├── test_feature/
│   │   ├── mxcp-site.yml
│   │   ├── mxcp-config.yml
│   │   ├── tools/
│   │   ├── resources/
│   │   └── sql/
│   └── test_other/
│       └── ...
├── test_feature.py
└── test_other.py
```

### Test Pattern

```python
@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(
        Path(__file__).parent / "fixtures" / "test_name" / "mxcp-config.yml"
    )

@pytest.fixture
def test_repo_path():
    return Path(__file__).parent / "fixtures" / "test_name"

def test_something(test_repo_path):
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        result = function_under_test()
        assert result == expected
    finally:
        os.chdir(original_dir)
```

### Key Testing Principles

1. **Repository context**: Tests must `chdir` to the test repository fixture directory
2. **Config isolation**: Each test uses its own config files via `MXCP_CONFIG` environment variable
3. **Complete fixtures**: Include all necessary files (site config, user config, endpoints, SQL)
4. **Cleanup**: Always restore the original working directory using try/finally
5. **Independence**: Tests should not depend on each other or share state

## Pull Request Process

### Before Submitting

1. Follow code style guidelines
2. Run all tests and fix failures
3. Update documentation if needed
4. Rebase on main

### Creating the PR

1. Use the PR template
2. Write clear title and description
3. Link related issues
4. Request review from maintainers

### During Review

1. Address review comments promptly
2. Keep PR up to date with main
3. Squash commits if requested

### After Approval

1. Wait for CI to pass
2. Address final comments
3. Maintainers will merge

## Release Process

MXCP uses automated CD via GitHub Actions.

### Version Format

| Type | Git Tag | pyproject.toml | User Install |
|------|---------|----------------|--------------|
| Stable | `v1.0.0` | `1.0.0` | `pip install mxcp` |
| RC | `v1.0.0rc1` | `1.0.0rc1` | `pip install --pre mxcp` |
| Beta | `v1.0.0b1` | `1.0.0b1` | `pip install --pre mxcp` |
| Alpha | `v1.0.0a1` | `1.0.0a1` | `pip install --pre mxcp` |

### Creating a Release

```bash
# Using release script (recommended)
./release.sh 1.0.0

# Then push
git push origin main
git push origin v1.0.0
```

### What Happens Automatically

1. Version validation (tag matches pyproject.toml)
2. Package build and validation
3. PyPI publication (using trusted publishing)
4. CDN propagation wait (up to 10 minutes)
5. Docker image build and push to `ghcr.io/raw-labs/mxcp`

### Monitoring the Release

1. Watch GitHub Actions at: `https://github.com/raw-labs/mxcp/actions`
2. Verify on PyPI: `https://pypi.org/project/mxcp/`
3. Test installation:
   ```bash
   # For stable releases
   pip install --upgrade mxcp
   mxcp --version

   # For pre-releases
   pip install --pre --upgrade mxcp
   mxcp --version
   ```

### Typical Release Workflow

A common pattern for major releases:

1. **Alpha** (`1.0.0a1`, `1.0.0a2`) - Early testing, API may change
2. **Beta** (`1.0.0b1`, `1.0.0b2`) - Feature complete, stabilizing
3. **Release Candidate** (`1.0.0rc1`, `1.0.0rc2`) - Final testing before stable
4. **Stable** (`1.0.0`) - Production ready

For minor/patch releases, you can skip pre-releases and go straight to stable.

## Communication

- **Issues**: Bug reports and feature requests
- **Discussions**: General questions and ideas
- **Email**: hello@raw-labs.com
- **Code Review**: GitHub PR reviews

## Getting Help

- Check the documentation
- Search existing issues
- Join community discussions
- Email for private matters

## Code of Conduct

Follow our [Code of Conduct](https://github.com/raw-labs/mxcp/blob/main/CODE_OF_CONDUCT.md). We maintain a welcoming and inclusive community.

## License

MXCP is released under the Business Source License 1.1. See [LICENSE](https://github.com/raw-labs/mxcp/blob/main/LICENSE) for details.

---

Thank you for contributing to MXCP!
