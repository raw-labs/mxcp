# Customizable SQL Tool Descriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow per-tool MCP `description` to be configured in `mxcp-site.yml` for the three built-in SQL tools.

**Architecture:** Add a `SiteSqlToolConfigModel` Pydantic model with an optional `description` field. Add three optional instances of it to `SiteSqlToolsConfigModel`. In `_register_duckdb_features`, read descriptions from config with hardcoded fallbacks.

**Tech Stack:** Python, Pydantic, FastMCP

**Spec:** `docs/superpowers/specs/2026-03-24-sql-tool-descriptions-design.md`

---

### Task 1: Add config model and unit tests

**Files:**
- Modify: `src/mxcp/server/core/config/models.py:77-81`
- Modify: `tests/server/test_site_config_model.py`

- [ ] **Step 1: Write failing tests for the new config fields**

Add to `tests/server/test_site_config_model.py`:

```python
def test_sql_tools_default_descriptions(tmp_path: Path):
    """sql_tools with only enabled: true still works (backward compat)."""
    cfg = {**_base_config(), "sql_tools": {"enabled": True}}
    model = SiteConfigModel.model_validate(cfg, context={"repo_root": tmp_path})
    assert model.sql_tools.enabled is True
    assert model.sql_tools.execute_sql_query.description is None
    assert model.sql_tools.list_tables.description is None
    assert model.sql_tools.get_table_schema.description is None


def test_sql_tools_custom_descriptions(tmp_path: Path):
    """Per-tool descriptions are parsed from config."""
    cfg = {
        **_base_config(),
        "sql_tools": {
            "enabled": True,
            "execute_sql_query": {"description": "Run queries on countries"},
            "list_tables": {"description": "List country tables"},
            "get_table_schema": {"description": "Show country table schemas"},
        },
    }
    model = SiteConfigModel.model_validate(cfg, context={"repo_root": tmp_path})
    assert model.sql_tools.execute_sql_query.description == "Run queries on countries"
    assert model.sql_tools.list_tables.description == "List country tables"
    assert model.sql_tools.get_table_schema.description == "Show country table schemas"


def test_sql_tools_partial_descriptions(tmp_path: Path):
    """Only some tools have custom descriptions; others stay None."""
    cfg = {
        **_base_config(),
        "sql_tools": {
            "enabled": True,
            "execute_sql_query": {"description": "Custom query desc"},
        },
    }
    model = SiteConfigModel.model_validate(cfg, context={"repo_root": tmp_path})
    assert model.sql_tools.execute_sql_query.description == "Custom query desc"
    assert model.sql_tools.list_tables.description is None
    assert model.sql_tools.get_table_schema.description is None


def test_sql_tools_rejects_unknown_tool_fields(tmp_path: Path):
    """extra=forbid rejects unknown keys inside per-tool config."""
    cfg = {
        **_base_config(),
        "sql_tools": {
            "enabled": True,
            "execute_sql_query": {"description": "ok", "limit": 100},
        },
    }
    with pytest.raises(Exception):
        SiteConfigModel.model_validate(cfg, context={"repo_root": tmp_path})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/server/test_site_config_model.py -v -k "sql_tools"`
Expected: FAIL — `SiteSqlToolsConfigModel` doesn't have the new fields yet.

- [ ] **Step 3: Add `SiteSqlToolConfigModel` and update `SiteSqlToolsConfigModel`**

In `src/mxcp/server/core/config/models.py`, replace lines 77-81:

```python
class SiteSqlToolConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str | None = Field(default=None, min_length=1)


class SiteSqlToolsConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    execute_sql_query: SiteSqlToolConfigModel = Field(default_factory=SiteSqlToolConfigModel)
    list_tables: SiteSqlToolConfigModel = Field(default_factory=SiteSqlToolConfigModel)
    get_table_schema: SiteSqlToolConfigModel = Field(default_factory=SiteSqlToolConfigModel)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/server/test_site_config_model.py -v -k "sql_tools"`
Expected: All 4 new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mxcp/server/core/config/models.py tests/server/test_site_config_model.py
git commit -m "Add per-tool description config for SQL tools (#123)"
```

---

### Task 2: Wire descriptions into MCP tool registration

**Files:**
- Modify: `src/mxcp/server/interfaces/server/mcp.py:1721-1819` (the `_register_duckdb_features` method)

- [ ] **Step 1: Update `_register_duckdb_features` to read descriptions from config**

In the three `@self.mcp.tool(...)` decorator calls, replace the hardcoded `description` with a config lookup + fallback.

For `execute_sql_query` (around line 1728):
```python
@self.mcp.tool(
    name="execute_sql_query",
    description=(
        self.site_config.sql_tools.execute_sql_query.description
        or "Execute a SQL query against the DuckDB database and return the results as a list of records"
    ),
    ...
)
```

For `list_tables` (around line 1809):
```python
@self.mcp.tool(
    name="list_tables",
    description=(
        self.site_config.sql_tools.list_tables.description
        or "List all tables in the DuckDB database"
    ),
    ...
)
```

For `get_table_schema` (around line 1893):
```python
@self.mcp.tool(
    name="get_table_schema",
    description=(
        self.site_config.sql_tools.get_table_schema.description
        or "Get the schema for a specific table in the DuckDB database"
    ),
    ...
)
```

- [ ] **Step 2: Run existing integration tests to verify nothing breaks**

Run: `python -m pytest tests/server/test_integration.py -v -k "sql_tools_registration"`
Expected: PASS — existing test still sees the default description.

- [ ] **Step 3: Commit**

```bash
git add src/mxcp/server/interfaces/server/mcp.py
git commit -m "Wire per-tool descriptions into MCP registration (#123)"
```

---

### Task 3: Update documentation

**Files:**
- Modify: `docs/schemas/site-config.md`

- [ ] **Step 1: Update the SQL Tools Configuration section**

Replace the SQL Tools Configuration section (around line 239-260) with:

```markdown
## SQL Tools Configuration

Enable built-in SQL tools for direct database access. Each tool's MCP `description` can be customized to provide domain-specific context to the LLM.

```yaml
sql_tools:
  enabled: true
  execute_sql_query:
    description: "Run SQL queries against the countries and capitals database"
  list_tables:
    description: "List available tables about countries and their capitals"
  get_table_schema:
    description: "Inspect the schema of country and capital tables"
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable built-in SQL tools. |
| `execute_sql_query` | object | - | Configuration for the SQL query tool. |
| `list_tables` | object | - | Configuration for the table listing tool. |
| `get_table_schema` | object | - | Configuration for the schema inspection tool. |

### Per-Tool Configuration

Each tool object supports:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | string | *(see below)* | Custom MCP tool description shown to the LLM. |

When `description` is omitted, the built-in default is used:

| Tool | Default Description |
|------|-------------|
| `execute_sql_query` | "Execute a SQL query against the DuckDB database and return the results as a list of records" |
| `list_tables` | "List all tables in the DuckDB database" |
| `get_table_schema` | "Get the schema for a specific table in the DuckDB database" |

**Security Note:** Only enable for trusted environments. Consider using custom tools with proper access controls for production.
```

- [ ] **Step 2: Commit**

```bash
git add docs/schemas/site-config.md
git commit -m "Document per-tool SQL tool descriptions (#123)"
```
