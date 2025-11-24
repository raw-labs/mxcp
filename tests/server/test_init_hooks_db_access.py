"""
Test that init hooks can access the database with the new architecture.
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from mxcp.server.core.config.models import SiteConfigModel
from mxcp.server.executor.engine import create_runtime_environment
from mxcp.server.services.endpoints import execute_endpoint_with_engine


@pytest.mark.asyncio
async def test_init_hooks_can_access_database():
    """Test that init hooks can now access the database during initialization."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)

        # Create Python module with init hook that uses database
        python_dir = project_dir / "python"
        python_dir.mkdir()

        init_module = python_dir / "init_test.py"
        init_module.write_text(
            """
from mxcp.runtime import on_init, on_shutdown, db

# Global variable to track if init succeeded
init_db_result = None

@on_init
def init_with_db():
    global init_db_result
    try:
        # Try to execute a simple query during init
        result = db.execute("SELECT 'Hello from init!' as message")
        init_db_result = result[0]['message']
        
        # Create a table for later use
        db.execute('''
            CREATE TABLE init_test (
                id INTEGER,
                value TEXT
            )
        ''')
        
        # Insert some data
        db.execute("INSERT INTO init_test VALUES (1, 'initialized')")
        
    except Exception as e:
        init_db_result = f"Error: {str(e)}"

@on_shutdown 
def cleanup():
    try:
        db.execute("DROP TABLE IF EXISTS init_test")
    except:
        pass

def check_init_result():
    '''Tool to check if init hook succeeded.'''
    return {
        "init_result": init_db_result,
        "table_exists": False
    }

def check_table_data():
    '''Check if table created in init hook persists.'''
    try:
        result = db.execute("SELECT * FROM init_test")
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
"""
        )

        # Create tool definitions
        tools_dir = project_dir / "tools"
        tools_dir.mkdir()

        check_tool = tools_dir / "check_init.yml"
        check_tool.write_text(
            """
mxcp: 1
tool:
  name: check_init_result
  description: Check if init hook succeeded
  language: python
  source:
    file: ../python/init_test.py
  return:
    type: object
"""
        )

        table_tool = tools_dir / "check_table.yml"
        table_tool.write_text(
            """
mxcp: 1
tool:
  name: check_table_data
  description: Check table created in init hook
  language: python
  source:
    file: ../python/init_test.py
  return:
    type: object
"""
        )

        # Create site config
        site_config_data = {
            "mxcp": 1,
            "project": "init-test",
            "profile": "test",
            "profiles": {
                "test": {"duckdb": {"path": str(project_dir / "test.duckdb"), "readonly": False}}
            },
            "paths": {"tools": "tools", "python": "python"},
        }

        with open(project_dir / "mxcp-site.yml", "w") as f:
            yaml.dump(site_config_data, f)

        # Create user config
        user_config = {
            "mxcp": 1,
            "projects": {
                "init-test": {
                    "profiles": {
                        "test": {
                            "secrets": [],
                            "auth": {"provider": "none"},
                            "plugin": {"config": {}},
                        }
                    }
                }
            },
        }

        # Change to project directory
        original_dir = os.getcwd()
        os.chdir(project_dir)

        try:
            # Create runtime environment - this will run init hooks
            site_config = SiteConfigModel.model_validate(
                site_config_data, context={"repo_root": project_dir}
            )

            runtime_env = create_runtime_environment(
                user_config, site_config, repo_root=project_dir
            )

            # Check if init hook succeeded
            result = await execute_endpoint_with_engine(
                endpoint_type="tool",
                name="check_init_result",
                params={},
                user_config=user_config,
                site_config=site_config,
                execution_engine=runtime_env.execution_engine,
            )

            # Init should have succeeded with new architecture
            assert (
                result["init_result"] == "Hello from init!"
            ), f"Init hook failed: {result['init_result']}"

            # Check if table persists
            table_result = await execute_endpoint_with_engine(
                endpoint_type="tool",
                name="check_table_data",
                params={},
                user_config=user_config,
                site_config=site_config,
                execution_engine=runtime_env.execution_engine,
            )

            assert table_result["success"], f"Table check failed: {table_result.get('error')}"
            assert len(table_result["data"]) == 1
            assert table_result["data"][0]["id"] == 1
            assert table_result["data"][0]["value"] == "initialized"

            # Clean up
            runtime_env.shutdown()

        finally:
            os.chdir(original_dir)


@pytest.mark.asyncio
async def test_memory_database_forbidden():
    """Test that :memory: databases are now forbidden."""
    from mxcp.sdk.duckdb import DuckDBRuntime, DatabaseConfig, PluginConfig

    # Should raise ValueError for :memory: database
    with pytest.raises(ValueError, match="In-memory databases.*not supported"):
        runtime = DuckDBRuntime(
            database_config=DatabaseConfig(path=":memory:", readonly=False, extensions=[]),
            plugins=[],
            plugin_config=PluginConfig(plugins_path="plugins", config={}),
            secrets=[],
        )
