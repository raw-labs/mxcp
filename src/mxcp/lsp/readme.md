# MXCP Editor Tooling – Feature Reference  

## ✅ Already Implemented (SQL-inside-YAML)

| Feature | What it is | What the user sees | Why it matters |
|---------|------------|--------------------|----------------|
| **Semantic tokens** | Colour-codes SQL keywords, strings, numbers, etc. inside the `source.code` block. | Syntax highlighting identical to a real SQL file. | Visual parsing speed; immediate spotting of typos. |
| **Autocompletion** | Offers table names, column names, functions while you type SQL. | <kbd>Ctrl-Space</kbd> after `SEL` → gets `SELECT`. | Reduces memorisation; fewer typos. |
| **Diagnostics** | Parses SQL and surfaces syntax / name errors inline. | Red underline under `FRM` with tooltip “Did you mean FROM?”. | Catches run-time errors early. |

---

## 1 Language-Server Track (runs via **`mxcp lsp`**)

### Core Features

| # | Feature | Analytical description |
|---|---------|------------------------|
| **1** | **Schema registration** | *Definition* – Load MXCP’s JSON Schema into the embedded YAML language service.<br> *User view* – As soon as they open any `*.yml` in `tools/`, unknown keys turn red, required keys are warned about, and <kbd>Ctrl-Space</kbd> completes valid field names.<br> *Why essential* – Prevents invalid specs **before** they ever hit `mxcp validate`; avoids frustration of silent runtime failures.<br> *Implementation path* – One call: `yamlLanguageService.addSchema("mxcp-schema", schemaJson);` on LSP initialise. |
| **2** | **Completion & hover (from schema)** | *Definition* – The same schema also carries descriptions and enumerated values; expose them via the language service.<br> *User view* – Hovering `type:` shows “Data type of parameter”; typing `fo` then <kbd>Tab</kbd> expands to `format:` when applicable.<br> *Why* – New team members can write correct YAML without reading docs in another tab.<br> *Implementation* – Comes almost for free once Feature 1 is set up. |
| **3** | **CodeLens stubs – “▶ Run Tool” / “🧪 Run Tests”** | *Definition* – Tiny inline links provided by the LS that VS Code renders above a section.<br>*User view* – A grey “▶ Run Tool” appears above every `tool:`; “🧪 Run Tests” above the `tests:` array.<br>*Why* – Makes running a tool/test a **one-click** action; no copy-pasting CLI commands.<br>*Implementation* – LS answers `textDocument/codeLens` with position + title; UI hookup in the extension shows them. |
| **4** | **Execution bridge** | *Definition* – The LS receives a “run” request (triggered from the CodeLens), spawns a real child process (`mxcp query` or `mxcp test`) and streams its stdout/stderr back to the client via `window/logMessage` notifications.<br>*User view* – Output appears in real time in the “MXCP Results” pane; long runs can be cancelled.<br>*Why* – Collapses the “edit ➜ save ➜ switch terminal ➜ run ➜ read output ➜ switch back” loop into a single click.<br>*Implementation* – Use Node’s `child_process.spawn`, set `stdio: ‘pipe’`; send custom `mxcp/runStarted` & `mxcp/runEnded` notifications so the extension can show a spinner. |
| **5** | **Execution-error ➜ Diagnostics** | *Definition* – Convert JSON error payloads from `mxcp` (e.g. SQL syntax, missing parameter) into LSP Diagnostics pointing at the offending YAML lines.<br>*User view* – Same red underline you get for schema errors, but for runtime issues; Problems panel lists them.<br>*Why* – Users fix issues where they write them instead of scrolling through terminal logs.<br>*Implementation* – Parse error JSON, look up corresponding AST node, call `connection.sendDiagnostics`. |

### Secondary Features

| # | Feature | Analytical description |
|---|---------|------------------------|
| 1 | **Inlay hints for defaults** | Shows grey “= 2.5” next to `min_magnitude`. Quick read of defaults without opening the block. |
| 2 | **Cross-file rename & workspace symbols** | Rename a tool once, LS updates all references; quick search across workspace. |
| 3 | **Drift-check diagnostics** | Calls `mxcp drift-check --json`; surfaces breaking changes as warnings in changed files. |
| 4 | **dbt model go-to-definition** | F12 on `FROM sales_daily` jumps to the dbt SQL file if present. |

---

## 2 VS Code Extension Track

### Core Features

| # | Feature | Analytical description |
|---|---------|------------------------|
| **1** | **Depend on Red Hat YAML extension** | *Definition* – Declare `"extensionDependencies": ["redhat.vscode-yaml"]`.<br>*User view* – They never install YAML tooling manually; all YAML folding/anchoring works out of the box.<br>*Why* – Re-uses battle-tested YAML support; keeps our VSIX size tiny.<br>*Implementation* – One line in `package.json`. |
| **2** | **`yamlValidation` contribution** | *Definition* – Tell VS Code which files the schema applies to.<br>*User view* – MXCP YAML files instantly pick up validation with zero config.<br>*Why* – Without this, only opened files that explicitly declare `$schema` get validation; friction for newcomers.<br>*Implementation* – In `package.json` → `contributes.yamlValidation` with `fileMatch` = `["*/tools/*.yml", …]`. |
| **3** | **Output channel `mxcp-results`** | *Definition* – A dedicated VS Code Output panel created by the extension, separate from generic “Output”.<br>*User view* – When they click Run, this panel pops up and streams rows/errors with ANSI colours.<br>*Why* – Keeps MXCP output organised; users can clear or save it without mixing with other extensions’ logs.<br>*Implementation* – `const out = window.createOutputChannel("MXCP Results");` then listen to LS log notifications. |
| **4** | **CodeLens UI hookup** | *Definition* – Registers a `CodeLensProvider` that surfaces the LS-sent CodeLens objects.<br>*User view* – The grey “▶ Run Tool” links actually render and call back into the LS when clicked.<br>*Why* – Without this, the server emits CodeLens but nothing shows up; links are essential to the single-click workflow.<br>*Implementation* – Translate LS command → execute VS Code command sending a `workspace/executeCommand` back to LS. |
| **5** | **Status-bar progress & cancel** | *Definition* – Shows a spinner icon while a run is in flight; clicking it sends a cancel to LS which kills the child process.<br>*User view* – Immediate feedback that something is running; peace of mind + control.<br>*Why* – Prevents users from thinking VS Code hung; avoids runaway queries on large data.<br>*Implementation* – On `mxcp/runStarted`, `window.withProgress({...})`; on `mxcp/runEnded` dispose; set an `AbortController` or send custom cancel request. |

### Secondary Features

| # | Feature | Analytical description |
|---|---------|------------------------|
| 1 | **New-project wizard & snippets** | Quick-pick flow to scaffold `mxcp init`; tab-trigger snippets for blocks. |
| 2 | **Prettier-YAML formatter** | Ensures consistent indentation and keeps `code: |` blocks intact. |
| 3 | **Notebook-style result viewer** | Webview collects each run as a cell with sortable tables, charts. |
| 4 | **DAG / graph visualiser** | Renders Mermaid/Graphviz of tool ↔ resource dependencies for architecture overview. |
| 5 | **CI workflow generator** | Writes a GitHub Action that runs `mxcp validate`, `test`, `drift-check` on every PR. |
| 6 | **Opt-in telemetry** | Counts feature usage to guide roadmap; anonymous, GDPR-safe. |

---

### How to read this table

*Everything in “Core” is what we must finish to avoid a frustrating, terminal-heavy workflow.*  
*Everything in “Secondary” adds polish once users are productive.*

Deliver core LS features 1–5 **and** core VS Code features 1–5 to reach a solid v1.
