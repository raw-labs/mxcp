# MXCP Language Server Protocol (LSP) Implementation

## Overview

The MXCP LSP provides intelligent language support for MXCP YAML files in code editors that support the Language Server Protocol. It offers features like syntax highlighting, code completion, diagnostics, and more for MXCP tool definitions.

## Features

### 1. **Semantic Tokens** 
- Provides syntax highlighting for SQL code blocks within MXCP YAML files
- Highlights SQL keywords, identifiers, operators, literals, and comments
- Automatically detects SQL code sections in YAML files

### 2. **Code Completion**
- Intelligent autocompletion for SQL code within YAML files
- Context-aware suggestions based on DuckDB's SQL dialect
- Completes table names, column names, and SQL functions
- Parameter completion based on tool definitions

### 3. **Diagnostics**
- Real-time SQL syntax validation
- Error reporting with precise location information
- Validates SQL queries against DuckDB's syntax rules
- Coordinate transformation for accurate error positioning in YAML files

## Architecture

### Directory Structure

```
src/mxcp/lsp/
├── __init__.py           # Package initialization
├── server.py             # Main LSP server implementation
├── features/             # LSP feature implementations
│   ├── __init__.py
│   ├── completion/       # Code completion feature
│   ├── diagnostics/      # Diagnostics feature
│   └── semantic_tokens/  # Semantic tokens feature
└── utils/                # Utility modules
    ├── duckdb_connector.py           # DuckDB connection management
    ├── document_event_coordinator.py # Document event handling
    ├── yaml_parser.py                # YAML parsing utilities
    └── models.py                     # Data models
```

### Key Components

#### 1. **MXCPLSPServer** (`server.py`)
The main server class that:
- Initializes the DuckDB session using MXCP configurations from `mxcp-site.yml` and user config
- Registers all LSP features
- Handles LSP lifecycle events (initialize, shutdown, etc.)
- Coordinates document events across features
- Supports both stdio and TCP communication modes

#### 2. **Features**
Each feature is implemented as a separate module:
- **Completion**: Provides SQL autocompletion using DuckDB's parser
- **Semantic Tokens**: Tokenizes SQL code for syntax highlighting
- **Diagnostics**: Validates SQL syntax and reports errors with accurate positioning

#### 3. **Utilities**
- **DuckDBConnector**: Manages DuckDB connections and query execution
- **DocumentEventCoordinator**: Centralizes document event handling
- **YamlParser**: Extracts SQL code blocks from MXCP YAML files
- **Models**: Data structures for parameters and other shared types

## Usage

### Starting the LSP Server

The LSP server is integrated with the MXCP CLI and can be started using:

```bash
mxcp lsp [OPTIONS]
```

**Options:**
- `--profile PROFILE`: Specify the MXCP profile to use
- `--readonly`: Start in read-only mode (disables write operations)
- `--port PORT`: Specify the port for TCP mode (automatically enables TCP)
- `--debug`: Show detailed debug information

**Examples:**
```bash
mxcp lsp                     # Start LSP server using stdio
mxcp lsp --port 3000         # Start LSP server using TCP on localhost:3000
mxcp lsp --profile dev       # Use the 'dev' profile configuration
mxcp lsp --readonly          # Open database connection in read-only mode
mxcp lsp --debug             # Start with detailed debug logging
```

**Communication Modes:**
- **stdio** (default): Suitable for IDE integration
- **TCP**: Use `--port` option for testing or when stdio communication is not suitable

### Configuring Your Editor

#### VS Code
1. Install the MXCP extension (if available)
2. The extension will automatically start the LSP server when opening `.yml` files
3. Ensure your workspace contains `mxcp-site.yml` for project detection

#### Neovim
Add the following to your Neovim configuration:

```lua
require('lspconfig').mxcp.setup{
  cmd = {'mxcp', 'lsp'},
  filetypes = {'yaml'},
  root_dir = require('lspconfig.util').root_pattern('mxcp-site.yml', 'mxcp-config.yml'),
}
```

#### Other Editors
Any editor that supports LSP can be configured to use the MXCP LSP server. The server communicates over stdio by default and follows the LSP specification.

## Development

### Running Tests

The LSP module includes comprehensive unit and end-to-end tests with isolated test environments:

```bash
# Run all LSP tests
pytest tests/lsp/

# Run unit tests only (fast, mocked dependencies)
pytest tests/lsp/unit/

# Run e2e tests only (slower, real LSP server)
pytest tests/lsp/e2e/
```

### Test Structure

```
tests/lsp/
├── README.md             # Comprehensive test documentation
├── fixtures/             # Test fixtures and configurations
│   └── e2e-config/      # Isolated test environment
│       ├── mxcp-site.yml # Test project configuration
│       ├── tool_with_inlined_code.yml
│       ├── tool_with_file_code.yml
│       └── tool_with_invalid_sql.yml
├── unit/                 # Unit tests for individual components
│   ├── completion_unit/
│   ├── diagnostics_unit/
│   ├── semantic_tokens_unit/
│   ├── duckdb_connector_unit/
│   └── yaml_parser_unit/
└── e2e/                  # End-to-end integration tests
    ├── completion/
    ├── diagnostics/
    ├── semantic_tokens/
    └── tcp/             # TCP server tests
```

### Test Environment Isolation

The e2e tests use an **isolated test environment** to ensure:
- ✅ Tests don't depend on main project configuration
- ✅ No test artifacts are left in the file system
- ✅ Consistent execution across different environments
- ✅ Safe parallel test execution

Key features:
- **In-memory database** (`:memory:`) prevents file system artifacts
- **Isolated configuration** in `fixtures/e2e-config/`
- **Server working directory** properly set for tests
- **Absolute file paths** for fixture references

### Adding New Features

To add a new LSP feature:

1. Create a new module in `features/`
2. Implement the feature following the existing pattern:
   ```python
   def register_feature_name(server, duckdb_connector):
       @server.feature("textDocument/featureName")
       def handle_feature(params):
           # Implementation
           pass
       
       # Return any service objects that need document event handling
       return feature_service
   ```
3. Register the feature in `server.py`'s `_register_features` method
4. Add corresponding unit and e2e tests following the isolation patterns
5. Update this documentation

## Technical Details

### Configuration Integration

The LSP server integrates with MXCP's configuration system:
- **Site Config** (`mxcp-site.yml`): Project-specific settings and database configuration
- **User Config** (`~/.mxcp/config.yml`): Personal settings and secrets
- **Profile Support**: Respects profile selection for environment-specific behavior
- **Auto-Generation**: Works with auto-generated user config for zero-configuration startup

### DuckDB Integration

The LSP server leverages MXCP's DuckDB session management:
- Uses the configured DuckDB instance from project configuration
- Respects profile settings and read-only mode
- Provides SQL validation against the actual database schema
- Session-scoped setup includes extensions, secrets, and plugins

### Document Event Coordination

The `DocumentEventCoordinator` ensures that document events (open, change, close) are handled consistently across all features. Features can register as handlers and will receive notifications when documents change.

### YAML Parsing and Code Extraction

The `YamlParser` utility extracts SQL code blocks from MXCP YAML files:
- Identifies `code:` sections in tool definitions
- Tracks line numbers for accurate error positioning
- Handles both inline and file-based SQL definitions
- Provides coordinate transformation for precise diagnostic positioning

### Session Architecture

Following MXCP's session pattern:
- **Per-Operation Sessions** for CLI commands
- **Shared Session** for LSP server with thread-safe access
- **Session-Scoped Setup**: Extensions, secrets, and plugins loaded once per session
- **Automatic Cleanup**: Context manager pattern ensures proper resource management

## Environment Variables

The LSP server respects standard MXCP environment variables:
- `MXCP_PROFILE`: Default profile name
- `MXCP_DEBUG`: Enable debug mode
- `MXCP_READONLY`: Enable read-only mode
- `MXCP_CONFIG`: Path to user configuration file

## Roadmap

See `roadmap.md` for planned features and improvements, including:
- Hover information with schema details
- Go to definition for endpoints and references
- Find references across MXCP files
- Code formatting for SQL blocks
- Refactoring support for endpoint names
- Enhanced completion with schema-aware suggestions
- Integration with VS Code extension
- Support for additional MXCP file types (resources, prompts)

## Contributing

When contributing to the LSP implementation:

1. **Follow MXCP patterns**: Use the established configuration loading and session management patterns
2. **Add comprehensive tests**: Include both unit tests (mocked) and e2e tests (real server)
3. **Maintain test isolation**: Use the isolated test environment for e2e tests
4. **Update documentation**: Include examples and usage information
5. **Consider editor integration**: Design features with editor user experience in mind

For detailed development guidelines, see the [MXCP Development Guide](../../docs/dev-guide.md) and [LSP Test Documentation](../../tests/lsp/README.md).
