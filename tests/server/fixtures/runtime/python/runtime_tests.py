"""
Runtime test implementations.

This module contains functions that test various aspects of the mxcp.runtime module.
"""

import os

from mxcp.runtime import config, db, on_init, on_shutdown, plugins

# Global variable to track lifecycle hooks
_init_called = False
_init_value = None


@on_init
def initialize_test():
    """Test init hook."""
    global _init_called, _init_value
    _init_called = True
    _init_value = "initialized"
    # Create a test file to verify init was called
    with open("/tmp/mxcp_runtime_test_init.txt", "w") as f:
        f.write("init hook called")


@on_shutdown
def cleanup_test():
    """Test shutdown hook."""
    # Clean up the test file
    if os.path.exists("/tmp/mxcp_runtime_test_init.txt"):
        os.remove("/tmp/mxcp_runtime_test_init.txt")


def test_db_execute() -> dict:
    """Test db.execute() functionality."""
    # Test basic query
    result1 = db.execute("SELECT 42 as answer, 'hello' as greeting")

    # Test parameterized query
    result2 = db.execute("SELECT $name as name, $age as age", {"name": "Alice", "age": 30})

    # Test querying secrets table
    secrets_result = db.execute("SELECT name, type FROM duckdb_secrets() ORDER BY name")

    # Test accessing raw connection
    try:
        conn = db.connection
        conn_exists = conn is not None
    except Exception as e:
        conn_exists = False

    return {
        "basic_query_result": result1,
        "param_query_result": result2,
        "secrets_count": len(secrets_result),
        "secret_names": [s["name"] for s in secrets_result],
        "connection_available": conn_exists,
    }


def test_get_secret():
    """Test getting a secret value."""
    from mxcp.runtime import config

    # Test getting a simple value secret
    simple_params = config.get_secret("simple_secret")
    assert simple_params is not None
    assert isinstance(simple_params, dict)
    assert simple_params.get("value") == "test-secret-value-123"

    # Test getting an HTTP secret with complex structure
    http_params = config.get_secret("http_secret")
    assert http_params is not None
    assert isinstance(http_params, dict)
    assert http_params.get("BEARER_TOKEN") == "bearer-token-456"
    assert "EXTRA_HTTP_HEADERS" in http_params
    headers = http_params["EXTRA_HTTP_HEADERS"]
    assert headers["X-API-Key"] == "api-key-789"
    assert headers["X-Custom-Header"] == "custom-value"

    # Test getting a non-existent secret
    missing = config.get_secret("non_existent")
    assert missing is None

    # Test S3 secret parameters
    s3_params = config.get_secret("s3_secret")
    assert s3_params is not None
    assert s3_params.get("ACCESS_KEY_ID") == "AKIAIOSFODNN7EXAMPLE"
    assert s3_params.get("SECRET_ACCESS_KEY") == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    assert s3_params.get("REGION") == "us-east-1"

    return {
        "test": "get_secret",
        "status": "passed",
        "simple_secret_value": simple_params.get("value") if simple_params else None,
        "http_secret_has_headers": bool(http_params and "EXTRA_HTTP_HEADERS" in http_params),
        "s3_secret_has_region": bool(s3_params and "REGION" in s3_params),
    }


def test_get_setting() -> dict:
    """Test config.get_setting() functionality."""
    # Test getting actual site config settings
    project = config.get_setting("project")
    profile = config.get_setting("profile")
    mxcp_version = config.get_setting("mxcp")
    secrets_list = config.get_setting("secrets")
    extensions = config.get_setting("extensions")

    # Test with default value for missing setting
    missing_setting = config.get_setting("non_existent_setting", "default_value")

    # Test nested access
    dbt_enabled = config.get_setting("dbt", {}).get("enabled", True)

    return {
        "project": project,
        "profile": profile,
        "mxcp_version": mxcp_version,
        "secrets_list": secrets_list,
        "extensions": extensions,
        "missing_setting": missing_setting,
        "dbt_enabled": dbt_enabled,
        "project_correct": project == "runtime_test",
        "profile_correct": profile == "default",
        "secrets_count": len(secrets_list) if secrets_list else 0,
        "missing_uses_default": missing_setting == "default_value",
    }


def test_config_properties() -> dict:
    """Test config.user_config and config.site_config properties."""
    user_cfg = config.user_config
    site_cfg = config.site_config

    # Verify we can access nested values
    try:
        # From user config
        project_name = list(user_cfg["projects"].keys())[0]
        secrets_count = len(user_cfg["projects"]["runtime_test"]["profiles"]["default"]["secrets"])

        # From site config
        site_project = site_cfg["project"]
        site_secrets = site_cfg["secrets"]

        access_works = True
    except Exception as e:
        access_works = False
        project_name = None
        secrets_count = 0
        site_project = None
        site_secrets = []

    return {
        "user_config_exists": user_cfg is not None,
        "site_config_exists": site_cfg is not None,
        "user_config_type": type(user_cfg).__name__,
        "site_config_type": type(site_cfg).__name__,
        "project_name": project_name,
        "secrets_count": secrets_count,
        "site_project": site_project,
        "site_secrets_count": len(site_secrets) if site_secrets else 0,
        "access_works": access_works,
    }


def test_plugins() -> dict:
    """Test plugins.get() and plugins.list() functionality."""
    # List all plugins
    plugin_list = plugins.list()

    # Try to get a specific plugin
    test_plugin = plugins.get("test_plugin")
    non_existent = plugins.get("non_existent_plugin")

    # Test accessing plugin methods if available
    plugin_info = None
    if test_plugin:
        try:
            # Plugins should have certain methods/attributes
            plugin_info = {
                "has_name": hasattr(test_plugin, "name"),
                "type": type(test_plugin).__name__,
            }
        except:
            plugin_info = None

    return {
        "plugin_list": plugin_list,
        "plugin_count": len(plugin_list),
        "test_plugin_exists": test_plugin is not None,
        "non_existent_is_none": non_existent is None,
        "plugin_info": plugin_info,
    }


def test_lifecycle_hooks() -> dict:
    """Test that lifecycle hooks were called."""
    global _init_called, _init_value

    # Check if init file was created
    init_file_exists = os.path.exists("/tmp/mxcp_runtime_test_init.txt")

    return {
        "init_called": _init_called,
        "init_value": _init_value,
        "init_file_exists": init_file_exists,
        "lifecycle_works": _init_called and init_file_exists,
    }


def test_error_handling() -> dict:
    """Test error handling in runtime APIs."""
    errors = {}

    # Test db.execute with invalid query
    try:
        db.execute("INVALID SQL QUERY")
        errors["db_invalid_query"] = None
    except Exception as e:
        errors["db_invalid_query"] = str(e)

    # Test with None parameters
    try:
        result = db.execute("SELECT 1", None)
        errors["db_none_params"] = None
    except Exception as e:
        errors["db_none_params"] = str(e)

    # Runtime context should always be available in endpoints
    return {
        "errors": errors,
        "db_error_contains_invalid": "INVALID" in str(errors.get("db_invalid_query", "")),
        "none_params_works": errors.get("db_none_params") is None,
    }
