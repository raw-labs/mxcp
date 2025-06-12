# MXCP LSP Tests

This directory contains comprehensive tests for the MXCP Language Server Protocol (LSP) implementation. The tests are organized into two main categories: **unit tests** and **end-to-end (e2e) tests**.

## Overview

The MXCP LSP server provides language server features for YAML files containing SQL code, including:
- **Completion**: SQL completions for table names, column names, and functions
- **Diagnostics**: SQL syntax error detection and validation
- **Semantic Tokens**: Syntax highlighting for SQL code within YAML files

## Directory Structure

```
tests/lsp/
├── README.md              # This file
├── fixtures/              # Test fixtures and configurations
│   └── e2e-config/       # Isolated test environment
│       ├── mxcp-site.yml # Test project configuration
│       ├── tool_with_inlined_code.yml
│       ├── tool_with_file_code.yml
│       └── tool_with_invalid_sql.yml
├── e2e/                   # End-to-end integration tests
│   ├── completion/        # LSP completion tests
│   ├── diagnostics/       # LSP diagnostics tests
│   ├── semantic_tokens/   # LSP semantic tokens tests
│   └── tcp/              # TCP server tests
└── unit/                  # Unit tests for individual components
    ├── completion_unit/   # Completion logic tests
    ├── diagnostics_unit/  # Diagnostics logic tests
    ├── semantic_tokens_unit/ # Semantic tokens logic tests
    ├── yaml_parser_unit/  # YAML parsing tests
    └── duckdb_connector_unit/ # Database connector tests
```

## Test Categories

### Unit Tests (`unit/`)

Unit tests focus on testing individual components in isolation using mocked dependencies:

- **No LSP server required** - Tests individual classes and functions
- **Fast execution** - Runs in milliseconds
- **Mocked dependencies** - Uses mock DuckDB connections and test data
- **Pure logic testing** - Validates algorithms, parsing, and data processing

**What they test:**
- YAML parsing and code extraction
- SQL validation and error detection
- Completion logic and filtering
- Semantic token generation
- Coordinate transformations

### End-to-End Tests (`e2e/`)

E2E tests validate the complete LSP server functionality with real client-server communication:

- **Full LSP server** - Starts actual `mxcp lsp` subprocess
- **Real protocol** - Uses LSP protocol messages
- **Integration testing** - Tests server, database, and file system integration
- **User-like scenarios** - Simulates real editor interactions

**What they test:**
- LSP protocol compliance (initialize, completion, diagnostics)
- File watching and document synchronization
- Real SQL validation against DuckDB
- Complete feature workflows

## Isolated Test Environment

### Test Configuration (`fixtures/e2e-config/`)

The e2e tests use an **isolated test environment** to ensure:
- ✅ Tests don't depend on main project configuration
- ✅ No test artifacts are left in the file system
- ✅ Consistent execution across different environments
- ✅ Safe parallel test execution

#### Key Configuration Files:

**`mxcp-site.yml`** - Minimal test project configuration:
```yaml
mxcp: "1.0.0"
project: lsp-e2e-test
profile: test
profiles:
  test:
    duckdb:
      path: ":memory:"    # In-memory database - no files
    audit:
      enabled: false      # No audit logging
    drift:
      path: ""           # No drift tracking
extensions: []           # No extensions needed
```

**Test YAML Files:**
- `tool_with_inlined_code.yml` - Valid SQL for testing completions
- `tool_with_file_code.yml` - SQL code from file references
- `tool_with_invalid_sql.yml` - Invalid SQL for testing diagnostics

### How Test Isolation Works

1. **Server Working Directory**: E2E tests launch the LSP server from the `fixtures/e2e-config/` directory:
   ```python
   server_command=["sh", "-c", f"cd {TEST_CONFIG_DIR} && mxcp lsp"]
   ```

2. **File Path Resolution**: Tests use absolute paths to test fixtures:
   ```python
   TEST_CONFIG_DIR = Path(__file__).parent.parent.parent / "fixtures" / "e2e-config"
   uri = (TEST_CONFIG_DIR / "tool_with_inlined_code.yml").resolve().as_uri()
   ```

3. **In-Memory Database**: Uses `:memory:` DuckDB path to avoid file system artifacts

4. **No Side Effects**: Tests create no files, logs, or persistent state

## Running Tests

### Run All LSP Tests
```bash
python -m pytest tests/lsp/ -v
```

### Run Only Unit Tests (Fast)
```bash
python -m pytest tests/lsp/unit/ -v
```

### Run Only E2E Tests (Slower)
```bash
python -m pytest tests/lsp/e2e/ -v
```

### Run Specific Test Categories
```bash
# Completion tests
python -m pytest tests/lsp/e2e/completion/ -v
python -m pytest tests/lsp/unit/completion_unit/ -v

# Diagnostics tests  
python -m pytest tests/lsp/e2e/diagnostics/ -v
python -m pytest tests/lsp/unit/diagnostics_unit/ -v

# Semantic tokens tests
python -m pytest tests/lsp/e2e/semantic_tokens/ -v
python -m pytest tests/lsp/unit/semantic_tokens_unit/ -v
```

### Run Individual Tests
```bash
# Single e2e test
python -m pytest tests/lsp/e2e/completion/test_completion.py::test_completions -v

# Single unit test
python -m pytest tests/lsp/unit/completion_unit/test_completion_unit.py::test_completion -v
```

## Test Development Guidelines

### Adding New Unit Tests

1. **Create test module** in appropriate `unit/` subdirectory
2. **Use fixtures** from `conftest.py` for common setup
3. **Mock dependencies** - Don't require real LSP server or database
4. **Test edge cases** - Invalid input, empty data, error conditions

Example:
```python
def test_yaml_parsing(yaml_manager_inlined):
    """Test that YAML parsing extracts SQL code correctly."""
    code_span = yaml_manager_inlined.get_code_span()
    assert code_span is not None
    assert "SELECT" in code_span[2]  # Check SQL content
```

### Adding New E2E Tests

1. **Create test module** in appropriate `e2e/` subdirectory
2. **Use client fixture** for LSP server communication
3. **Reference test files** using `TEST_CONFIG_DIR` pattern
4. **Test realistic scenarios** - What users would actually do

Example:
```python
@pytest.mark.asyncio
async def test_new_feature(client: LanguageClient):
    """Test new LSP feature with real server."""
    uri = (TEST_CONFIG_DIR / "test_file.yml").resolve().as_uri()
    result = await client.some_lsp_method(uri)
    assert result is not None
```

### Adding New Test Fixtures

1. **Add YAML files** to `fixtures/e2e-config/`
2. **Keep them minimal** - Only what's needed for the test
3. **Use valid MXCP format** - Follow `mxcp-site.yml` schema
4. **Document purpose** - Comment what the fixture tests

## Dependencies

The tests require these key packages:
- `pytest` - Test framework
- `pytest-lsp` - LSP testing utilities
- `pytest-asyncio` - Async test support
- `duckdb` - Database for SQL validation
- `pathlib` - Path manipulation

## Troubleshooting

### Common Issues

**"mxcp-site.yml not found"**
- The LSP server is starting from wrong directory
- Check `conftest.py` uses correct `server_command` with `cd`

**"No such file or directory" for test fixtures**
- Test is using wrong path to fixture files
- Use `TEST_CONFIG_DIR` pattern for absolute paths

**Tests timing out**
- LSP server might not be starting properly
- Check server logs and ensure `mxcp` command is available

**Database connection errors**
- Unit tests should use mocked connections
- E2E tests should use `:memory:` database from test config

### Debug Mode

Run tests with extra logging:
```bash
python -m pytest tests/lsp/ -v -s --log-cli-level=DEBUG
```

## Contributing

When contributing to LSP tests:

1. **Add both unit and e2e tests** for new features
2. **Keep test isolation** - No dependencies on external state
3. **Use descriptive test names** - Explain what is being tested
4. **Test error conditions** - Not just happy paths
5. **Update this README** - Document new test patterns or fixtures

For questions about the test architecture, refer to the main MXCP documentation or ask the development team. 