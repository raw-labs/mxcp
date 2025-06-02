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

## Implementation Roadmap

### Phase 1: Language Server Core Features

**Target**: Functional LSP server with essential YAML and SQL support

| #     | Feature                        | Implementation Specification                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | **Content-based schema detection** | **Definition**: Dynamically detect and apply MXCP schemas based on file content rather than directory patterns.<br>**Implementation**: <br>• Parse YAML on file open/change to detect root keys (`tool:`, `resource:`, `prompt:`)<br>• Use filename detection for `mxcp-site.yml`<br>• Register schemas dynamically: `yamlLanguageService.addSchema()` per file<br>• Cache detection results for performance<br>**User Experience**: Schema validation works regardless of file organization |
| **2** | **SQL-in-YAML semantic highlighting**  | **Definition**: Detect SQL blocks in YAML (`source.code: \|`) and apply SQL syntax highlighting.<br>**Implementation**:<br>• Use MXCP's existing YAML parsing from `mxcp.endpoints.loader`<br>• Return semantic tokens for SQL keywords, strings, identifiers within YAML blocks<br>• Integrate with DuckDB session for SQL validation<br>• Focus only on SQL embedded in YAML files<br>**User Experience**: SQL code blocks in YAML look identical to `.sql` files                                                                                                                |
| **3** | **Intelligent autocompletion** | **Definition**: Context-aware completion for SQL and YAML using MXCP internals.<br>**Implementation**:<br>• **SQL-in-YAML**: Use existing `DuckDBSession` to query `INFORMATION_SCHEMA` for SQL blocks within YAML<br>• **YAML**: Leverage `mxcp.endpoints.schema` validation for completions<br>• **Template vars**: Extract parameters from tool definitions using existing parsers<br>• **Note**: Standalone .sql files handled by dbt extension<br>**User Experience**: Typing `SEL` in YAML SQL blocks completes to `SELECT`, table names autocomplete |
| **4** | **Real-time diagnostics**      | **Definition**: Use MXCP's validation engine for comprehensive error checking.<br>**Implementation**:<br>• **SQL-in-YAML**: Use `DuckDBSession.execute()` with `EXPLAIN` for syntax validation of embedded SQL<br>• **YAML**: Call `mxcp.endpoints.schema.validate_endpoint_payload()` directly<br>• **Config**: Use `mxcp.config.site_config.load_site_config()` for site validation<br>• Map validation errors to LSP diagnostic format<br>**User Experience**: Red squiggles under errors, hover for details                   |
| **5** | **CodeLens integration**       | **Definition**: Provide executable actions above tools and tests.<br>**Implementation**:<br>• Use content-based detection to identify tools and test blocks<br>• Parse tools and tests using existing `mxcp.endpoints.loader`<br>• Return CodeLens at line positions: "▶ Run Tool", "🧪 Run Tests", "✓ Validate"<br>• Register `workspace/executeCommand` handlers<br>**User Experience**: Clickable gray links above each tool definition                                                                |

### Phase 2: Execution & Integration

**Target**: Direct integration with MXCP execution engine

| #     | Feature                    | Implementation Specification                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **6** | **Direct MXCP execution**  | **Definition**: Execute MXCP operations directly without subprocess overhead.<br>**Implementation**:<br>• **Tools**: Use `mxcp.endpoints.executor.EndpointExecutor` directly<br>• **Tests**: Call `mxcp.cli.test.run_tests()` with parsed arguments<br>• **Validation**: Use `mxcp.cli.validate.validate_project()` function<br>• Stream results via LSP `window/logMessage` notifications<br>• Support cancellation via Python threading/asyncio<br>**User Experience**: Instant execution, faster than subprocess calls |
| **7** | **Execution diagnostics**  | **Definition**: Convert MXCP exceptions into LSP diagnostics using internal error handling.<br>**Implementation**:<br>• Catch `mxcp.endpoints.executor.SchemaError` and map to diagnostics<br>• Use `mxcp.endpoints.loader.extract_validation_error()` for error formatting<br>• Map SQL execution errors from DuckDB to source locations<br>• Send `textDocument/publishDiagnostics` with precise locations<br>**User Experience**: Runtime errors appear as red squiggles in editor                                     |
| **8** | **Profile-aware features** | **Definition**: Use MXCP's configuration system for profile management.<br>**Implementation**:<br>• Initialize with `mxcp.config.user_config.load_user_config()`<br>• Use `mxcp.config.site_config.load_site_config()` for project settings<br>• Pass profile to `DuckDBSession` constructor<br>• Reload configuration on file changes using existing config loaders<br>**User Experience**: Features work with correct database/config for environment                                                                   |

### Phase 3: VS Code Extension Core

**Target**: Functional VS Code extension with essential UI

| #      | Feature                                 | Implementation Specification                                                                                                                                                                                                                                                                                                                                          |
| ------ | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **9**  | **Extension activation & dependencies** | **Definition**: Activate on MXCP projects and depend on YAML extension.<br>**Implementation**:<br>• `package.json`: `"activationEvents": ["workspaceContains:mxcp-site.yml"]`<br>• `"extensionDependencies": ["redhat.vscode-yaml"]`<br>• Auto-detect MXCP projects and activate LSP client<br>**User Experience**: Zero-config activation when opening MXCP projects |
| **10** | **YAML schema contributions**           | **Definition**: Register MXCP schemas with VS Code YAML extension.<br>**Implementation**:<br>• `package.json` → `contributes.yamlValidation`:<br>`json<br>{"fileMatch": ["**/tools/*.yml"], "url": "mxcp://schemas/endpoint"}<br>`<br>• Provide schema URIs via extension API<br>**User Experience**: YAML validation works immediately without manual setup          |
| **11** | **Output channel & result display**     | **Definition**: Dedicated output panel for MXCP operations.<br>**Implementation**:<br>• Create output channel: `window.createOutputChannel("MXCP Results")`<br>• Listen to LSP log notifications and display with ANSI color support<br>• Auto-focus on execution, provide clear/save actions<br>**User Experience**: Organized output separate from other extensions |
| **12** | **Status bar & progress**               | **Definition**: Show execution status and provide cancellation.<br>**Implementation**:<br>• Listen for custom `mxcp/runStarted` and `mxcp/runEnded` notifications<br>• Display spinner with `window.withProgress`<br>• Provide cancel button that sends abort signal to LSP<br>**User Experience**: Clear feedback on long-running operations                         |

### Phase 4: Advanced Features

**Target**: Polish and productivity enhancements

| #      | Feature                         | Implementation Specification                                                                                                                                                                                                                                                                                                                                                                                    |
| ------ | ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **13** | **Integrated MCP client**       | **Definition**: Use MXCP's built-in MCP server for endpoint testing.<br>**Implementation**:<br>• Start embedded `mxcp.server.mcp.RAWMCP` instance<br>• Provide "Test Endpoint" CodeLens action<br>• Use MXCP's parameter validation and result formatting<br>**User Experience**: Click "🧪 Test Endpoint" → parameter form → live results                                                                      |
| **14** | **Cross-reference validation**     | **Definition**: Validate references between MXCP endpoints and external resources.<br>**Implementation**:<br>• Parse resource URIs and validate they're accessible<br>• Check template variable references in prompts<br>• Validate parameter types across tool chains<br>• Provide hover info for cross-references<br>**User Experience**: Immediate feedback on broken references, F12 navigation between MXCP files                  |
| **15** | **Drift detection integration** | **Definition**: Use MXCP's drift detection system for schema warnings.<br>**Implementation**:<br>• Call `mxcp.drift.detector.detect_drift()` directly<br>• Use `mxcp.drift.snapshot.create_snapshot()` for baseline creation<br>• Display warnings as diagnostics for breaking changes<br>• Provide quick-fix actions to update snapshots<br>**User Experience**: Immediate feedback on schema-breaking changes |

---

## Distribution & Installation Strategy

### Overview

MXCP uses a unified distribution approach: the LSP server is built into the main MXCP CLI as a subcommand (`mxcp lsp`), eliminating the need for separate binaries or version management. The project uses modern Python packaging standards with setuptools and universal wheels.

### Phase 1: Python Package Build & Distribution

| Component | Implementation | Details |
|-----------|---------------|---------|
| **Build System** | `setuptools>=42` with `wheel` backend | Modern Python packaging, faster installs |
| **Package Structure** | ```toml<br>[project.scripts]<br>mxcp = "mxcp.__main__:cli"<br># LSP server available as: mxcp lsp<br>``` | Single entry point, LSP as subcommand |
| **Dependencies** | Core LSP dependencies included:<br>• `pygls>=1.0.0` (LSP server)<br>• `lsprotocol>=2023.0.0` (LSP types)<br>• All MXCP dependencies (DuckDB, etc.) | No separate LSP package needed |
| **Package Data** | JSON schemas included via `package-data` | Schemas bundled for offline validation |
| **Version Strategy** | Single version for CLI + LSP server | Automatic compatibility, no version skew |

### Phase 2: VS Code Extension Installation Logic

```typescript
// Extension activation - updated for actual MXCP CLI interface
async function activate(context: ExtensionContext) {
    let mxcpPath = await discoverMXCP();
    
    if (!mxcpPath) {
        mxcpPath = await installMXCPIsolated(context);
    }
    
    await startLSPClient(mxcpPath);
    registerCommands(mxcpPath);
}

async function discoverMXCP(): Promise<string | null> {
    // 1. Check user setting: mxcp.cliPath
    const userPath = vscode.workspace.getConfiguration('mxcp').get<string>('cliPath');
    if (userPath && await verifyMXCPInstall(userPath)) {
        return userPath;
    }
    
    // 2. Check PATH for existing installation
    try {
        const result = await exec('mxcp', ['--version']);
        if (result.stdout.includes('mxcp')) {
            // 3. Test LSP support
            await exec('mxcp', ['lsp', '--help']);
            return 'mxcp'; // Use from PATH
        }
    } catch (error) {
        // Not found in PATH or LSP not supported
    }
    
    return null;
}

async function verifyMXCPInstall(path: string): Promise<boolean> {
    try {
        // Verify version and LSP support
        await exec(path, ['--version']);
        await exec(path, ['lsp', '--help']);
        return true;
    } catch {
        return false;
    }
}

async function installMXCPIsolated(context: ExtensionContext): Promise<string> {
    const venvPath = path.join(context.globalStorageUri.fsPath, "mxcp-venv");
    
    // Create isolated virtual environment
    await exec("python3", ["-m", "venv", venvPath]);
    
    // Install specific MXCP version (includes LSP automatically)
    const pythonPath = getVenvPython(venvPath);
    await exec(pythonPath, [
        "-m", "pip", "install", 
        `mxcp==${REQUIRED_VERSION}`,
        "--no-cache-dir"  // Ensure fresh install
    ]);
    
    return getVenvMXCP(venvPath);
}

function getVenvPython(venvPath: string): string {
    return process.platform === 'win32' 
        ? path.join(venvPath, "Scripts", "python.exe")
        : path.join(venvPath, "bin", "python");
}

function getVenvMXCP(venvPath: string): string {
    return process.platform === 'win32'
        ? path.join(venvPath, "Scripts", "mxcp.exe") 
        : path.join(venvPath, "bin", "mxcp");
}

async function startLSPClient(mxcpPath: string) {
    // Start LSP server using mxcp lsp subcommand (stdio mode by default)
    const client = new LanguageClient(
        "mxcp-lsp",
        "MXCP Language Server",
        {
            command: mxcpPath,
            args: ["lsp"], // No --stdio flag needed, it's the default
            options: {
                env: {
                    ...process.env,
                    // Pass VS Code workspace settings to LSP
                    MXCP_PROFILE: getConfigValue('mxcp.profile'),
                    MXCP_DEBUG: getConfigValue('mxcp.debug') ? 'true' : 'false'
                }
            }
        },
        {
            documentSelector: [
                // MXCP focuses on YAML files and embedded SQL
                { scheme: "file", language: "yaml" },
                // Site config by filename
                { scheme: "file", pattern: "**/mxcp-site.yml" },
            ],
            initializationOptions: {
                // Pass extension settings to LSP server
                profile: getConfigValue('mxcp.profile'),
                logLevel: getConfigValue('mxcp.logLevel'),
                enableTelemetry: getConfigValue('mxcp.enableTelemetry')
            }
        }
    );
    
    await client.start();
}
```

### Phase 3: Installation Flow & Error Handling

| Scenario | Behavior | Implementation |
| -------------------- | ----------------------------------- | -------------------------------------------- |
| **Fresh install** | Create isolated venv, install MXCP with pip | Use `context.globalStorageUri` for complete isolation |
| **Existing global install** | Verify version and LSP support, use if compatible | Check `mxcp --version` and `mxcp lsp --help` |
| **User-specified path** | Use `mxcp.cliPath` setting if valid | Highest priority, full verification |
| **Version mismatch** | Offer upgrade in isolated venv | Never modify user's global Python environment |
| **Python not found** | Show helpful error with install instructions | Guide users to install Python 3.9+ |
| **Pip install fails** | Retry with different flags, show detailed error | Handle network issues, permission problems |
| **LSP server fails** | Restart with debug mode, collect logs | Provide troubleshooting information |
| **Extension uninstall** | Clean up isolated venv | Remove all extension-created files |

### Build & Release Process

#### Python Package (PyPI)
```bash
# Development build
python -m build
pip install dist/mxcp-*.whl

# Release build
python -m build --clean
twine check dist/*
twine upload dist/*
```

#### VS Code Extension (Marketplace)
```bash
# Package extension
vsce package

# Publish to marketplace
vsce publish
```

### Configuration & Settings

```json
// VS Code settings with current MXCP CLI options
{
   "mxcp.cliPath": "",                    // Manual path override (highest priority)
   "mxcp.profile": "dev",                 // Default profile for LSP (maps to --profile)
   "mxcp.debug": false,                   // Enable debug logging (maps to --debug)
   "mxcp.autoValidate": true,             // Validate on save
   "mxcp.showInlayHints": true,           // Show parameter defaults
   "mxcp.logLevel": "info",               // LSP logging level
   "mxcp.enableTelemetry": false,         // Usage analytics
   "mxcp.fileDetection": {
     "enableContentBasedDetection": true, // Detect schemas from file content
     "customPatterns": {                  // Optional: user-defined patterns
       "tools": ["**/my-tools/*.yml"],
       "resources": ["**/data/*.yml"]
     }
   }
}
```

### Dependency Management

#### Core Dependencies (automatically installed)
```toml
# From pyproject.toml - included with MXCP
dependencies = [
    "pygls>=1.0.0",           # LSP server framework
    "lsprotocol>=2023.0.0",   # LSP protocol types
    "pyyaml>=6.0.1",          # YAML parsing
    "jsonschema",             # Schema validation
    "duckdb>=0.9.2",          # Database engine
    "click>=8.1.7"            # CLI framework
]
```

#### VS Code Extension Dependencies
```json
{
    "extensionDependencies": [
        "redhat.vscode-yaml"  // Required for base YAML support
    ],
    "extensionPack": [
        // Optional but recommended extensions
        "bastienboutonnet.vscode-dbt"  // For .sql file support
    ]
}
```

### Distribution Advantages

1. **Single Source of Truth**: LSP server shares exact same code as CLI
2. **Automatic Updates**: Extension updates get latest LSP features automatically  
3. **No Version Skew**: CLI and LSP always compatible
4. **Simplified Testing**: Test one package instead of coordinating two
5. **Better Error Reporting**: Shared error handling and logging
6. **Reduced Bundle Size**: No duplicate dependencies
7. **Cross-Platform**: Universal wheels work on all Python-supported platforms

### Installation Troubleshooting

#### Common Issues & Solutions
| Issue | Cause | Solution |
|-------|-------|----------|
| "mxcp command not found" | Not in PATH or not installed | Install via extension or `pip install mxcp` |
| "LSP server failed to start" | Missing dependencies | Reinstall in clean venv |
| "Schema validation not working" | YAML extension conflict | Check extension dependencies |
| "Permission denied" | Venv creation failed | Check VS Code permissions |
| "Python not found" | Python 3.9+ not available | Install Python, update PATH |

The unified distribution strategy ensures users get a consistent, reliable experience while minimizing the complexity of managing separate LSP server installations.

---

## Technical Specifications

### Content-Based Schema Detection

```python
# LSP server schema detection logic
class SchemaDetector:
    @staticmethod
    def detect_schema_from_content(file_path: str, content: str) -> Optional[str]:
        """Detect MXCP schema based on file content"""
        
        # Site config detection by filename
        if file_path.endswith('mxcp-site.yml'):
            return 'mxcp-site-schema-1.0.0.json'
        
        # Skip .sql files - handled by dbt extension
        if file_path.endswith('.sql'):
            return None
        
        # Parse YAML content for endpoint types
        try:
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return None
                
            # Check for endpoint type keys
            if 'tool' in data:
                return 'endpoint-schema-1.0.0.json'
            elif 'resource' in data:
                return 'endpoint-schema-1.0.0.json'
            elif 'prompt' in data:
                return 'endpoint-schema-1.0.0.json'
            elif 'mxcp' in data and ('project' in data or 'profile' in data):
                # User config file
                return 'mxcp-config-schema-1.0.0.json'
                
        except yaml.YAMLError:
            # Invalid YAML, no schema detection
            pass
            
        return None
    
    @staticmethod
    def get_endpoint_type(content: str) -> Optional[str]:
        """Extract endpoint type from YAML content"""
        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict):
                for endpoint_type in ['tool', 'resource', 'prompt']:
                    if endpoint_type in data:
                        return endpoint_type
        except yaml.YAMLError:
            pass
        return None

# LSP server integration
class MXCPLSPServer:
    def on_document_open(self, document_uri: str):
        """Handle document open and apply appropriate schema"""
        # Skip .sql files - let dbt extension handle them
        if document_uri.endswith('.sql'):
            return
            
        content = self.get_document_content(document_uri)
        schema = SchemaDetector.detect_schema_from_content(document_uri, content)
        
        if schema:
            # Register schema for this specific document
            self.yaml_service.add_schema_for_document(document_uri, schema)
            
    def on_document_change(self, document_uri: str, changes: List[TextDocumentContentChangeEvent]):
        """Re-detect schema on content changes"""
        # Skip .sql files
        if document_uri.endswith('.sql'):
            return
            
        # Only re-detect if changes might affect root-level keys
        if self.might_affect_schema_detection(changes):
            content = self.get_updated_content(document_uri, changes)
            schema = SchemaDetector.detect_schema_from_content(document_uri, content)
            
            if schema:
                self.yaml_service.update_schema_for_document(document_uri, schema)
```

### VS Code Extension Schema Contributions

```typescript
// Dynamic schema registration in VS Code extension
export function activate(context: vscode.ExtensionContext) {
    // Register schema provider for dynamic detection
    const schemaProvider = vscode.workspace.registerTextDocumentContentProvider(
        'mxcp-schema',
        new MXCPSchemaProvider()
    );
    
    context.subscriptions.push(schemaProvider);
}

class MXCPSchemaProvider implements vscode.TextDocumentContentProvider {
    provideTextDocumentContent(uri: vscode.Uri): string {
        // Provide schema content based on URI
        const schemaName = uri.path;
        return this.getSchemaContent(schemaName);
    }
    
    private getSchemaContent(schemaName: string): string {
        // Load schema from embedded resources or LSP server
        switch (schemaName) {
            case 'endpoint-schema-1.0.0.json':
                return this.loadEndpointSchema();
            case 'mxcp-site-schema-1.0.0.json':
                return this.loadSiteSchema();
            default:
                return '{}';
        }
    }
}

// Package.json contributions
{
    "contributes": {
        "yamlValidation": [
            {
                "fileMatch": ["mxcp-site.yml"],
                "url": "mxcp-schema:///mxcp-site-schema-1.0.0.json"
            }
        ],
        "languages": [
            {
                "id": "mxcp-yaml",
                "aliases": ["MXCP YAML"],
                "extensions": [".yml", ".yaml"],
                "filenames": ["mxcp-site.yml"]
            }
        ]
    },
    "extensionDependencies": [
        "redhat.vscode-yaml"
        // Note: dbt extension is recommended but not required
        // Users can install "bastienboutonnet.vscode-dbt" for .sql file support
    ]
}
```

### Error Handling & Diagnostics

```