# MCP Server Instructions Support

**Issue:** https://github.com/raw-labs/mxcp/issues/202
**Date:** 2026-03-23

## Problem

MXCP projects have no way to provide global instructions to MCP clients. Project authors work around this by duplicating rules across individual tool descriptions or embedding them in tool results. The MCP spec supports an `instructions` field in the `InitializeResult` response, which clients can add to the system prompt.

## Design

Add a top-level `instructions` field to `mxcp-site.yml` that gets passed through to the MCP `InitializeResult`.

### Config format

```yaml
mxcp: 1
project: my-project
profile: dev
instructions: |
  Tools return objid. That is useful to query the system further
  with other tools. Don't surface objid to users.
  Tool failures are expected because parameters are tricky.
  When a failure occurs, check the error carefully and see if
  another tool could help.
```

The field is optional and defaults to `None` (no instructions sent).

### Changes

#### 1. `SiteConfigModel` (`src/mxcp/server/core/config/models.py`)

Add field to `SiteConfigModel`:

```python
class SiteConfigModel(BaseModel):
    ...
    instructions: str | None = None
    ...
```

#### 2. `RAWMCP._initialize_fastmcp()` (`src/mxcp/server/interfaces/server/mcp.py`)

Pass `instructions` to `FastMCP`:

```python
def _initialize_fastmcp(self) -> None:
    fastmcp_kwargs: dict[str, Any] = {
        "name": "MXCP Server",
        "instructions": self.site_config.instructions,
        "stateless_http": self.stateless_http,
        ...
    }
```

`FastMCP.__init__` already accepts `instructions: str | None`. Passing `None` preserves current behavior for projects without the field.

### Hot reload

No special handling needed. `_initialize_fastmcp()` is called on reload and reads from the freshly loaded `self.site_config`.

### Testing

1. **Config model test** (`tests/server/test_site_config_model.py`): Verify `instructions` parses correctly when present and defaults to `None` when absent.
2. **Integration test**: Verify instructions reach the MCP initialize response by starting a server with the test harness and inspecting the result.

### Documentation

Update the `mxcp-site.yml` reference in docs to document the new `instructions` field.
