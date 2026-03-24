from pathlib import Path

import pytest
from pydantic import ValidationError

from mxcp.server.core.config.models import SiteConfigModel


def _base_config() -> dict:
    return {
        "mxcp": 1,
        "project": "demo",
        "profile": "dev",
        "profiles": {"dev": {}},
    }


def test_site_config_applies_defaults(tmp_path: Path):
    model = SiteConfigModel.model_validate(_base_config(), context={"repo_root": tmp_path})

    assert model.dbt.enabled is True
    assert model.paths.tools == "tools"
    assert model.extensions == []

    profile = model.profiles["dev"]
    assert profile.duckdb.path == str(tmp_path / "data" / "db-dev.duckdb")
    assert profile.drift.path == str(tmp_path / "drift" / "drift-dev.json")
    assert profile.audit.path == str(tmp_path / "audit" / "logs-dev.jsonl")
    assert profile.audit.enabled is False


def test_duckdb_path_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MXCP_DUCKDB_PATH", "/tmp/custom.duckdb")
    model = SiteConfigModel.model_validate(_base_config(), context={"repo_root": tmp_path})
    assert model.profiles["dev"].duckdb.path == "/tmp/custom.duckdb"
    monkeypatch.delenv("MXCP_DUCKDB_PATH")


@pytest.mark.parametrize("env_value,expected", [("true", True), ("false", False)])
def test_audit_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env_value: str, expected: bool
):
    monkeypatch.setenv("MXCP_AUDIT_ENABLED", env_value)
    model = SiteConfigModel.model_validate(_base_config(), context={"repo_root": tmp_path})
    assert model.profiles["dev"].audit.enabled is expected
    monkeypatch.delenv("MXCP_AUDIT_ENABLED")


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
    with pytest.raises(ValidationError):
        SiteConfigModel.model_validate(cfg, context={"repo_root": tmp_path})


def test_sql_tools_rejects_empty_description(tmp_path: Path):
    """description must be non-empty when provided."""
    cfg = {
        **_base_config(),
        "sql_tools": {
            "enabled": True,
            "execute_sql_query": {"description": ""},
        },
    }
    with pytest.raises(ValidationError):
        SiteConfigModel.model_validate(cfg, context={"repo_root": tmp_path})
