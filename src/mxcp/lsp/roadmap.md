# MXCP Editor Tooling – Implementation Reference

## Overview

MXCP's editor tooling transforms the development experience from a terminal-heavy workflow to an integrated, one-click development environment. This document specifies the complete implementation roadmap for both the Language Server Protocol (LSP) server and VS Code extension, along with the distribution strategy.

**Goal**: Eliminate the "edit → save → switch terminal → run → read output → switch back" cycle by providing:

- Real-time validation and autocompletion for MXCP YAML files
- One-click execution of tools, tests, and validation
- Integrated MCP client for endpoint testing
- Seamless CLI integration within the editor

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   VS Code       │    │   MXCP LSP      │    │   MXCP Core     │
│   Extension     │◄──►│   Server        │◄──►│   Engine        │
│                 │    │  (mxcp lsp)     │    │                 │
│ • UI Controls   │    │ • Schema Val.   │    │ • Validation    │
│ • CodeLens      │    │ • Completion    │    │ • Execution     │
│ • Output Panel  │    │ • Diagnostics   │    │ • Testing       │
│ • Commands      │    │ • Hover Info    │    │ • MCP Server    │
└─────────────────┘    └─────────────────┘    │ • Config Mgmt   │
         │                       │            │ • Schema Load   │
         └───────────────────────┼────────────┤ • CLI Commands  │
                                 │            └─────────────────┘
                    ┌─────────────────┐
                    │   DuckDB        │
                    │   Session       │
                    │                 │
                    │ • Schema Info   │
                    │ • SQL Exec.     │
                    │ • Table/Col     │
                    │   Completion    │
                    └─────────────────┘
```

**Key Advantage**: The LSP server runs as `mxcp lsp` subcommand, giving it direct access to all MXCP internals including validation, execution, schema loading, and configuration management.

## Project Structure & File Support

MXCP tooling supports flexible project organization. Schema detection is based on file content rather than directory structure, giving users complete freedom in organizing their files.

```
your-project/
├── mxcp-site.yml           # Site config (detected by filename)
├── earthquake_tool.yml     # Tool definition (detected by 'tool:' key)
├── sales_analysis.yml      # Tool definition (detected by 'tool:' key)
├── data/
│   ├── earthquake_feed.yml # Resource definition (detected by 'resource:' key)
│   └── sales_cache.yml     # Resource definition (detected by 'resource:' key)
├── prompts/
│   └── analysis.yml        # Prompt template (detected by 'prompt:' key)
├── tools/                  # Alternative organization
│   └── custom_tool.yml     # Tool definition (detected by 'tool:' key)
└── models/                 # dbt models (handled by dbt extension)
    ├── staging/
    └── marts/
```

### File Detection & Schema Application

| Detection Method | Schema Applied | LSP Features |
| ---------------- | ----------------------------- | ------------------------------------------------------- |
| **Filename**: `mxcp-site.yml` | `mxcp-site-schema-1.0.0.json` | Site config validation, profile completion |
| **Content**: Contains `tool:` key | `endpoint-schema-1.0.0.json` | Tool validation, parameter completion, SQL highlighting |
| **Content**: Contains `resource:` key | `endpoint-schema-1.0.0.json` | Resource validation, URI completion |
| **Content**: Contains `prompt:` key | `endpoint-schema-1.0.0.json` | Prompt validation, template variable checking |
| **Extension**: `*.sql` files | Handled by dbt extension | Use existing dbt VS Code extension for full dbt support |

**Schema Detection Logic**:
1. **Site Config**: Files named `mxcp-site.yml` (exact match)
2. **Endpoint Types**: Parse YAML content and detect root-level keys:
   - `tool:` → Tool endpoint schema
   - `resource:` → Resource endpoint schema  
   - `prompt:` → Prompt endpoint schema
3. **SQL Files**: Handled by existing dbt VS Code extension
4. **SQL-in-YAML**: SQL blocks within YAML files get MXCP-specific highlighting and validation
5. **Fallback**: Unknown YAML files get basic YAML support without MXCP schemas

---

## Implementation Status

### ✅ Completed Features

**Core Language Server Functionality** - *Ready for use*

| Feature | Status | User Experience |
|---------|--------|-----------------|
| **Content-based schema detection** | ✅ Complete | Schema validation works regardless of file organization - move files anywhere and they're automatically recognized |
| **SQL-in-YAML semantic highlighting** | ✅ Complete | SQL code blocks in YAML look identical to `.sql` files with full syntax highlighting |
| **Intelligent autocompletion** | ✅ Complete | Typing `SEL` in YAML SQL blocks completes to `SELECT`, table names autocomplete from DuckDB schema |
| **Real-time diagnostics** | ✅ Complete | Red squiggles under errors, hover for details - catches both YAML schema and SQL syntax errors |

**Technical Implementation Notes**:
- Uses MXCP's existing YAML parsing from `mxcp.endpoints.loader`
- Integrates with DuckDB session for SQL validation and completion
- Leverages `mxcp.endpoints.schema` validation for YAML diagnostics
- Dynamic schema registration per file based on content analysis

---

## Development Roadmap

### Phase 1: Execution Integration (Next Priority)

**Target**: Direct integration with MXCP execution engine

| #     | Feature                    | User Experience Goal | Technical Approach |
| ----- | -------------------------- | -------------------- | ------------------ |
| **1** | **CodeLens integration**   | Clickable "▶ Run Tool", "🧪 Run Tests", "✓ Validate" links above each tool definition | Parse tools/tests using existing `mxcp.endpoints.loader`, return CodeLens at line positions |
| **2** | **Direct MXCP execution**  | Instant execution, faster than subprocess calls | Use `mxcp.endpoints.executor.EndpointExecutor` directly, stream results via LSP notifications |
| **3** | **Execution diagnostics**  | Runtime errors appear as red squiggles in editor | Catch `mxcp.endpoints.executor.SchemaError`, map to LSP diagnostics with source locations |
| **4** | **Profile-aware features** | Features work with correct database/config for current environment | Initialize with `mxcp.config.user_config`, pass profile to `DuckDBSession` |

### Phase 2: VS Code Extension Core

**Target**: Functional VS Code extension with essential UI

| #      | Feature                                 | User Experience Goal | Technical Approach |
| ------ | --------------------------------------- | -------------------- | ------------------ |
| **5**  | **Extension activation & dependencies** | Zero-config activation when opening MXCP projects | `"activationEvents": ["workspaceContains:mxcp-site.yml"]`, depend on YAML extension |
| **6**  | **YAML schema contributions**           | YAML validation works immediately without manual setup | Register schemas via `contributes.yamlValidation` in `package.json` |
| **7**  | **Output channel & result display**     | Organized output separate from other extensions | Create dedicated MXCP output channel with ANSI color support |
| **8**  | **Status bar & progress**               | Clear feedback on long-running operations with cancellation | Listen for custom LSP notifications, display spinner with cancel button |

### Phase 3: Advanced Features

**Target**: Polish and productivity enhancements

| #      | Feature                         | User Experience Goal | Technical Approach |
| ------ | ------------------------------- | -------------------- | ------------------ |
| **9**  | **Integrated MCP client**       | Click "🧪 Test Endpoint" → parameter form → live results | Start embedded `mxcp.server.mcp.RAWMCP` instance for endpoint testing |
| **10** | **Cross-reference validation**   | Immediate feedback on broken references, F12 navigation between MXCP files | Parse resource URIs, validate accessibility, check template variable references |
| **11** | **Drift detection integration** | Immediate feedback on schema-breaking changes with quick-fix actions | Call `mxcp.drift.detector.detect_drift()` directly, display as diagnostics |

---

## Distribution & Installation Strategy

### Overview

MXCP uses a unified distribution approach: the LSP server is built into the main MXCP CLI as a subcommand (`mxcp lsp`), eliminating the need for separate binaries or version management.

### Installation Flow & User Experience

| Scenario | User Experience | Implementation Details |
| -------------------- | ----------------------------------- | -------------------------------------------- |
| **Fresh install** | Extension automatically creates isolated environment | Use `context.globalStorageUri` for complete isolation from user Python |
| **Existing global install** | Extension detects and uses existing MXCP if compatible | Check `mxcp --version` and `mxcp lsp --help` |
| **User-specified path** | Use `mxcp.cliPath` setting for custom installations | Highest priority, full verification of path |
| **Version mismatch** | Offer upgrade in isolated environment | Never modify user's global Python environment |
| **Python not found** | Clear error message with installation guidance | Guide users to install Python 3.9+ |
| **LSP server fails** | Automatic restart with debug mode and helpful logs | Provide troubleshooting information |

### VS Code Extension Installation Logic

```typescript
async function activate(context: ExtensionContext) {
    // 1. Try user-specified path first
    let mxcpPath = getUserConfiguredPath();
    
    // 2. Try existing system installation
    if (!mxcpPath) {
        mxcpPath = await discoverSystemMXCP();
    }
    
    // 3. Install in isolated environment as fallback
    if (!mxcpPath) {
        mxcpPath = await installMXCPIsolated(context);
    }
    
    await startLSPClient(mxcpPath);
}

async function discoverSystemMXCP(): Promise<string | null> {
    try {
        // Check if mxcp is in PATH and supports LSP
        await exec('mxcp', ['--version']);
        await exec('mxcp', ['lsp', '--help']);
        return 'mxcp';
    } catch {
        return null; // Not found or incompatible
    }
}
```

### Configuration & Settings

```json
{
   "mxcp.cliPath": "",                    // Manual path override (highest priority)
   "mxcp.profile": "dev",                 // Default profile for LSP operations
   "mxcp.debug": false,                   // Enable debug logging
   "mxcp.autoValidate": true,             // Validate files on save
   "mxcp.showInlayHints": true,           // Show parameter defaults as hints
   "mxcp.logLevel": "info",               // LSP server logging level
   "mxcp.fileDetection": {
     "enableContentBasedDetection": true, // Detect schemas from file content
     "customPatterns": {                  // Optional: user-defined patterns
       "tools": ["**/my-tools/*.yml"],
       "resources": ["**/data/*.yml"]
     }
   }
}
```

### Build & Release Process

#### Python Package (PyPI)
- Single package includes both CLI and LSP server
- Universal wheels for cross-platform compatibility
- Standard `python -m build` and `twine upload` workflow

#### VS Code Extension (Marketplace)
- Standard `vsce package` and `vsce publish` workflow
- Extension includes schema files and TypeScript activation logic
- No Python code bundled - relies on separate MXCP installation

### Distribution Advantages

1. **Single Source of Truth**: LSP server shares exact same code as CLI
2. **Automatic Updates**: Extension updates get latest LSP features automatically  
3. **No Version Skew**: CLI and LSP always compatible
4. **Simplified Testing**: Test one package instead of coordinating two
5. **Better Error Reporting**: Shared error handling and logging
6. **Cross-Platform**: Universal wheels work on all Python-supported platforms

---

## User Experience Validation

### Key Workflows

1. **New Project Setup**
   - User creates `mxcp-site.yml` → Extension activates automatically
   - Schema validation works immediately without configuration
   - SQL completion works in embedded blocks

2. **Daily Development**
   - Edit YAML files → Real-time validation and completion
   - Click CodeLens → Instant tool execution with results in output panel
   - Save files → Auto-validation with clear error indicators

3. **Testing & Debugging**
   - Test endpoints directly from editor with parameter forms
   - Runtime errors mapped to source locations
   - Integrated output panel with syntax highlighting

4. **Collaboration**
   - Files can be organized in any directory structure
   - Team members get consistent experience regardless of setup
   - No manual schema configuration required

### Success Metrics

- **Zero Configuration**: Extension works immediately after installation
- **Fast Feedback**: Diagnostics appear within 100ms of typing
- **One-Click Operations**: All MXCP commands accessible via CodeLens
- **Unified Experience**: Same validation logic as CLI ensures consistency

---

## Questions & Clarifications Needed

1. **Profile Management**: How should the extension handle switching between different MXCP profiles during development?

2. **Error Recovery**: What's the preferred behavior when the LSP server crashes - automatic restart vs. user notification?

3. **Large Projects**: Are there performance considerations for projects with hundreds of YAML files?

4. **Integration Testing**: Should the extension include integration tests that verify LSP communication?

5. **Telemetry**: What usage data (if any) should be collected to improve the extension?