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

MXCP tooling supports the complete project structure:

```
your-project/
├── mxcp-site.yml           # Site config (mxcp-site-schema-1.0.0.json)
├── tools/                  # Tool definitions (endpoint-schema-1.0.0.json)
│   ├── query_earthquakes.yml
│   └── analyze_sales.yml
├── resources/              # Resource definitions (endpoint-schema-1.0.0.json)
│   ├── earthquake_data.yml
│   └── sales_cache.yml
├── prompts/                # Prompt templates (endpoint-schema-1.0.0.json)
│   └── analysis_prompt.yml
└── models/                 # dbt models (SQL language support)
    ├── staging/
    └── marts/
```

| File Pattern      | Schema Applied                | LSP Features                                            |
| ----------------- | ----------------------------- | ------------------------------------------------------- |
| `mxcp-site.yml`   | `mxcp-site-schema-1.0.0.json` | Site config validation, profile completion              |
| `tools/*.yml`     | `endpoint-schema-1.0.0.json`  | Tool validation, parameter completion, SQL highlighting |
| `resources/*.yml` | `endpoint-schema-1.0.0.json`  | Resource validation, URI completion                     |
| `prompts/*.yml`   | `endpoint-schema-1.0.0.json`  | Prompt validation, template variable checking           |
| `models/**/*.sql` | SQL language support          | dbt model validation, ref() completion                  |

---

## Implementation Roadmap

### Phase 1: Language Server Core Features

**Target**: Functional LSP server with essential YAML and SQL support

| #     | Feature                        | Implementation Specification                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | **Multi-schema registration**  | **Definition**: Load MXCP JSON schemas directly from internal schema registry and register with YAML language service.<br>**Implementation**: <br>• Use existing `mxcp.config.schemas` module to load schemas<br>• Register with patterns: `yamlLanguageService.addSchema()`<br>• Map `tools/*.yml` → endpoint schema, `mxcp-site.yml` → site schema<br>• Leverage MXCP's existing schema validation logic<br>**User Experience**: Real-time validation, autocomplete for YAML keys, hover documentation  |
| **2** | **SQL semantic highlighting**  | **Definition**: Detect SQL blocks in YAML (`source.code: \|`) and apply SQL syntax highlighting.<br>**Implementation**:<br>• Use MXCP's existing YAML parsing from `mxcp.endpoints.loader`<br>• Return semantic tokens for SQL keywords, strings, identifiers<br>• Integrate with DuckDB session for SQL validation<br>**User Experience**: SQL code blocks look identical to `.sql` files                                                                                                                |
| **3** | **Intelligent autocompletion** | **Definition**: Context-aware completion for SQL and YAML using MXCP internals.<br>**Implementation**:<br>• **SQL**: Use existing `DuckDBSession` to query `INFORMATION_SCHEMA`<br>• **YAML**: Leverage `mxcp.endpoints.schema` validation for completions<br>• **dbt**: Use MXCP's dbt integration to parse `manifest.json`<br>• **Template vars**: Extract parameters from tool definitions using existing parsers<br>**User Experience**: Typing `SEL` completes to `SELECT`, table names autocomplete |
| **4** | **Real-time diagnostics**      | **Definition**: Use MXCP's validation engine for comprehensive error checking.<br>**Implementation**:<br>• **SQL**: Use `DuckDBSession.execute()` with `EXPLAIN` for syntax validation<br>• **YAML**: Call `mxcp.endpoints.schema.validate_endpoint_payload()` directly<br>• **Config**: Use `mxcp.config.site_config.load_site_config()` for site validation<br>• Map validation errors to LSP diagnostic format<br>**User Experience**: Red squiggles under errors, hover for details                   |
| **5** | **CodeLens integration**       | **Definition**: Provide executable actions above tools and tests.<br>**Implementation**:<br>• Use MXCP's endpoint discovery from `mxcp.endpoints.discovery`<br>• Parse tools and tests using existing `mxcp.endpoints.loader`<br>• Return CodeLens at line positions: "▶ Run Tool", "🧪 Run Tests", "✓ Validate"<br>• Register `workspace/executeCommand` handlers<br>**User Experience**: Clickable gray links above each tool definition                                                                |

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
        { scheme: "file", pattern: "**/mxcp-site.yml" },
        { scheme: "file", pattern: "**/tools/*.yml" },
        { scheme: "file", pattern: "**/resources/*.yml" },
        { scheme: "file", pattern: "**/prompts/*.yml" },
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
  "mxcp.enableTelemetry": false // Usage analytics
}
```

---

## Technical Specifications

### LSP Server Interface

```python
# LSP server as mxcp subcommand
# mxcp/cli/lsp.py

@click.command(name="lsp")
@click.option("--stdio", is_flag=True, help="Use stdio for LSP communication")
@click.option("--port", type=int, help="Port for TCP LSP server (for testing)")
@click.option("--profile", help="Profile to use for validation and execution")
@click.option("--log-level", default="info", help="Logging level")
def lsp(stdio: bool, port: Optional[int], profile: Optional[str], log_level: str):
    """Start MXCP Language Server Protocol server"""

    # Load MXCP configuration
    site_config = load_site_config()
    user_config = load_user_config(site_config)

    # Initialize LSP server with full MXCP context
    server = MXCPLSPServer(
        user_config=user_config,
        site_config=site_config,
        profile=profile
    )

    if stdio:
        server.start_io()  # Standard LSP stdio mode
    else:
        server.start_tcp(port or 3000)  # For testing/debugging

# Core LSP server with MXCP integration
class MXCPLSPServer:
    def __init__(self, user_config: UserConfig, site_config: SiteConfig, profile: Optional[str]):
        self.user_config = user_config
        self.site_config = site_config
        self.profile = profile

        # Direct access to MXCP components
        self.db_session = DuckDBSession(user_config, site_config, profile)
        self.validator = EndpointValidator(user_config, site_config)
        self.executor = EndpointExecutor(user_config, site_config, profile)

        # LSP capabilities using MXCP internals
        self.capabilities = {
            "textDocumentSync": TextDocumentSyncKind.Incremental,
            "completionProvider": {"triggerCharacters": [".", "$", "{", "}"]},
            "hoverProvider": True,
            "definitionProvider": True,
            "diagnosticsProvider": True,
            "codeLensProvider": {"resolveProvider": True},
            "executeCommandProvider": {
                "commands": ["mxcp.runTool", "mxcp.runTests", "mxcp.validate"]
            }
        }
```

### Extension Commands

```typescript
// VS Code command contributions
{
    "commands": [
        {
            "command": "mxcp.runTool",
            "title": "Run MXCP Tool",
            "icon": "$(play)"
        },
        {
            "command": "mxcp.runTests",
            "title": "Run MXCP Tests",
            "icon": "$(beaker)"
        },
        {
            "command": "mxcp.validate",
            "title": "Validate MXCP Project",
            "icon": "$(check)"
        },
        {
            "command": "mxcp.installGlobally",
            "title": "Install MXCP Globally (pipx)"
        }
    ]
}

// Command execution using mxcp CLI
async function executeMXCPCommand(command: string, args: string[]): Promise<void> {
    const mxcpPath = await getMXCPPath();
    const process = spawn(mxcpPath, [command, ...args], {
        cwd: workspace.workspaceFolders?.[0]?.uri.fsPath
    });

    // Stream output to MXCP Results panel
    process.stdout.on('data', (data) => {
        outputChannel.append(data.toString());
    });

    process.stderr.on('data', (data) => {
        outputChannel.append(data.toString());
    });
}
```

### Error Handling & Diagnostics

```python
# Direct integration with MXCP error handling
from mxcp.endpoints.schema import SchemaError
from mxcp.engine.duckdb_session import SQLError

class LSPDiagnosticsMapper:
    @staticmethod
    def map_mxcp_error_to_diagnostic(error: Exception, document_uri: str) -> Diagnostic:
        if isinstance(error, SchemaError):
            return Diagnostic(
                range=error.location_range,  # MXCP provides location info
                message=error.message,
                severity=DiagnosticSeverity.Error,
                source="mxcp-schema",
                code=error.error_code
            )
        elif isinstance(error, SQLError):
            return Diagnostic(
                range=error.sql_range,
                message=f"SQL Error: {error.message}",
                severity=DiagnosticSeverity.Error,
                source="mxcp-sql"
            )
        # ... handle other MXCP error types
```

---

## Implementation Priorities

### Minimum Viable Product (MVP)

**Goal**: Eliminate terminal dependency for basic MXCP development

**Must Have**:

- Schema validation using MXCP internals (Features 1, 4)
- SQL highlighting and completion via DuckDBSession (Features 2, 3)
- Direct execution using MXCP executor (Features 5, 6)
- VS Code integration (Features 9, 10, 11)
- Simplified installation (Distribution Phase 1-2)

**Success Criteria**: Developer can create, validate, and test MXCP tools entirely within VS Code using the same engine as the CLI

### Version 1.0

**Goal**: Production-ready development environment

**Adds**:

- Advanced error mapping (Feature 7)
- Profile management via MXCP config (Feature 8)
- Progress indicators (Feature 12)
- Complete installation flow (Distribution Phase 3)

### Future Versions

**Goal**: Advanced productivity features

**Adds**:

- Embedded MCP server testing (Feature 13)
- dbt lineage via MXCP integration (Feature 14)
- Drift detection using MXCP drift system (Feature 15)
- Notebook-style result viewer
- CI workflow generation

---

## Development Guidelines

### Testing Strategy

- **LSP Server**: Unit tests using existing MXCP test infrastructure
- **Integration Tests**: Real MXCP projects with various configurations
- **VS Code Extension**: Extension development host testing, automated UI tests
- **Installation**: Test matrix across Python versions and operating systems

### Documentation Requirements

- **README**: Installation, basic usage, troubleshooting
- **CONTRIBUTING**: Local development setup leveraging existing MXCP dev tools
- **API Reference**: LSP capabilities, extension commands, configuration options

### Release Process

1. Version bump in MXCP package (LSP included automatically)
2. Automated testing across platforms using existing MXCP CI
3. PyPI release for MXCP package (includes LSP server)
4. VS Code Marketplace release for extension
5. Update compatibility matrix and documentation

**Key Advantage**: Since the LSP server is part of MXCP, it automatically stays in sync with CLI features and has access to the complete MXCP ecosystem without any inter-process communication overhead.
