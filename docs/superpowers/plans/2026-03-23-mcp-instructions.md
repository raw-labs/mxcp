# MCP Instructions Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow MXCP projects to define global MCP server instructions in `mxcp-site.yml` that get returned to clients in the `InitializeResult`.

**Architecture:** Add an optional `instructions` field to `SiteConfigModel`, thread it through `RAWMCP._initialize_fastmcp()` into `FastMCP(instructions=...)`. No new files needed.

**Tech Stack:** Python, Pydantic, FastMCP, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-mcp-instructions-design.md`

---

### Task 1: Add `instructions` field to SiteConfigModel

**Files:**
- Modify: `src/mxcp/server/core/config/models.py:127-139` (SiteConfigModel)
- Test: `tests/server/test_site_config_model.py`

- [ ] **Step 1: Write failing tests**

Add two tests to `tests/server/test_site_config_model.py`:

```python
def test_instructions_default_is_none(tmp_path: Path):
    """instructions field defaults to None when not provided."""
    model = SiteConfigModel.model_validate(_base_config(), context={"repo_root": tmp_path})
    assert model.instructions is None


def test_instructions_accepted_when_provided(tmp_path: Path):
    """instructions field is parsed when present in config."""
    config = _base_config()
    config["instructions"] = "Always call tool X before tool Y.\nDon't surface objid to users."
    model = SiteConfigModel.model_validate(config, context={"repo_root": tmp_path})
    assert model.instructions == "Always call tool X before tool Y.\nDon't surface objid to users."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/server/test_site_config_model.py::test_instructions_default_is_none tests/server/test_site_config_model.py::test_instructions_accepted_when_provided -v`
Expected: FAIL — `SiteConfigModel` has `extra="forbid"`, so the second test raises a validation error, and the first fails on missing attribute.

- [ ] **Step 3: Add the field to SiteConfigModel**

In `src/mxcp/server/core/config/models.py`, add to `SiteConfigModel`:

```python
class SiteConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mxcp: Literal[1] = 1
    project: str
    profile: str
    instructions: str | None = None    # <-- ADD THIS LINE
    secrets: list[str] = Field(default_factory=list)
    # ... rest unchanged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/server/test_site_config_model.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mxcp/server/core/config/models.py tests/server/test_site_config_model.py
git commit -m "Add instructions field to SiteConfigModel (#202)"
```

---

### Task 2: Pass instructions to FastMCP and verify end-to-end

**Files:**
- Modify: `src/mxcp/server/interfaces/server/mcp.py:643-662` (_initialize_fastmcp)
- Modify: `tests/server/fixtures/mcp/mxcp-site.yml` (add instructions to test fixture)
- Test: `tests/server/test_mcp.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/server/test_mcp.py`:

```python
def test_instructions_passed_to_fastmcp(mcp_server):
    """Verify instructions from site config reach the FastMCP instance."""
    assert mcp_server.mcp.instructions == "Test instructions for MCP clients."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/server/test_mcp.py::test_instructions_passed_to_fastmcp -v`
Expected: FAIL — `mcp_server.mcp.instructions` is `None`.

- [ ] **Step 3: Add instructions to the test fixture**

In `tests/server/fixtures/mcp/mxcp-site.yml`, add:

```yaml
mxcp: 1
project: test_project
profile: test_profile
instructions: "Test instructions for MCP clients."
```

- [ ] **Step 4: Add instructions to fastmcp_kwargs**

In `RAWMCP._initialize_fastmcp()`, add `instructions` to the kwargs dict:

```python
def _initialize_fastmcp(self) -> None:
    """Initialize the FastMCP server."""
    fastmcp_kwargs: dict[str, Any] = {
        "name": "MXCP Server",
        "instructions": self.site_config.instructions,    # <-- ADD THIS LINE
        "stateless_http": self.stateless_http,
        "json_response": self.json_response,
        "host": self.host,
        "port": self.port,
    }
    # ... rest unchanged
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/server/test_mcp.py -v`
Expected: All tests PASS, including the new `test_instructions_passed_to_fastmcp`.

- [ ] **Step 6: Commit**

```bash
git add src/mxcp/server/interfaces/server/mcp.py tests/server/fixtures/mcp/mxcp-site.yml tests/server/test_mcp.py
git commit -m "Pass instructions from site config to FastMCP (#202)"
```

---

### Task 3: Update documentation

**Files:**
- Modify: `docs/schemas/site-config.md`

- [ ] **Step 1: Add instructions to the complete example**

In `docs/schemas/site-config.md`, add `instructions` to the complete example after the `profile` line:

```yaml
mxcp: 1
project: my-analytics
profile: default

instructions: |
  Tools return objid. That is useful to query the system further
  with other tools. Don't surface objid to users.
  Tool failures are expected. When a failure occurs, check the
  error carefully and see if another tool could help.

secrets:
  - db_credentials
  - api_key
```

- [ ] **Step 2: Add instructions to the Root Fields table**

Add a row after the `profile` row:

```markdown
| `instructions` | string | No | `null` | Global instructions for MCP clients. Returned in the MCP `InitializeResult` and typically added to the LLM's system prompt by the client. |
```

- [ ] **Step 3: Add an Instructions section after "Project and Profile"**

Add a new section:

```markdown
## Instructions

Provide global instructions that MCP clients can use to improve how LLMs interact with your server's tools.

~~~yaml
instructions: |
  Tools return objid. That is useful to query the system further
  with other tools. Don't surface objid to users.
  Tool failures are expected because parameters are tricky.
  When a failure occurs, check the error carefully and see if
  another tool could help.
~~~

Instructions are returned in the MCP `InitializeResult` response. Clients like Claude Desktop typically add them to the LLM's system prompt.

Use this instead of duplicating general rules across individual tool descriptions.
```

- [ ] **Step 4: Commit**

```bash
git add docs/schemas/site-config.md
git commit -m "Document instructions field in site config schema (#202)"
```
