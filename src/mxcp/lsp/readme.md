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

### 3. **Diagnostics**
- Real-time SQL syntax validation
- Error reporting with precise location information
- Validates SQL queries against DuckDB's syntax rules

## Architecture

### Directory Structure

```
src/mxcp/lsp/
├── __init__.py           # Package initialization
├── server.py             # Main LSP server implementation
├── features/             # LSP feature implementations
│   ├── completion.py     # Code completion feature
│   ├── diagnostics.py    # Diagnostics feature
│   └── semantic_tokens.py # Semantic tokens feature
└── utils/                # Utility modules
    ├── duckdb_connector.py    # DuckDB connection management
    ├── document_event_coordinator.py # Document event handling
    └── yaml_parser.py         # YAML parsing utilities
```

### Key Components

#### 1. **MXCPLSPServer** (`server.py`)
The main server class that:
- Initializes the DuckDB session using MXCP configurations
- Registers all LSP features
- Handles LSP lifecycle events (initialize, shutdown, etc.)
- Coordinates document events across features

#### 2. **Features**
Each feature is implemented as a separate module:
- **Completion**: Provides SQL autocompletion using DuckDB's parser
- **Semantic Tokens**: Tokenizes SQL code for syntax highlighting
- **Diagnostics**: Validates SQL syntax and reports errors

#### 3. **Utilities**
- **DuckDBConnector**: Manages DuckDB connections and query execution
- **DocumentEventCoordinator**: Centralizes document event handling
- **YamlParser**: Extracts SQL code blocks from MXCP YAML files

## Usage

### Starting the LSP Server

The LSP server is integrated with the MXCP CLI and can be started using:

```bash
mxcp lsp [options]
```

Options:
- `--profile PROFILE`: Specify the MXCP profile to use
- `--readonly`: Start in read-only mode (disables write operations)
- `--port PORT`: Specify the port for the LSP server (default: stdio)

### Configuring Your Editor

#### VS Code
1. Install the MXCP extension (if available)
2. The extension will automatically start the LSP server when opening `.yml` files

#### Neovim
Add the following to your Neovim configuration:

```lua
require('lspconfig').mxcp.setup{
  cmd = {'mxcp', 'lsp'},
  filetypes = {'yaml'},
  root_dir = require('lspconfig.util').root_pattern('mxcp-config.yml', 'mxcp-site.yml'),
}
```

#### Other Editors
Any editor that supports LSP can be configured to use the MXCP LSP server. The server communicates over stdio by default.

## Development

### Running Tests

The LSP module includes comprehensive unit and end-to-end tests:

```bash
# Run all LSP tests
pytest tests/lsp/

# Run unit tests only
pytest tests/lsp/unit/

# Run e2e tests only
pytest tests/lsp/e2e/
```

### Test Structure

```
tests/lsp/
├── fixtures/             # Test YAML files
├── unit/                 # Unit tests for individual components
│   ├── completion_unit/
│   ├── diagnostics_unit/
│   ├── semantic_tokens_unit/
│   ├── duckdb_connector_unit/
│   └── yaml_parser_unit/
└── e2e/                  # End-to-end integration tests
    ├── completion/
    └── semantic_tokens/
```

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
   ```
3. Register the feature in `server.py`'s `_register_features` method
4. Add corresponding unit and e2e tests

## Technical Details

### Document Event Coordination

The `DocumentEventCoordinator` ensures that document events (open, change, close) are handled consistently across all features. Features can register as handlers and will receive notifications when documents change.

### DuckDB Integration

The LSP server leverages MXCP's DuckDB session management:
- Uses the configured DuckDB instance from `mxcp-config.yml`
- Respects profile settings and read-only mode
- Provides SQL validation against the actual database schema

### YAML Parsing

The `YamlParser` utility extracts SQL code blocks from MXCP YAML files:
- Identifies `code:` sections in tool definitions
- Tracks line numbers for accurate error positioning
- Handles both inline and file-based SQL definitions

## Roadmap

See `roadmap.md` for planned features and improvements, including:
- Hover information
- Go to definition
- Find references
- Code formatting
- Refactoring support
