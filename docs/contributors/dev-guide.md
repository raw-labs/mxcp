---
title: "Development Guide"
description: "Complete guide for contributing to MXCP development including setup, architecture patterns, testing, and pull request process."
keywords:
  - mxcp development
  - contributing to mxcp
  - mxcp development setup
  - python development
  - duckdb development
sidebar_position: 1
slug: /contributors/development
---

# Development Guide

Welcome to the MXCP development community! This guide will help you get started with contributing to the project.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- A GitHub account
- Basic understanding of SQL and YAML
- `uv` package manager (install with `pip install uv`)

### Development Setup

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/raw-labs/mxcp.git
   cd mxcp
   ```
3. Install dependencies using `uv`:
   ```bash
   # Install uv if you haven't already
   pip install uv
   
   # Install MXCP with development dependencies
   uv pip install -e ".[dev]"
   
   # For testing optional features
   uv pip install -e ".[dev,vault]"  # Test Vault integration
   uv pip install -e ".[dev,onepassword]"  # Test 1Password integration
   uv pip install -e ".[all]"  # Everything (includes dev tools)
   ```

   Note: `uv` automatically manages the virtual environment for you, so you don't need to create one manually.

## Architecture Patterns

### Configuration Loading Pattern

MXCP follows a specific configuration loading pattern across all CLI commands:

1. **Site config loaded first**: Always load `mxcp-site.yml` from the repository root first
2. **User config loaded second**: Load `~/.mxcp/config.yml` based on site config requirements
3. **Auto-generation**: User config is optional and auto-generated in memory from site config defaults if missing
4. **CLI layer ownership**: Configuration loading is done at the CLI layer, not in business logic

```python
# Standard pattern used across all CLI commands
try:
    site_config = load_site_config()
    user_config = load_user_config(site_config)  # Generates defaults if needed
    
    # Business logic here
    
except Exception as e:
    output_error(e, json_output, debug)
```

**Why this pattern?**
- Site config defines project requirements and structure
- User config provides personal settings and secrets
- Auto-generation allows projects to work out-of-the-box without requiring manual setup
- CLI layer ownership keeps configuration concerns separate from business logic

### DuckDB Session Management

MXCP manages DuckDB connections:

- **Connection pooling**: MXCP manages a pool of connections for efficient resource usage
- **Graceful reloads**: Connection pool intelligently drains and refreshes without service interruption
- **Thread-safe operations**: Each request gets its own connection from the pool
- **Context manager pattern**: Ensures proper acquisition and return of connections to the pool
- **Zero-downtime updates**: Database changes are visible to new connections without stopping the service

```python
# Modern connection management pattern using DuckDBRuntime
runtime = DuckDBRuntime(database_config, plugins, plugin_config, secrets)

# Get a connection from the pool
with runtime.get_connection() as session:
    # All database operations happen here
    result = session.execute_query_to_dict(sql, params)
    
# Connection automatically returned to pool when context exits

# For graceful shutdown
runtime.shutdown()
```

**Connection Management:**
- **CLI commands**: Create their own `DuckDBRuntime` instance for the operation
- **Server mode**: Shared `DuckDBRuntime` with connection pool (default size: 2 × CPU cores)
- **Thread safety**: Each request gets its own connection from the pool
- **Initialization**: Extensions, secrets, and plugins loaded once when pool is created
- **Reload behavior**: Pool gracefully drains and refreshes without downtime

### Common CLI Patterns

All MXCP CLI commands follow consistent patterns for maintainability and user experience:

#### Standard Command Structure

```python
@click.command(name="command_name")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@click.option("--readonly", is_flag=True, help="Open database connection in read-only mode")
@track_command_with_timing("command_name")  # Analytics tracking
def command_name(profile: Optional[str], json_output: bool, debug: bool, readonly: bool):
    """Command description with examples in docstring."""
    
    # 1. Environment variable fallback
    if not profile:
        profile = get_env_profile()
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")
    
    # 2. Configure logging early
    configure_logging(debug)
    
    try:
        # 3. Load configurations
        site_config = load_site_config()
        user_config = load_user_config(site_config)
        
        # 4. Business logic here
        result = do_work(...)
        
        # 5. Output results consistently
        output_result(result, json_output, debug)
        
    except Exception as e:
        # 6. Error handling with consistent format
        output_error(e, json_output, debug)
```

#### Key Patterns

1. **Environment variable support**: All commands support `MXCP_PROFILE`, `MXCP_DEBUG`, `MXCP_READONLY`
2. **Consistent options**: `--profile`, `--json-output`, `--debug`, `--readonly` across commands
3. **Early logging setup**: Call `configure_logging(debug)` before any operations
4. **Structured output**: Use `output_result()` and `output_error()` for consistent formatting
5. **Analytics tracking**: `@track_command_with_timing()` decorator for usage analytics

#### JSON Output Format

All commands support `--json-output` with standardized format:

```python
# Success response
{
  "status": "ok",
  "result": <command-specific-data>
}

# Error response  
{
  "status": "error",
  "error": "Error message",
  "traceback": "Full traceback (if --debug enabled)"
}
```

## Development Workflow

### 1. Branch Management

- Create a new branch for each feature or bugfix:
  ```bash
  git checkout -b feature/your-feature-name
  # or
  git checkout -b fix/your-bugfix-name
  ```

- Keep your branch up to date with main:
  ```bash
  git fetch origin
  git rebase origin/main
  ```

### 2. Code Style

- Follow PEP 8 guidelines (enforced by `black` and `ruff`)
- Use type hints for all function parameters and return values (checked by `mypy`)
- Write docstrings for all public functions and classes
- Keep lines under 100 characters (enforced by `black` with line-length=100)
- Use meaningful variable and function names
- Import statements are automatically sorted by `ruff`

### 3. Testing

#### Test Fixture Organization

MXCP uses a specific pattern for organizing test fixtures:

- **Per-test fixtures**: Each test has its own fixture directory at `/test/fixtures/{test_name}/`
- **Complete repositories**: Each fixture contains a complete MXCP repository with `mxcp-site.yml` and `mxcp-config.yml`
- **Isolated environments**: Tests use environment variables to point to their specific config files

> 📖 For endpoint testing best practices and writing tests for MXCP endpoints, see the [Quality & Testing Guide](../guides/quality.md).

```python
# Standard test setup pattern
@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    """Point to test-specific config file."""
    os.environ["MXCP_CONFIG"] = str(Path(__file__).parent / "fixtures" / "test_name" / "mxcp-config.yml")

@pytest.fixture
def test_repo_path():
    """Path to the test repository fixture."""
    return Path(__file__).parent / "fixtures" / "test_name"

@pytest.fixture
def test_config(test_repo_path):
    """Load test configuration with proper chdir."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        site_config = load_site_config()
        return load_user_config(site_config)
    finally:
        os.chdir(original_dir)

def test_something(test_repo_path, test_config):
    """Test function with fixture setup."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)  # Critical: change to test repo directory
    try:
        # Test logic here - runs in context of test repository
        result = function_under_test()
        assert result == expected
    finally:
        os.chdir(original_dir)  # Always restore original directory
```

#### Test Directory Structure

```
tests/
├── fixtures/
│   ├── test_name_1/          # Fixture for test_name_1
│   │   ├── mxcp-site.yml     # Test site configuration
│   │   ├── mxcp-config.yml   # Test user configuration  
│   │   ├── tools/            # Test tool definitions
│   │   ├── resources/        # Test resource definitions
│   │   ├── prompts/          # Test prompt definitions
│   │   ├── evals/            # Test evaluation definitions
│   │   ├── python/           # Test Python endpoints
│   │   ├── plugins/          # Test MXCP plugins
│   │   ├── sql/              # Test SQL files
│   │   ├── drift/            # Test drift snapshots
│   │   └── audit/            # Test audit logs
│   ├── test_name_2/          # Fixture for test_name_2
│   │   └── ...
│   └── ...
├── test_name_1.py            # Tests using fixtures/test_name_1/
├── test_name_2.py            # Tests using fixtures/test_name_2/
└── ...
```

#### Key Testing Principles

1. **Repository context**: Tests must `chdir` to the test repository fixture directory
2. **Config isolation**: Each test uses its own config files via `MXCP_CONFIG` environment variable  
3. **Complete fixtures**: Include all necessary files (site config, user config, endpoints, SQL)
4. **Cleanup**: Always restore the original working directory using try/finally
5. **Independence**: Tests should not depend on each other or share state

#### Running Tests

- Write tests for all new features and bugfixes
- Run the test suite:
  ```bash
  uv run pytest
  ```
- Ensure all tests pass before submitting a PR
- Aim for high test coverage

### 4. Documentation

- Update relevant documentation when adding features
- Add docstrings to new functions and classes
- Update examples if they're affected by your changes
- Follow the existing documentation style

## Implementation Details

### Object Lifecycle Management

CLI commands follow a consistent pattern for object construction and destruction:

1. **CLI owns objects**: Command functions create and manage all objects
2. **Context managers**: Use `with` statements for resources that need cleanup
3. **Exception safety**: Ensure cleanup happens even if exceptions occur
4. **Explicit cleanup**: Don't rely on garbage collection for resource cleanup

```python
def cli_command():
    try:
        # Create session with context manager
        with DuckDBSession(user_config, site_config) as session:
            # Use session for operations
            result = session.conn.execute(sql)
            
        # Session automatically cleaned up here
        
    except Exception as e:
        # Error handling
        output_error(e, json_output, debug)
```

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

## Pull Request Process

1. **Before Submitting**
   - Ensure your code follows the style guide
   - Run all tests and fix any failures
   - Update documentation as needed
   - Rebase your branch on main

2. **Creating the PR**
   - Use the PR template provided
   - Write a clear title and description
   - Link any related issues
   - Request review from maintainers

3. **During Review**
   - Address review comments promptly
   - Keep the PR up to date with main
   - Squash commits if requested

4. **After Approval**
   - Wait for CI to pass
   - Address any final comments
   - Maintainers will merge your PR

## Project Structure

```
mxcp/
├── src/              # Source code
│   └── mxcp/        # Main package
│       ├── cli/     # CLI command implementations
│       ├── config/  # Configuration loading and validation
│       ├── engine/  # DuckDB session and execution engine
│       ├── endpoints/ # Endpoint loading and execution
│       ├── auth/    # Authentication and authorization
│       ├── audit/   # Audit logging
│       ├── drift/   # Schema drift detection
│       ├── policy/   # Policy enforcement
│       ├── plugins/ # Plugin system
│       └── server/  # MCP server implementation
├── tests/           # Test suite
│   └── fixtures/    # Test repository fixtures
├── docs/            # Documentation
├── examples/        # Example projects
└── pyproject.toml   # Project configuration
```

## Development Tools

### Code Quality

MXCP uses several tools to maintain code quality. All commands should be run with `uv run` to ensure they use the project's virtual environment:

- **Ruff**: Fast Python linter (replaces isort and adds additional checks)
  ```bash
  # Check for linting issues
  uv run ruff check .
  # Fix auto-fixable issues (including import sorting)
  uv run ruff check . --fix
  # Show what would be fixed without making changes
  uv run ruff check . --diff
  ```

- **Black**: Code formatter
  ```bash
  uv run black .
  # Check without making changes
  uv run black . --check
  # Check with diff output
  uv run black . --check --diff
  ```

- **mypy**: Static type checking
  ```bash
  uv run mypy .
  ```

Run all checks (same as CI):
```bash
# Run all code quality checks
uv run ruff check . && \
uv run black --check --diff . && \
uv run mypy .
```

### Testing

- Use `pytest` for testing (always run with `uv run`)
- Use `pytest-cov` for coverage reports

Run tests:
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_cli_lint.py

# Run tests with coverage
uv run pytest --cov=mxcp

# Run tests with verbose output
uv run pytest -v

# Run tests matching a pattern
uv run pytest -k "test_format"
```

## Communication

- **Issues**: Use GitHub Issues for bug reports and feature requests
- **Discussions**: Use GitHub Discussions for general questions and ideas
- **Email**: Contact hello@raw-labs.com for private matters
- **Code Review**: Use GitHub PR reviews for code-related discussions

## Release Process

1. Version bump in `pyproject.toml`
2. Update CHANGELOG.md
3. Create release tag
4. Build and publish to PyPI

## Getting Help

- Check the [documentation](../../)
- Search existing issues and discussions
- Join our community discussions
- Email hello@raw-labs.com for private matters

## Code of Conduct

Please read and follow our [Code of Conduct](https://github.com/raw-labs/mxcp/blob/main/CODE_OF_CONDUCT.md). We aim to maintain a welcoming and inclusive community.

## License

MXCP is released under the Business Source License 1.1. See [LICENSE](https://github.com/raw-labs/mxcp/blob/main/LICENSE) for details. This license allows for non-production use and will convert to MIT after four years from the first public release.

---

Thank you for contributing to MXCP! Your work helps make the project better for everyone. 
