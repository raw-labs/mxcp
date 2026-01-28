---
title: "Contributing"
description: "Contribute to MXCP development. Setup, coding standards, testing, and pull request process."
sidebar:
  order: 1
---

Welcome to the MXCP development community! This guide helps you contribute to the project.

## Your First Contribution

New to MXCP? Here's how to get started:

1. **Find an issue** - Look for issues labeled `good first issue` or `help wanted`
2. **Comment on the issue** - Let maintainers know you're working on it
3. **Fork and clone** - Set up your development environment
4. **Make your changes** - Follow the guidelines below
5. **Submit a PR** - Request review from maintainers

Common contribution types:
- **Bug fixes** - Fix issues reported by users
- **Documentation** - Improve guides, fix typos, add examples
- **Features** - Add new functionality (discuss first in an issue)
- **Tests** - Improve test coverage

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Git
- GitHub account
- Basic understanding of SQL and YAML
- `uv` package manager

### Installation

1. **Fork and clone**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/mxcp.git
   cd mxcp
   ```

2. **Install dependencies**:
   ```bash
   # Install uv if you haven't already
   pip install uv

   # Install with dev dependencies
   uv pip install -e ".[dev]"
   ```

   `uv` automatically manages the virtual environment - no need to create one manually.

3. **Install optional features** (for testing specific integrations):
   ```bash
   # Test Vault integration
   uv pip install -e ".[dev,vault]"

   # Test 1Password integration
   uv pip install -e ".[dev,onepassword]"

   # Everything (all optional features + dev tools)
   uv pip install -e ".[all]"
   ```

### Project Structure

```
mxcp/
├── src/mxcp/              # Main package
│   ├── plugins/           # Plugin system
│   ├── runtime/           # Runtime initialization
│   ├── sdk/               # Core SDK modules
│   │   ├── audit/         # Audit logging
│   │   ├── auth/          # Authentication
│   │   ├── core/          # Core utilities
│   │   ├── duckdb/        # DuckDB execution engine
│   │   ├── evals/         # Evaluations
│   │   ├── executor/      # Query execution
│   │   ├── mcp/           # MCP protocol
│   │   ├── policy/        # Policy enforcement
│   │   ├── telemetry/     # Telemetry
│   │   └── validator/     # Validation
│   └── server/            # MCP server
│       ├── interfaces/
│       │   ├── cli/       # CLI commands
│       │   └── server/    # HTTP/SSE server
│       ├── definitions/   # Endpoint definitions
│       └── services/      # Business logic
├── tests/                 # Test suite
│   └── server/fixtures/   # Test repositories
├── docs/                  # Documentation
└── examples/              # Example projects
```

## Development Workflow

### 1. Branch Management

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Or bugfix branch
git checkout -b fix/your-bugfix-name

# Keep up to date with main
git fetch origin
git rebase origin/main
```

### 2. Code Style

MXCP enforces code quality with automated tools:

- **black**: Code formatting (line-length=100)
- **ruff**: Linting and import sorting
- **mypy**: Static type checking

Guidelines:
- Follow PEP 8 (enforced by black and ruff)
- Use type hints for all function parameters and return values
- Write docstrings for all public functions and classes
- Keep lines under 100 characters
- Use meaningful variable and function names

```bash
# Check all (recommended before committing)
./check-all.sh

# Auto-fix formatting
./format-all.sh
```

Individual tools:
```bash
# Ruff - check for issues
uv run ruff check .

# Ruff - auto-fix issues
uv run ruff check . --fix

# Ruff - show diff without changing
uv run ruff check . --diff

# Black - format code
uv run black .

# Black - check without changing
uv run black . --check --diff

# Mypy - type checking
uv run mypy .
```

### 3. Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_cli_lint.py

# Run tests matching a pattern
uv run pytest -k "test_format"

# With coverage
uv run pytest --cov=mxcp

# Verbose output
uv run pytest -v
```

### 4. Documentation

- Update relevant docs when adding features
- Add docstrings to new functions and classes
- Update examples if affected by your changes
- Follow existing documentation style

## Maintainer Guides

Internal implementation notes for contributors working on core subsystems:

- [Auth & OAuth Internals (Maintainers)](/contributing/auth-oauth)

## Test Fixtures

Each test has its own complete repository fixture. This ensures test isolation and reproducibility.

> For endpoint testing best practices, see the [Testing Guide](/quality/testing).

### Fixture Structure

```
tests/
├── server/
│   ├── fixtures/
│   │   ├── test-repo/              # Example fixture directory
│   │   │   ├── mxcp-site.yml       # Site configuration
│   │   │   ├── mxcp-config.yml     # User configuration
│   │   │   ├── tools/              # Tool definitions
│   │   │   ├── resources/          # Resource definitions
│   │   │   ├── prompts/            # Prompt definitions
│   │   │   ├── evals/              # Evaluation definitions
│   │   │   ├── python/             # Python endpoints
│   │   │   ├── plugins/            # MXCP plugins
│   │   │   ├── sql/                # SQL files
│   │   │   ├── drift/              # Drift snapshots
│   │   │   └── audit/              # Audit logs
│   │   └── validation/             # Another fixture
│   │       └── ...
│   ├── test_cli.py
│   └── test_validation.py
├── sdk/                            # SDK tests
└── conftest.py                     # Shared fixtures
```

### Test Pattern

```python
@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    """Point to test-specific config file."""
    os.environ["MXCP_CONFIG"] = str(
        Path(__file__).parent / "fixtures" / "test-repo" / "mxcp-config.yml"
    )

@pytest.fixture
def test_repo_path():
    """Path to the test repository fixture."""
    return Path(__file__).parent / "fixtures" / "test-repo"

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
    """Test with fixture setup."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)  # Critical: change to test repo
    try:
        result = function_under_test()
        assert result == expected
    finally:
        os.chdir(original_dir)  # Always restore
```

### Key Testing Principles

1. **Repository context**: Tests must `chdir` to the fixture directory
2. **Config isolation**: Each test uses its own config via `MXCP_CONFIG`
3. **Complete fixtures**: Include all necessary files (configs, endpoints, SQL)
4. **Cleanup**: Always restore original directory using try/finally
5. **Independence**: Tests should not depend on each other

## Pull Request Process

### Before Submitting

1. Follow code style guidelines (`./check-all.sh` passes)
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

## Architecture Patterns

This section covers internal patterns for contributors working on core MXCP code.

### Configuration Loading

```python
# Standard pattern for CLI commands
try:
    site_config = load_site_config()
    user_config = load_user_config(site_config)

    result = do_work()

except Exception as e:
    output_error(e, json_output, debug)
```

**Why this pattern?**
- Site config defines project requirements
- User config provides personal settings and secrets
- Auto-generation allows projects to work out-of-the-box
- CLI layer owns configuration loading

### DuckDB Connection Management

```python
# Use DuckDBRuntime for connection pooling
runtime = DuckDBRuntime(database_config, plugins, plugin_config, secrets)

with runtime.get_connection() as session:
    result = session.execute_query_to_dict(sql, params)

runtime.shutdown()  # For graceful shutdown
```

**Connection details:**
- CLI commands: Create their own `DuckDBRuntime` instance
- Server mode: Shared runtime with pool (default: 2 × CPU cores)
- Thread safety: Each request gets its own connection from pool
- Reload: Pool drains and refreshes without downtime

### CLI Command Pattern

```python
@click.command(name="command_name")
@click.option("--profile", help="Profile name")
@click.option("--json-output", is_flag=True, help="JSON output")
@click.option("--debug", is_flag=True, help="Debug info")
@click.option("--readonly", is_flag=True, help="Read-only mode")
@track_command_with_timing("command_name")
def command_name(profile, json_output, debug, readonly):
    """Command description."""

    # Environment variable fallback
    if not profile:
        profile = get_env_profile()
    if not readonly:
        readonly = get_env_flag("MXCP_READONLY")

    configure_logging(debug)

    try:
        site_config = load_site_config()
        user_config = load_user_config(site_config)

        result = do_work()
        output_result(result, json_output, debug)

    except Exception as e:
        output_error(e, json_output, debug)
```

**Key patterns:**
- Environment variable support: `MXCP_PROFILE`, `MXCP_DEBUG`, `MXCP_READONLY`
- Consistent options: `--profile`, `--json-output`, `--debug`, `--readonly`
- Early logging setup before any operations
- Structured output via `output_result()` and `output_error()`

### JSON Output Format

```json
// Success
{"status": "ok", "result": {}}

// Error
{"status": "error", "error": "Message", "traceback": "..."}
```

### Error Handling

```python
from mxcp.server.interfaces.cli.utils import output_error, configure_logging

def cli_command(debug: bool, json_output: bool):
    configure_logging(debug)  # Set up logging first

    try:
        # Command logic
        pass
    except Exception as e:
        output_error(e, json_output, debug)
        raise click.Abort()
```

## Release Process

MXCP uses automated CD via GitHub Actions.

### Version Format

MXCP follows [PEP 440](https://peps.python.org/pep-0440/) for version numbers:
- **Git tags**: Include `v` prefix (`v1.0.0`, `v1.0.0rc1`)
- **Python package** (pyproject.toml): No `v` prefix (`1.0.0`, `1.0.0rc1`)

| Type | Git Tag | pyproject.toml | User Install |
|------|---------|----------------|--------------|
| Stable | `v1.0.0` | `1.0.0` | `pip install mxcp` |
| RC | `v1.0.0rc1` | `1.0.0rc1` | `pip install --pre mxcp` |
| Beta | `v1.0.0b1` | `1.0.0b1` | `pip install --pre mxcp` |
| Alpha | `v1.0.0a1` | `1.0.0a1` | `pip install --pre mxcp` |

Users must use `--pre` to install pre-release versions (or specify exact version: `pip install mxcp==1.0.0rc1`).

### Creating a Release

**Using the release script (recommended):**
```bash
./release.sh 1.0.0      # Stable
./release.sh 1.0.0rc1   # Pre-release

# Then push
git push origin main
git push origin v1.0.0
```

**Manual release:**
```bash
# 1. Update version in pyproject.toml
# 2. Commit
git add pyproject.toml
git commit -m "Release v1.0.0"
git push

# 3. Create and push tag
git tag v1.0.0
git push origin v1.0.0
```

### What Happens Automatically

1. Version validation (tag matches pyproject.toml)
2. Package build and validation
3. PyPI publication (trusted publishing)
4. CDN propagation wait (up to 10 minutes)
5. Docker image build and push to `ghcr.io/raw-labs/mxcp`

### Typical Release Workflow

```bash
# Alpha testing
./release.sh 1.0.0a1 && git push origin main v1.0.0a1

# Beta (feature complete)
./release.sh 1.0.0b1 && git push origin main v1.0.0b1

# Release candidate (final testing)
./release.sh 1.0.0rc1 && git push origin main v1.0.0rc1

# Found bug, fix and new RC
./release.sh 1.0.0rc2 && git push origin main v1.0.0rc2

# Stable release
./release.sh 1.0.0 && git push origin main v1.0.0
```

For minor/patch releases, skip pre-releases and go straight to stable.

### Verifying the Release

```bash
# Monitor: https://github.com/raw-labs/mxcp/actions
# Verify: https://pypi.org/project/mxcp/

# Test installation
pip install --upgrade mxcp      # Stable
pip install --pre --upgrade mxcp  # Pre-release
mxcp --version
```

## Communication

- **Issues**: Bug reports and feature requests
- **Discussions**: General questions and ideas
- **Email**: hello@raw-labs.com
- **Code Review**: GitHub PR reviews

## Getting Help

- Check the [documentation](/)
- Search existing issues
- Join community discussions
- Email for private matters

## Code of Conduct

Follow our [Code of Conduct](https://github.com/raw-labs/mxcp/blob/main/CODE_OF_CONDUCT.md). We maintain a welcoming and inclusive community.

## License

MXCP is released under the Business Source License 1.1. See [LICENSE](https://github.com/raw-labs/mxcp/blob/main/LICENSE) for details. This license allows for non-production use and will convert to MIT after four years from the first public release.

---

Thank you for contributing to MXCP!
