# Customizable SQL Tool Descriptions

**Issue:** [#123](https://github.com/raw-labs/mxcp/issues/123)
**Date:** 2026-03-24

## Problem

The three built-in SQL tools (`execute_sql_query`, `list_tables`, `get_table_schema`) have hardcoded MCP `description` fields that are generic (e.g., "Execute a SQL query against the DuckDB database"). When an MXCP project targets a specific dataset, these descriptions provide no domain context to the LLM, leading to worse tool selection and query quality.

## Solution

Allow each SQL tool's `description` to be configured in `mxcp-site.yml` via a nested per-tool object under `sql_tools`.

### Config Shape

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

All per-tool fields are optional. When omitted, the existing hardcoded defaults are used. The existing `sql_tools: enabled: true` config remains valid with no breaking change.

### Config Model

A new `SiteSqlToolConfigModel` with a single optional field:

```python
class SiteSqlToolConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str | None = None
```

`SiteSqlToolsConfigModel` gains three optional fields:

```python
class SiteSqlToolsConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    enabled: bool = False
    execute_sql_query: SiteSqlToolConfigModel = Field(default_factory=SiteSqlToolConfigModel)
    list_tables: SiteSqlToolConfigModel = Field(default_factory=SiteSqlToolConfigModel)
    get_table_schema: SiteSqlToolConfigModel = Field(default_factory=SiteSqlToolConfigModel)
```

### MCP Registration

In `_register_duckdb_features`, each `@self.mcp.tool(...)` decorator reads the description from config with a fallback to the current hardcoded string:

```python
description = self.site_config.sql_tools.execute_sql_query.description \
    or "Execute a SQL query against the DuckDB database and return the results as a list of records"
```

Same pattern for `list_tables` and `get_table_schema`. Default descriptions stay at the registration call site (not in the model), since all three tools share the same model type but have different defaults.

### Files Changed

1. `src/mxcp/server/core/config/models.py` — Add `SiteSqlToolConfigModel`, update `SiteSqlToolsConfigModel`
2. `src/mxcp/server/interfaces/server/mcp.py` — Read descriptions from config in `_register_duckdb_features`
3. `docs/schemas/site-config.md` — Document new per-tool description fields
4. `tests/` — Unit test verifying custom descriptions appear in registered MCP tools

### Testing

- Config with no per-tool overrides still works (backward compatibility)
- Config with custom descriptions propagates them to MCP tool registration
- Config with partial overrides (e.g., only `execute_sql_query`) works; others keep defaults
- Invalid fields under per-tool config are rejected (`extra="forbid"`)
