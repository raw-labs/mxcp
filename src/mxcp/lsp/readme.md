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
└── models/                 # dbt models (SQL language support)
    ├── staging/
    └── marts/
```

| Detection Method | Schema Applied | LSP Features |
| ---------------- | ----------------------------- | ------------------------------------------------------- |
| **Filename**: `mxcp-site.yml` | `mxcp-site-schema-1.0.0.json` | Site config validation, profile completion |
| **Content**: Contains `tool:` key | `endpoint-schema-1.0.0.json` | Tool validation, parameter completion, SQL highlighting |
| **Content**: Contains `resource:` key | `endpoint-schema-1.0.0.json` | Resource validation, URI completion |
| **Content**: Contains `prompt:` key | `endpoint-schema-1.0.0.json` | Prompt validation, template variable checking |
| **Extension**: `*.sql` files | SQL language support | dbt model validation, ref() completion |

**Schema Detection Logic**:
1. **Site Config**: Files named `mxcp-site.yml` (exact match)
2. **Endpoint Types**: Parse YAML content and detect root-level keys:
   - `tool:` → Tool endpoint schema
   - `resource:` → Resource endpoint schema  
   - `prompt:` → Prompt endpoint schema
3. **SQL Files**: Any `.sql` file gets SQL language support
4. **Fallback**: Unknown YAML files get basic YAML support without MXCP schemas

---

## Implementation Roadmap

### Phase 1: Language Server Core Features

**Target**: Functional LSP server with essential YAML and SQL support

| #     | Feature                        | Implementation Specification                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | **Content-based schema detection** | **Definition**: Dynamically detect and apply MXCP schemas based on file content rather than directory patterns.<br>**Implementation**: <br>• Parse YAML on file open/change to detect root keys (`tool:`, `resource:`, `prompt:`)<br>• Use filename detection for `mxcp-site.yml`<br>• Register schemas dynamically: `yamlLanguageService.addSchema()` per file<br>• Cache detection results for performance<br>**User Experience**: Schema validation works regardless of file organization |
| **2** | **SQL semantic highlighting**  | **Definition**: Detect SQL blocks in YAML (`source.code: \|`) and apply SQL syntax highlighting.<br>**Implementation**:<br>• Use MXCP's existing YAML parsing from `mxcp.endpoints.loader`<br>• Return semantic tokens for SQL keywords, strings, identifiers<br>• Integrate with DuckDB session for SQL validation<br>**User Experience**: SQL code blocks look identical to `.sql` files                                                                                                                |
| **3** | **Intelligent autocompletion** | **Definition**: Context-aware completion for SQL and YAML using MXCP internals.<br>**Implementation**:<br>• **SQL**: Use existing `DuckDBSession` to query `INFORMATION_SCHEMA`<br>• **YAML**: Leverage `mxcp.endpoints.schema` validation for completions<br>• **dbt**: Use MXCP's dbt integration to parse `manifest.json`<br>• **Template vars**: Extract parameters from tool definitions using existing parsers<br>**User Experience**: Typing `SEL` completes to `SELECT`, table names autocomplete |
| **4** | **Real-time diagnostics**      | **Definition**: Use MXCP's validation engine for comprehensive error checking.<br>**Implementation**:<br>• **SQL**: Use `DuckDBSession.execute()` with `EXPLAIN` for syntax validation<br>• **YAML**: Call `mxcp.endpoints.schema.validate_endpoint_payload()` directly<br>• **Config**: Use `mxcp.config.site_config.load_site_config()` for site validation<br>• Map validation errors to LSP diagnostic format<br>**User Experience**: Red squiggles under errors, hover for details                   |
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
| **14** | **dbt lineage integration**     | **Definition**: Leverage MXCP's dbt integration for model dependencies.<br>**Implementation**:<br>• Use existing dbt adapter configuration from MXCP<br>• Parse `manifest.json` using MXCP's dbt utilities<br>• Provide hover info for `{{ ref('model') }}` references<br>• Optional: Webview with interactive lineage graph<br>**User Experience**: F12 on dbt refs, dependency visualization                  |
| **15** | **Drift detection integration** | **Definition**: Use MXCP's drift detection system for schema warnings.<br>**Implementation**:<br>• Call `mxcp.drift.detector.detect_drift()` directly<br>• Use `mxcp.drift.snapshot.create_snapshot()` for baseline creation<br>• Display warnings as diagnostics for breaking changes<br>• Provide quick-fix actions to update snapshots<br>**User Experience**: Immediate feedback on schema-breaking changes |

---

## Distribution & Installation Strategy

### Overview

MXCP uses a simplified distribution approach: the LSP server is built into the main MXCP CLI as a subcommand (`mxcp lsp`), eliminating the need for separate binaries or version management.

### Phase 1: Unified Python Package

| Step                  | Implementation                                                                                       | Rationale                                            |
| --------------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| **Package structure** | `toml<br>[project.scripts]<br>mxcp = "mxcp.__main__:cli"<br># LSP server is mxcp lsp subcommand<br>` | Single binary, no version skew, simpler distribution |
| **Universal wheel**   | `python -m build && twine upload dist/*`                                                             | Fast installation, cross-platform compatibility      |
| **Version strategy**  | Use semantic versioning, LSP compatibility guaranteed                                                | No separate versioning needed for LSP                |

### Phase 2: VS Code Extension Installation Logic

```typescript
// Extension activation pseudocode
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
    // 2. Check PATH for existing installation
    // 3. Verify version compatibility with `mxcp --version`
    // 4. Test LSP support with `mxcp lsp --help`
    return foundPath;
}

async function installMXCPIsolated(context: ExtensionContext): Promise<string> {
   const venvPath = path.join(context.globalStorageUri.fsPath, "mxcp-venv");

   // Create isolated virtual environment
   await exec("python3", ["-m", "venv", venvPath]);

   // Install specific MXCP version
   const pythonPath = path.join(venvPath, "bin", "python");
   await exec(pythonPath, ["-m", "pip", "install", `mxcp==${REQUIRED_VERSION}`]);

   return path.join(venvPath, "bin", "mxcp");
}

async function startLSPClient(mxcpPath: string) {
    // Start LSP server using mxcp lsp subcommand
    const client = new LanguageClient(
     "mxcp-lsp",
     "MXCP Language Server",
     {
       command: mxcpPath,
       args: ["lsp", "--stdio"], // Use stdio mode for LSP communication
     },
     {
       documentSelector: [
         // Content-based detection - any YAML file could be an MXCP file
         { scheme: "file", language: "yaml" },
         { scheme: "file", language: "sql" },
         // Site config by filename
         { scheme: "file", pattern: "**/mxcp-site.yml" },
       ],
     }
   );
   
   await client.start();
}
```

### Phase 3: Installation Flow

| Scenario             | Behavior                            | Implementation                               |
| -------------------- | ----------------------------------- | -------------------------------------------- |
| **Fresh install**    | Create isolated venv, install MXCP  | Use `context.globalStorageUri` for isolation |
| **Existing install** | Verify version and LSP support      | Check `mxcp --version` and `mxcp lsp --help` |
| **Version mismatch** | Offer upgrade in isolated venv      | Never modify user's global Python            |
| **pipx integration** | Provide command to install globally | `pipx install mxcp` for system-wide access   |
| **Uninstall**        | Clean up extension venv             | Delete venv on extension removal             |

### Configuration & Settings

```json
// VS Code settings
{
   "mxcp.cliPath": "", // Manual path override
   "mxcp.profile": "dev", // Default profile for LSP
   "mxcp.autoValidate": true, // Validate on save
   "mxcp.showInlayHints": true, // Show parameter defaults
   "mxcp.logLevel": "info", // LSP logging level
   "mxcp.enableTelemetry": false, // Usage analytics
   "mxcp.fileDetection": {
     "enableContentBasedDetection": true, // Detect schemas from file content
     "customPatterns": { // Optional: user-defined patterns for schema detection
       "tools": ["**/my-tools/*.yml"],
       "resources": ["**/data/*.yml"]
     }
   }
}
```

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
        content = self.get_document_content(document_uri)
        schema = SchemaDetector.detect_schema_from_content(document_uri, content)
        
        if schema:
            # Register schema for this specific document
            self.yaml_service.add_schema_for_document(document_uri, schema)
            
    def on_document_change(self, document_uri: str, changes: List[TextDocumentContentChangeEvent]):
        """Re-detect schema on content changes"""
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

// Package.json contributions - simplified since we use content detection
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
    }
}
```

### Error Handling & Diagnostics

```