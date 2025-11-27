import os
from pathlib import Path

import pytest

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
