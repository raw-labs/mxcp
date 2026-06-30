import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from mxcp.server.executor.engine import DUCKDB_INSTALL_HINT


@contextmanager
def block_duckdb_imports() -> Iterator[None]:
    """Temporarily simulate an environment without DuckDB installed."""

    prefixes = ("duckdb", "mxcp.sdk.duckdb", "mxcp.sdk.executor.plugins.duckdb")
    saved_modules = {
        name: module
        for name, module in list(sys.modules.items())
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)
    }
    for name in saved_modules:
        sys.modules.pop(name, None)

    class Blocker:
        def find_spec(
            self,
            fullname: str,
            path: Any | None = None,
            target: Any | None = None,
        ) -> None:
            if any(fullname == prefix or fullname.startswith(f"{prefix}.") for prefix in prefixes):
                raise ImportError(f"blocked optional dependency: {fullname}")
            return None

    blocker = Blocker()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)
        for name in list(sys.modules):
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes):
                sys.modules.pop(name, None)
        sys.modules.update(saved_modules)


def write_python_only_project(project_dir: Path) -> None:
    (project_dir / "tools").mkdir()
    (project_dir / "python").mkdir()
    (project_dir / "mxcp-site.yml").write_text(
        """
mxcp: 1
project: optional-duckdb
profile: test
paths:
  tools: tools
  python: python
profiles:
  test: {}
""",
        encoding="utf-8",
    )
    (project_dir / "mxcp-config.yml").write_text(
        """
mxcp: 1
projects:
  optional-duckdb:
    profiles:
      test:
        plugin:
          config: {}
""",
        encoding="utf-8",
    )
    (project_dir / "python" / "tools.py").write_text(
        """
def hello(name: str) -> dict:
    return {"message": f"hello {name}"}

def database_access() -> None:
    from mxcp.runtime import db

    db.execute("select 1")
""",
        encoding="utf-8",
    )
    (project_dir / "tools" / "hello.yml").write_text(
        """
mxcp: 1
tool:
  name: hello
  language: python
  source:
    file: ../python/tools.py
  parameters:
    - name: name
      type: string
  return:
    type: object
""",
        encoding="utf-8",
    )
    (project_dir / "tools" / "database_access.yml").write_text(
        """
mxcp: 1
tool:
  name: database_access
  language: python
  source:
    file: ../python/tools.py
  return:
    type: object
""",
        encoding="utf-8",
    )


def test_server_mcp_import_does_not_import_duckdb() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    code = """
import builtins
import sys

orig_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "duckdb" or name.startswith("duckdb."):
        raise AssertionError(f"duckdb import attempted by {name}")
    return orig_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import mxcp.server.interfaces.server.mcp  # noqa: F401
assert "duckdb" not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], check=True, env=env)


def test_top_level_cli_import_does_not_import_duckdb() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    code = """
import builtins
import sys

orig_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "duckdb" or name.startswith("duckdb."):
        raise AssertionError(f"duckdb import attempted by {name}")
    return orig_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import mxcp.__main__  # noqa: F401
assert "duckdb" not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], check=True, env=env)


@pytest.mark.asyncio
async def test_python_only_server_starts_and_executes_without_duckdb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_python_only_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MXCP_CONFIG", str(tmp_path / "mxcp-config.yml"))

    with block_duckdb_imports():
        from mxcp.server.interfaces.server.mcp import RAWMCP

        server = RAWMCP(site_config_path=tmp_path)
        try:
            assert server.runtime_environment is not None
            assert server.runtime_environment.duckdb_runtime is None
            assert "duckdb" not in sys.modules

            result = await server._execute(
                endpoint_type="tool",
                name="hello",
                params={"name": "world"},
            )
            assert result == {"message": "hello world"}
            assert "duckdb" not in sys.modules
        finally:
            await server.shutdown()


@pytest.mark.asyncio
async def test_python_endpoint_db_execute_reports_missing_duckdb_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_python_only_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MXCP_CONFIG", str(tmp_path / "mxcp-config.yml"))

    with block_duckdb_imports():
        from mxcp.server.interfaces.server.mcp import RAWMCP

        server = RAWMCP(site_config_path=tmp_path)
        try:
            with pytest.raises(RuntimeError, match="DuckDB runtime is not available"):
                await server._execute(
                    endpoint_type="tool",
                    name="database_access",
                    params={},
                )
        finally:
            await server.shutdown()


def test_sql_endpoint_requires_duckdb_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_python_only_project(tmp_path)
    (tmp_path / "tools" / "sql_tool.yml").write_text(
        """
mxcp: 1
tool:
  name: sql_tool
  source:
    code: SELECT 1 AS value
  return:
    type: array
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MXCP_CONFIG", str(tmp_path / "mxcp-config.yml"))

    with block_duckdb_imports():
        from mxcp.server.interfaces.server.mcp import RAWMCP

        with pytest.raises(RuntimeError, match=r"mxcp\[duckdb\]") as exc_info:
            RAWMCP(site_config_path=tmp_path)

    assert DUCKDB_INSTALL_HINT in str(exc_info.value)


def test_enabled_sql_tools_require_duckdb_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_python_only_project(tmp_path)
    site_path = tmp_path / "mxcp-site.yml"
    site_path.write_text(
        site_path.read_text(encoding="utf-8") + "\nsql_tools:\n  enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MXCP_CONFIG", str(tmp_path / "mxcp-config.yml"))

    with block_duckdb_imports():
        from mxcp.server.interfaces.server.mcp import RAWMCP

        with pytest.raises(RuntimeError, match=r"mxcp\[duckdb\]") as exc_info:
            RAWMCP(site_config_path=tmp_path)

    assert DUCKDB_INSTALL_HINT in str(exc_info.value)
