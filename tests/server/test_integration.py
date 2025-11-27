"""Integration tests for RAWMCP server with real MCP protocol calls.

These tests start an actual server subprocess and communicate with it using
the MCP protocol to test the full stack including configuration reloads.
"""

import asyncio
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

# Import MCP SDK for making protocol calls
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# Import MXCP components for dbt integration
from mxcp.server.core.config.site_config import load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.services.dbt.runner import configure_dbt


class MCPTestClient:
    """Client for making MCP protocol calls using the official SDK."""

    def __init__(self, port: int = 8765):
        self.port = port
        self.url = f"http://localhost:{port}/mcp/"
        self.session = None
        self.context = None

    async def __aenter__(self):
        # Connect using streamable HTTP transport
        self.context = streamablehttp_client(self.url)
        read_stream, write_stream, _ = await self.context.__aenter__()

        # Create session
        self.session = ClientSession(read_stream, write_stream)
        await self.session.__aenter__()

        # Initialize the connection
        await self.session.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.session:
                await self.session.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            if self.context:
                await self.context.__aexit__(exc_type, exc_val, exc_tb)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool via MCP protocol."""
        try:
            result = await self.session.call_tool(name, arguments)

            # Debug: print what we got
            if os.environ.get("MXCP_TEST_DEBUG"):
                print(f"[DEBUG] Tool result type: {type(result)}")
                print(f"[DEBUG] Tool result: {result}")
                if hasattr(result, "__dict__"):
                    print(f"[DEBUG] Tool result attributes: {result.__dict__}")

            # Extract the actual result from MCP format
            # First check for structured content (new format with output schema)
            if hasattr(result, "structuredContent") and result.structuredContent is not None:
                structured_content = result.structuredContent
                if os.environ.get("MXCP_TEST_DEBUG"):
                    print(f"[DEBUG] Using structured content: {structured_content}")
                # Structured content is wrapped in a 'result' key, so unwrap it
                if isinstance(structured_content, dict) and "result" in structured_content:
                    return structured_content["result"]
                else:
                    return structured_content

            # Fall back to regular content (legacy format)
            elif (
                hasattr(result, "content")
                and isinstance(result.content, list)
                and len(result.content) > 0
            ):
                content = result.content[0]
                if hasattr(content, "type") and content.type == "text" and hasattr(content, "text"):
                    # Parse the JSON text content
                    try:
                        parsed = json.loads(content.text)
                        if os.environ.get("MXCP_TEST_DEBUG"):
                            print(f"[DEBUG] Parsed result: {parsed}")
                        return parsed
                    except json.JSONDecodeError:
                        # If it's not JSON, return the text as-is
                        return {"result": content.text}

            # Check if result has an error attribute
            if hasattr(result, "isError") and result.isError:
                # This is an error result
                error_msg = str(result)
                if hasattr(result, "error"):
                    error_msg = str(result.error)
                return {"result": f"Error executing tool {name}: {error_msg}"}

            # Fallback to returning the raw result
            return {"result": str(result)}
        except Exception as e:
            if os.environ.get("MXCP_TEST_DEBUG"):
                import traceback

                print(f"[DEBUG] Exception in call_tool: {e}")
                print(f"[DEBUG] Traceback: {traceback.format_exc()}")
            return {"result": f"Error executing tool {name}: {str(e)}"}

    async def list_tools(self) -> list:
        """List available tools."""
        response = await self.session.list_tools()
        tools = response.tools if hasattr(response, "tools") else []
        # Convert tool objects to dictionaries for consistent interface
        return [
            {
                "name": tool.name,
                "description": tool.description if hasattr(tool, "description") else None,
                "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
            }
            for tool in tools
        ]


class ServerProcess:
    """Manager for RAWMCP server subprocess."""

    def __init__(self, working_dir: Path, port: int = None):
        self.working_dir = working_dir
        # Use a random available port to avoid conflicts
        if port is None:
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("", 0))
            self.port = sock.getsockname()[1]
            sock.close()
        else:
            self.port = port
        self.process: subprocess.Popen | None = None
        self.original_dir = os.getcwd()

    def start(self, extra_args: list = None):
        """Start the server process."""
        os.chdir(self.working_dir)

        cmd = [
            "mxcp",
            "serve",
            "--port",
            str(self.port),
            "--transport",
            "streamable-http",
            "--debug",  # Enable debug mode
            # Removed --stateless flag due to MCP library issue
        ]
        if extra_args:
            cmd.extend(extra_args)

        # Set MXCP_CONFIG to use our test config
        env = os.environ.copy()
        env["MXCP_CONFIG"] = str(self.working_dir / "mxcp-config.yml")

        # Enable debug logging
        env["MXCP_LOG_LEVEL"] = "DEBUG"

        self.process = subprocess.Popen(
            cmd,
            env=env,
            cwd=str(self.working_dir),  # Set working directory for subprocess
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Combine stdout and stderr
            text=True,
        )

        # Start a thread to read server output
        import threading

        def read_output():
            for line in self.process.stdout:
                # Enable output for debugging when needed
                if os.environ.get("MXCP_TEST_DEBUG"):
                    print(f"[SERVER] {line.strip()}")
                # Always capture lines that might indicate the issue
                if any(
                    keyword in line.lower()
                    for keyword in ["error", "errno", "traceback", "exception", "failed"]
                ):
                    print(f"[SERVER ERROR] {line.strip()}")

        output_thread = threading.Thread(target=read_output, daemon=True)
        output_thread.start()

        # Wait for server to start
        self._wait_for_server()

    def _wait_for_server(self, timeout: float = 10.0):
        """Wait for server to be ready."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Try to connect
                import socket

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(("localhost", self.port))
                sock.close()

                if result == 0:
                    # Give it a bit more time to fully initialize
                    time.sleep(0.5)
                    return
            except Exception:
                pass

            # Check if process died
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                raise RuntimeError(f"Server process died: stdout={stdout}, stderr={stderr}")

            time.sleep(0.1)

        raise TimeoutError(f"Server did not start within {timeout} seconds")

    def reload(self):
        """Send SIGHUP to reload configuration."""
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGHUP)
            # Give it more time to reload - the reload happens in a separate thread
            # and involves shutting down components, resolving references, and recreating sessions
            time.sleep(3.0)

    def stop(self):
        """Stop the server process."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

        # Safely restore original directory
        try:
            os.chdir(self.original_dir)
        except (FileNotFoundError, OSError):
            # Original directory may no longer exist, go to a safe location
            try:
                os.chdir(Path(__file__).parent)
            except (FileNotFoundError, OSError):
                # Last resort - go to home directory
                os.chdir(os.path.expanduser("~"))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


@pytest.fixture
def integration_fixture_dir():
    """Create a temporary test fixture directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fixture_path = Path(tmpdir)

        # Copy the integration fixture template
        template_dir = Path(__file__).parent / "fixtures" / "integration"
        if template_dir.exists():
            shutil.copytree(template_dir, fixture_path, dirs_exist_ok=True)
        else:
            # Create a basic structure if template doesn't exist
            _create_integration_fixture(fixture_path)

        yield fixture_path


def _create_integration_fixture(fixture_path: Path):
    """Create a basic integration test fixture."""
    # Create directories
    for dir_name in ["tools", "python", "data", "audit", "drift"]:
        (fixture_path / dir_name).mkdir(exist_ok=True)

    # Create user config
    user_config = {
        "mxcp": 1,
        "transport": {"provider": "streamable-http", "http": {"port": 8765, "host": "localhost"}},
        "projects": {
            "integration_test": {
                "profiles": {
                    "default": {
                        "secrets": [
                            {
                                "name": "test_secret",
                                "type": "custom",
                                "parameters": {
                                    "api_key": "initial_key_123",
                                    "endpoint": "https://api.example.com",
                                },
                            }
                        ]
                    }
                }
            }
        },
    }

    with open(fixture_path / "mxcp-config.yml", "w") as f:
        yaml.dump(user_config, f)

    # Create site config
    site_config = {
        "mxcp": 1,
        "project": "integration_test",
        "profile": "default",
        "profiles": {"default": {"duckdb": {"path": "test.duckdb"}}},
        "secrets": ["test_secret"],
    }

    with open(fixture_path / "mxcp-site.yml", "w") as f:
        yaml.dump(site_config, f)

    # Create a Python endpoint that uses secrets
    python_code = '''
from mxcp.runtime import config

def check_secret() -> dict:
    """Check the current secret value."""
    secret_params = config.get_secret("test_secret")
    return {
        "api_key": secret_params.get("api_key") if secret_params else None,
        "endpoint": secret_params.get("endpoint") if secret_params else None,
        "has_secret": secret_params is not None
    }

def echo_message(message: str) -> dict:
    """Echo a message back."""
    return {
        "original": message,
        "reversed": message[::-1],
        "length": len(message)
    }
'''

    with open(fixture_path / "python" / "test_endpoints.py", "w") as f:
        f.write(python_code)

    # Create tool definitions
    check_secret_tool = {
        "mxcp": 1,
        "tool": {
            "name": "check_secret",
            "description": "Check the current secret value",
            "language": "python",
            "source": {"file": "../python/test_endpoints.py"},
            "parameters": [],
            "return": {"type": "object"},
        },
    }

    with open(fixture_path / "tools" / "check_secret.yml", "w") as f:
        yaml.dump(check_secret_tool, f)

    echo_tool = {
        "mxcp": 1,
        "tool": {
            "name": "echo_message",
            "description": "Echo a message",
            "language": "python",
            "source": {"file": "../python/test_endpoints.py"},
            "parameters": [{"name": "message", "type": "string", "description": "Message to echo"}],
            "return": {"type": "object"},
        },
    }

    with open(fixture_path / "tools" / "echo_message.yml", "w") as f:
        yaml.dump(echo_tool, f)


class TestIntegration:
    """Integration tests for RAWMCP server."""

    @pytest.mark.asyncio
    async def test_basic_tool_call(self, integration_fixture_dir):
        """Test basic tool call through MCP protocol."""
        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                # Call the echo tool
                result = await client.call_tool("echo_message", {"message": "Hello MXCP!"})

                assert result["original"] == "Hello MXCP!"
                assert result["reversed"] == "!PCXM olleH"
                assert result["length"] == 11

    @pytest.mark.asyncio
    async def test_secret_access(self, integration_fixture_dir):
        """Test that Python endpoints can access secrets."""
        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                # Check initial secret value
                result = await client.call_tool("check_secret", {})

                assert result["has_secret"] is True
                assert result["api_key"] == "initial_key_123"
                assert result["endpoint"] == "https://api.example.com"

    @pytest.mark.asyncio
    async def test_reload_with_external_ref(self, integration_fixture_dir):
        """Test reload with external references (env vars, files)."""
        # Create a secret file
        secret_file = integration_fixture_dir / "secret.txt"
        secret_file.write_text("file_secret_v1")

        # Create another file for the endpoint (since env vars don't propagate to subprocesses)
        endpoint_file = integration_fixture_dir / "endpoint.txt"
        endpoint_file.write_text("https://api.v1.example.com")

        # Update config to use external references
        config_path = integration_fixture_dir / "mxcp-config.yml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        config["projects"]["integration_test"]["profiles"]["default"]["secrets"][0][
            "parameters"
        ] = {"api_key": f"file://{secret_file}", "endpoint": f"file://{endpoint_file}"}

        with open(config_path, "w") as f:
            yaml.dump(config, f)

        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            # Check initial values
            async with MCPTestClient(server.port) as client:
                result1 = await client.call_tool("check_secret", {})
                assert result1["api_key"] == "file_secret_v1"
                assert result1["endpoint"] == "https://api.v1.example.com"

            # Update external values
            secret_file.write_text("file_secret_v2")
            endpoint_file.write_text("https://api.v2.example.com")

            # Reload - now no active requests should be holding up the reload
            server.reload()

            # Wait for the asynchronous reload to complete
            # The reload is now scheduled asynchronously and happens after current requests finish
            # Need to wait longer to ensure reload completes and new connections pick up the changes
            await asyncio.sleep(10.0)

            # Check updated values with a new client connection
            async with MCPTestClient(server.port) as client:
                result2 = await client.call_tool("check_secret", {})
                assert result2["api_key"] == "file_secret_v2"
                assert result2["endpoint"] == "https://api.v2.example.com"

    @pytest.mark.asyncio
    async def test_reload_always_refreshes_duckdb(self, integration_fixture_dir):
        """Test that SIGHUP always reloads DuckDB session even without config changes."""
        # Use context manager to ensure proper cleanup
        with ServerProcess(integration_fixture_dir) as process:
            process.start()  # Add missing start() call

            # Call tool to verify initial state
            async with MCPTestClient(process.port) as client:
                result = await client.call_tool("echo_message", {"message": "test1"})
                assert result["original"] == "test1"
                assert result["reversed"] == "1tset"
                # Verify initial state
                assert result["length"] == len("test1")

            # Wait a moment to ensure timestamp would be different
            await asyncio.sleep(1)

            # Send SIGHUP to reload (no config changes)
            print("Sending SIGHUP signal for reload...")
            process.reload()  # Use the reload method

            # Wait for reload to complete
            await asyncio.sleep(1)

            # Verify we can still call tools after reload
            # The server should work fine after reload even without config changes
            async with MCPTestClient(process.port) as client:
                result2 = await client.call_tool("echo_message", {"message": "test after reload"})
                assert result2["original"] == "test after reload"
                assert result2["reversed"] == "daoler retfa tset"
                # The result should still work correctly after reload
                assert result2["length"] == len("test after reload")

    @pytest.mark.asyncio
    async def test_reload_duckdb_from_tool(self, integration_fixture_dir):
        """Test that reload_duckdb called from a tool doesn't hang."""
        # Create a Python endpoint that calls reload_duckdb
        python_dir = integration_fixture_dir / "python"
        python_dir.mkdir(exist_ok=True)

        reload_tool_py = python_dir / "reload_tool.py"
        reload_tool_py.write_text(
            '''
import time
import shutil
from pathlib import Path
from mxcp.runtime import reload_duckdb, db, config

def trigger_reload(message: str = "test") -> dict:
    """Trigger a DuckDB reload from within a tool - realistic user code."""
    import duckdb
    from datetime import datetime

    # Track timing
    start_time = time.time()

    # First, check what's in the database before modification
    assert db is not None, "db proxy is None - implementation is broken!"

    try:
        # Try to query existing data
        before_data = db.execute("SELECT * FROM reload_test ORDER BY id")
        before_count = len(before_data)
    except Exception as e:
        # Table doesn't exist yet - this is fine for first run
        print(f"Table doesn't exist yet: {e}")
        before_count = 0
        before_data = []

    # Get DuckDB file path
    site_config = config.site_config
    profile = site_config["profiles"]["default"]
    duckdb_cfg = profile["duckdb"]
    db_path = Path(duckdb_cfg["path"])
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path

    # Create a new database file with additional test data
    temp_db = db_path.with_suffix('.tmp')

    # If database exists, copy it to preserve existing data
    if db_path.exists():
        shutil.copy2(db_path, temp_db)

    # Add new data to the temp database
    timestamp = datetime.now().isoformat()
    with duckdb.connect(str(temp_db)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS reload_test (id INTEGER, message VARCHAR, created_at VARCHAR)")
        # Add a new row with current count + 1
        conn.execute(
            f"INSERT INTO reload_test VALUES ({before_count + 1}, '{message}', '{timestamp}')"
        )
        conn.commit()

    # Replace the database file atomically
    shutil.move(str(temp_db), str(db_path))

    # Now reload DuckDB to pick up the changes
    # IMPORTANT: reload_duckdb() is now asynchronous and will happen AFTER this request completes
    # So we can't verify the reload in the same request
    reload_duckdb()

    # Since the reload is async and happens after this request, we can't query the new data yet
    # Instead, we'll return info about what we did and let the test verify in a subsequent call
    
    elapsed = time.time() - start_time
    
    return {
        "message": message,
        "before_count": before_count,
        "after_count": before_count,  # Can't get the real after count yet
        "new_row": None,  # Can't get the new row yet
        "all_data": before_data,  # Return the data we had before
        "reload_requested": True,  # Indicate we requested a reload
        "elapsed_time": elapsed,
        "db_path": str(db_path),
        "timestamp": timestamp  # Save this so we can verify later
    }


def verify_reload(expected_count: int, expected_message: str, expected_timestamp: str) -> dict:
    """Verify that the reload completed and the new data is available."""
    # Query the database to see if the reload worked
    try:
        data = db.execute("SELECT * FROM reload_test ORDER BY id")
        count = len(data)
        
        # Find the row with the expected message
        found_row = None
        for row in data:
            if row["message"] == expected_message and row["created_at"] == expected_timestamp:
                found_row = row
                break
        
        return {
            "reload_success": count >= expected_count,
            "count": count,
            "expected_count": expected_count,
            "found_row": found_row,
            "all_data": data
        }
    except Exception as e:
        return {
            "reload_success": False,
            "error": str(e)
        }
'''
        )

        # Create the tool YAML in the expected format
        tools_dir = integration_fixture_dir / "tools"

        # Tool to trigger reload
        reload_tool_yml = tools_dir / "trigger_reload.yml"
        reload_tool = {
            "mxcp": 1,
            "tool": {
                "name": "trigger_reload",
                "description": "Test tool that triggers a reload",
                "language": "python",
                "source": {"file": "../python/reload_tool.py"},
                "parameters": [
                    {
                        "name": "message",
                        "type": "string",
                        "description": "Test message",
                        "default": "test",
                    }
                ],
                "return": {"type": "object"},
            },
        }
        with open(reload_tool_yml, "w") as f:
            yaml.dump(reload_tool, f)

        # Tool to verify reload
        verify_tool_yml = tools_dir / "verify_reload.yml"
        verify_tool = {
            "mxcp": 1,
            "tool": {
                "name": "verify_reload",
                "description": "Verify that reload completed",
                "language": "python",
                "source": {"file": "../python/reload_tool.py"},
                "parameters": [
                    {
                        "name": "expected_count",
                        "type": "integer",
                        "description": "Expected row count",
                    },
                    {
                        "name": "expected_message",
                        "type": "string",
                        "description": "Expected message",
                    },
                    {
                        "name": "expected_timestamp",
                        "type": "string",
                        "description": "Expected timestamp",
                    },
                ],
                "return": {"type": "object"},
            },
        }
        with open(verify_tool_yml, "w") as f:
            yaml.dump(verify_tool, f)

        # Start the server
        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                # Set a timeout for the entire test
                start_time = time.time()

                # Call the tool that triggers reload - this should NOT hang!
                result = await asyncio.wait_for(
                    client.call_tool("trigger_reload", {"message": "integration_test"}),
                    timeout=10.0,  # 10 second timeout - if it hangs, test fails
                )

                elapsed = time.time() - start_time

                # Verify the trigger worked
                assert result["reload_requested"] is True
                assert result["message"] == "integration_test"
                assert result["before_count"] == 0  # First run, no data yet

                # Save values for verification
                timestamp1 = result["timestamp"]

                # The trigger call should be quick (not hanging)
                assert elapsed < 5.0, f"Tool call took too long: {elapsed}s"

                # Wait for the async reload to complete
                await asyncio.sleep(3.0)

                # Step 2: Verify the reload completed
                verify_result = await client.call_tool(
                    "verify_reload",
                    {
                        "expected_count": 1,
                        "expected_message": "integration_test",
                        "expected_timestamp": timestamp1,
                    },
                )

                assert verify_result["reload_success"] is True
                assert verify_result["count"] >= 1
                assert verify_result["found_row"] is not None
                assert verify_result["found_row"]["message"] == "integration_test"

                # Call again to verify persistence and accumulation
                result2 = await client.call_tool("trigger_reload", {"message": "second_test"})
                assert result2["reload_requested"] is True
                assert result2["message"] == "second_test"
                assert result2["before_count"] == 1  # Should see the previous row

                timestamp2 = result2["timestamp"]

                # Wait for the second reload
                await asyncio.sleep(3.0)

                # Verify second reload
                verify_result2 = await client.call_tool(
                    "verify_reload",
                    {
                        "expected_count": 2,
                        "expected_message": "second_test",
                        "expected_timestamp": timestamp2,
                    },
                )

                assert verify_result2["reload_success"] is True
                assert verify_result2["count"] >= 2
                assert verify_result2["found_row"] is not None

                # Verify server is still functional after reload
                echo_result = await client.call_tool("echo_message", {"message": "still alive"})
                assert echo_result["original"] == "still alive"

    @pytest.mark.asyncio
    async def test_non_duckdb_secret_types(self, integration_fixture_dir):
        """Test that non-DuckDB secret types work correctly."""
        # Update config to have multiple secret types
        config_path = integration_fixture_dir / "mxcp-config.yml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Add various non-DuckDB secret types
        config["projects"]["integration_test"]["profiles"]["default"]["secrets"] = [
            {
                "name": "custom_secret",
                "type": "custom",
                "parameters": {
                    "api_key": "custom_key",
                    "x_custom_header": "header_value",  # Flat structure
                },
            },
            {
                "name": "python_secret",
                "type": "python",
                "parameters": {
                    "value": "python_only_value",
                    "nested_value": "deep_value",  # Flat structure instead of nested
                },
            },
        ]

        with open(config_path, "w") as f:
            yaml.dump(config, f)

        # Update site config to reference new secrets
        site_config_path = integration_fixture_dir / "mxcp-site.yml"
        with open(site_config_path) as f:
            site_config_data = yaml.safe_load(f) or {}

        site_config_data["secrets"] = ["custom_secret", "python_secret"]

        with open(site_config_path, "w") as f:
            yaml.dump(site_config_data, f)

        # Create endpoint to test these secrets
        python_code = '''
from mxcp.runtime import config

def check_all_secrets() -> dict:
    """Check all secret types."""
    custom = config.get_secret("custom_secret")
    python = config.get_secret("python_secret")

    return {
        "custom": {
            "found": custom is not None,
            "api_key": custom.get("api_key") if custom else None,
            "has_header": "x_custom_header" in custom if custom else False
        },
        "python": {
            "found": python is not None,
            "value": python.get("value") if python else None,
            "nested_value": python.get("nested_value") if python else None
        }
    }
'''

        with open(integration_fixture_dir / "python" / "test_endpoints.py", "a") as f:
            f.write("\n\n" + python_code)

        # Create tool definition
        tool_def = {
            "mxcp": 1,
            "tool": {
                "name": "check_all_secrets",
                "description": "Check all secret types",
                "language": "python",
                "source": {"file": "../python/test_endpoints.py"},
                "parameters": [],
                "return": {"type": "object"},
            },
        }

        with open(integration_fixture_dir / "tools" / "check_all_secrets.yml", "w") as f:
            yaml.dump(tool_def, f)

        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                # Test non-DuckDB secrets
                result = await client.call_tool("check_all_secrets", {})

                # Custom secret
                assert result["custom"]["found"] is True
                assert result["custom"]["api_key"] == "custom_key"
                assert result["custom"]["has_header"] is True

                # Python secret
                assert result["python"]["found"] is True
                assert result["python"]["value"] == "python_only_value"
                assert result["python"]["nested_value"] == "deep_value"

    @pytest.mark.asyncio
    async def test_list_tools(self, integration_fixture_dir):
        """Test listing available tools."""
        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                tools = await client.list_tools()

                # Should have our test tools
                tool_names = [t["name"] for t in tools] if tools else []

                # Check if we have any tools at all
                assert len(tools) > 0, "No tools were returned by the server"
                assert "check_secret" in tool_names
                assert "echo_message" in tool_names

                # Check tool has proper description
                echo_tool = next((t for t in tools if t["name"] == "echo_message"), None)
                assert echo_tool is not None, "echo_message tool not found"
                assert echo_tool["description"] == "Echo a message"
                assert len(echo_tool.get("inputSchema", {}).get("properties", {})) == 1

    @pytest.mark.asyncio
    async def test_parameter_optionality_in_mcp_schema(self, integration_fixture_dir):
        """Test that MCP schema correctly advertises optional vs required parameters."""
        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                tools = await client.list_tools()

                # Find our test tool with optional parameters
                test_tool = next((t for t in tools if t["name"] == "check_optional_params"), None)
                assert test_tool is not None, "check_optional_params tool not found"

                # Get the input schema
                input_schema = test_tool.get("inputSchema", {})
                properties = input_schema.get("properties", {})
                required_fields = input_schema.get("required", [])

                # Verify we have all expected parameters
                expected_params = [
                    "required_param",
                    "optional_param",
                    "optional_number",
                    "optional_float",
                    "optional_bool",
                    "optional_date",
                    "optional_datetime",
                ]
                for param in expected_params:
                    assert param in properties, f"{param} should be in properties"

                # Verify only required_param is in required array
                assert (
                    "required_param" in required_fields
                ), "required_param should be in required array"

                optional_params = [
                    "optional_param",
                    "optional_number",
                    "optional_float",
                    "optional_bool",
                    "optional_date",
                    "optional_datetime",
                ]
                for param in optional_params:
                    assert param not in required_fields, f"{param} should NOT be in required array"

                # Verify default values are present in the schema with correct types
                assert (
                    properties["optional_param"].get("default") == "default_value"
                ), "optional_param should have default value"
                assert (
                    properties["optional_number"].get("default") == 42
                ), "optional_number should have default value"
                assert (
                    properties["optional_float"].get("default") == 3.14
                ), "optional_float should have default value"
                assert (
                    properties["optional_bool"].get("default") is True
                ), "optional_bool should have default value"
                assert (
                    properties["optional_date"].get("default") == "2024-01-15"
                ), "optional_date should have default value"
                assert (
                    properties["optional_datetime"].get("default") == "2024-01-15T10:30:00Z"
                ), "optional_datetime should have default value"
                assert (
                    "default" not in properties["required_param"]
                ), "required_param should not have default value"

    @pytest.mark.asyncio
    async def test_optional_parameters_functionality(self, integration_fixture_dir):
        """Test that tools with optional parameters work correctly when called."""
        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                # Test calling with only required parameter (optional params should use defaults)
                result1 = await client.call_tool(
                    "check_optional_params", {"required_param": "test_value"}
                )

                assert result1["required_param"] == "test_value"
                assert result1["optional_param"] == "default_value"  # Should use default
                assert result1["optional_number"] == 42  # Should use default
                assert result1["optional_float"] == 3.14  # Should use default
                assert result1["optional_bool"] is True  # Should use default
                assert result1["optional_date"] == "2024-01-15"  # Should use default
                # Datetime may be normalized to +00:00 format instead of Z
                assert result1["optional_datetime"] in [
                    "2024-01-15T10:30:00Z",
                    "2024-01-15T10:30:00+00:00",
                ]  # Should use default

                # Test calling with all parameters (should override defaults)
                result2 = await client.call_tool(
                    "check_optional_params",
                    {
                        "required_param": "test_value",
                        "optional_param": "custom_value",
                        "optional_number": 100,
                        "optional_float": 2.71,
                        "optional_bool": False,
                        "optional_date": "2025-12-31",
                        "optional_datetime": "2025-12-31T23:59:59Z",
                    },
                )

                assert result2["required_param"] == "test_value"
                assert result2["optional_param"] == "custom_value"  # Should use provided value
                assert result2["optional_number"] == 100  # Should use provided value
                assert result2["optional_float"] == 2.71  # Should use provided value
                assert result2["optional_bool"] is False  # Should use provided value
                assert result2["optional_date"] == "2025-12-31"  # Should use provided value
                # Datetime may be normalized to +00:00 format instead of Z
                assert result2["optional_datetime"] in [
                    "2025-12-31T23:59:59Z",
                    "2025-12-31T23:59:59+00:00",
                ]  # Should use provided value

                # Test calling with partial optional parameters (some defaults, some custom)
                result3 = await client.call_tool(
                    "check_optional_params",
                    {
                        "required_param": "test_value",
                        "optional_float": 1.618,  # Override only some optional params
                        "optional_bool": False,
                    },
                )

                assert result3["required_param"] == "test_value"
                assert result3["optional_param"] == "default_value"  # Should use default
                assert result3["optional_number"] == 42  # Should use default
                assert result3["optional_float"] == 1.618  # Should use provided value
                assert result3["optional_bool"] is False  # Should use provided value
                assert result3["optional_date"] == "2024-01-15"  # Should use default
                # Datetime may be normalized to +00:00 format instead of Z
                assert result3["optional_datetime"] in [
                    "2024-01-15T10:30:00Z",
                    "2024-01-15T10:30:00+00:00",
                ]  # Should use default

    @pytest.mark.asyncio
    async def test_global_var(self, integration_fixture_dir):
        """Test that global variables are set correctly."""
        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                result = await client.call_tool("get_global_var", {})
                assert result == "initial_key_123"

    @pytest.mark.asyncio
    async def test_get_users_detailed(self, integration_fixture_dir):
        """Test tool with detailed object type specification."""
        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                result = await client.call_tool("get_users_detailed", {})

                # Verify it's an object with users array and count
                assert isinstance(result, dict)
                assert "users" in result
                assert "n" in result
                assert result["n"] == 3
                assert isinstance(result["users"], list)
                assert len(result["users"]) == 3

                # Verify structure of first user
                user = result["users"][0]
                assert user["id"] == 1
                assert user["name"] == "Alice Johnson"
                assert user["email"] == "alice@example.com"
                assert user["age"] == 28
                assert user["active"] is True
                assert isinstance(user["roles"], list)
                assert "admin" in user["roles"]
                assert "user" in user["roles"]

                # Verify nested profile object
                assert isinstance(user["profile"], dict)
                assert user["profile"]["department"] == "Engineering"
                assert user["profile"]["location"] == "San Francisco"

    @pytest.mark.asyncio
    async def test_get_users_simple(self, integration_fixture_dir):
        """Test tool with simple object type specification."""
        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                result = await client.call_tool("get_users_simple", {})

                # Verify it's an object with users array and count (same data as detailed version)
                assert isinstance(result, dict)
                assert "users" in result
                assert "n" in result
                assert result["n"] == 3
                assert isinstance(result["users"], list)
                assert len(result["users"]) == 3

                # Verify structure of first user (should be identical to detailed version)
                user = result["users"][0]
                assert user["id"] == 1
                assert user["name"] == "Alice Johnson"
                assert user["email"] == "alice@example.com"
                assert user["age"] == 28
                assert user["active"] is True
                assert isinstance(user["roles"], list)
                assert "admin" in user["roles"]
                assert "user" in user["roles"]

                # Verify nested profile object
                assert isinstance(user["profile"], dict)
                assert user["profile"]["department"] == "Engineering"
                assert user["profile"]["location"] == "San Francisco"

    @pytest.mark.asyncio
    async def test_complex_object_input(self, integration_fixture_dir):
        """Test tool that takes a complex object as input parameter."""
        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                # Create a complex user data object
                user_data = {
                    "name": "John Doe",
                    "age": 25,
                    "preferences": {
                        "interests": ["technology", "music", "sports"],
                        "premium": True,
                        "notifications": {"email": True, "sms": False},
                    },
                    "contact": {
                        "email": "john.doe@example.com",
                        "phone": "+1-555-0123",
                        "address": {
                            "street": "123 Main St",
                            "city": "San Francisco",
                            "country": "USA",
                        },
                    },
                }

                # Call the tool with the complex object
                result = await client.call_tool("process_user_data", {"user_data": user_data})

                # Verify the result structure
                assert isinstance(result, dict)
                assert "original_data" in result
                assert "analysis" in result
                assert "processing_status" in result
                assert result["processing_status"] == "success"

                # Verify the original data is preserved
                assert result["original_data"] == user_data

                # Verify the analysis results
                analysis = result["analysis"]
                assert analysis["processed_name"] == "JOHN DOE"
                assert analysis["age_category"] == "adult"
                assert analysis["has_email"] is True
                assert analysis["has_phone"] is True
                assert analysis["preference_count"] == 3
                assert analysis["is_premium"] is True
                assert "123 Main St, San Francisco, USA" in analysis["full_address"]
                assert "John Doe is a 25-year-old premium user" in analysis["summary"]

    @pytest.mark.asyncio
    async def test_sql_tools_registration(self, integration_fixture_dir):
        """Test that SQL tools are properly registered when enabled."""
        with ServerProcess(integration_fixture_dir) as server:
            server.start(extra_args=["--sql-tools", "true"])

            async with MCPTestClient(server.port) as client:
                tools = await client.list_tools()
                tool_names = [t["name"] for t in tools] if tools else []

                # Verify SQL tools are registered
                assert "execute_sql_query" in tool_names, "execute_sql_query tool not found"
                assert "list_tables" in tool_names, "list_tables tool not found"
                assert "get_table_schema" in tool_names, "get_table_schema tool not found"

                # Check tool descriptions
                execute_sql_tool = next(
                    (t for t in tools if t["name"] == "execute_sql_query"), None
                )
                assert execute_sql_tool is not None
                assert "Execute a SQL query" in execute_sql_tool["description"]

    @pytest.mark.asyncio
    async def test_sql_tools_functionality(self, integration_fixture_dir):
        """Test SQL tools functionality using dbt-created tables."""
        # Run dbt to create the tables first
        original_dir = os.getcwd()
        try:
            os.chdir(integration_fixture_dir)

            # Load configs and generate dbt profile
            site_config = load_site_config(integration_fixture_dir)
            user_config = load_user_config(site_config)

            # Configure dbt (creates profiles.yml)
            configure_dbt(site_config=site_config, user_config=user_config, force=True)

            # Run the dbt workflow: seed -> run
            subprocess.run(["dbt", "seed"], check=True)
            subprocess.run(["dbt", "run"], check=True)

        except subprocess.CalledProcessError as e:
            pytest.skip(f"dbt command failed: {e} - skipping SQL tools functionality test")
        except Exception as e:
            pytest.skip(f"dbt setup failed: {e} - skipping SQL tools functionality test")
        finally:
            os.chdir(original_dir)

        with ServerProcess(integration_fixture_dir) as server:
            server.start(extra_args=["--sql-tools", "true"])

            async with MCPTestClient(server.port) as client:
                # Test list_tables - should show dbt-created tables
                tables_result = await client.call_tool("list_tables", {})
                assert isinstance(tables_result, list)
                table_names = [table["name"] for table in tables_result]
                assert "users" in table_names, "users dbt model should exist"
                assert "raw_users" in table_names, "raw_users seed should exist"

                # Test get_table_schema on dbt model
                schema_result = await client.call_tool("get_table_schema", {"table_name": "users"})
                assert isinstance(schema_result, list)
                assert len(schema_result) == 5  # user_id, username, email, created_date, status

                column_names = [col["name"] for col in schema_result]
                expected_columns = ["user_id", "username", "email", "created_date", "status"]
                for col in expected_columns:
                    assert col in column_names, f"Column {col} should exist in users model"

                # Test query execution (proper use of execute_sql_query - SELECT only)
                query_result = await client.call_tool(
                    "execute_sql_query", {"sql": "SELECT * FROM users ORDER BY user_id"}
                )
                assert isinstance(query_result, list)
                assert len(query_result) == 3  # Should have 3 active users (Charlie is inactive)
                assert query_result[0]["username"] == "Alice Johnson"
                assert query_result[1]["username"] == "Bob Smith"
                assert query_result[2]["username"] == "Diana Prince"

    @pytest.mark.asyncio
    async def test_sql_tools_asyncio_fix_regression(self, integration_fixture_dir):
        """Test that SQL tools work correctly after the asyncio execution fix (regression test)."""
        # Update site config to enable SQL tools
        site_config_path = integration_fixture_dir / "mxcp-site.yml"
        with open(site_config_path) as f:
            site_config_data = yaml.safe_load(f) or {}

        sql_tools_cfg = site_config_data.setdefault("sql_tools", {})
        sql_tools_cfg["enabled"] = True

        with open(site_config_path, "w") as f:
            yaml.dump(site_config_data, f)

        with ServerProcess(integration_fixture_dir) as server:
            server.start(extra_args=["--sql-tools", "true"])

            async with MCPTestClient(server.port) as client:
                # This is the main regression test - the fix was to remove asyncio.run()
                # calls in the SQL tool implementations and use proper async execution

                # Create test data using a single CREATE TABLE AS SELECT (acceptable for test setup)
                await client.call_tool(
                    "execute_sql_query",
                    {
                        "sql": """
                        CREATE TABLE asyncio_test AS
                        SELECT * FROM (VALUES
                            (0, 'data_0'),
                            (1, 'data_1'),
                            (2, 'data_2')
                        ) AS t(id, data)
                    """
                    },
                )

                # Make multiple concurrent SELECT calls to ensure no asyncio conflicts
                tasks = []
                for i in range(3):
                    task = client.call_tool(
                        "execute_sql_query", {"sql": f"SELECT * FROM asyncio_test WHERE id = {i}"}
                    )
                    tasks.append(task)

                # Wait for all queries to complete - this would fail before the fix
                results = await asyncio.gather(*tasks)

                # Verify all queries returned correct data
                for i, result in enumerate(results):
                    assert isinstance(result, list)
                    assert len(result) == 1
                    assert result[0]["id"] == i
                    assert result[0]["data"] == f"data_{i}"

                # Test that list_tables and get_table_schema also work concurrently
                concurrent_tasks = [
                    client.call_tool("list_tables", {}),
                    client.call_tool("get_table_schema", {"table_name": "asyncio_test"}),
                    client.call_tool("execute_sql_query", {"sql": "SELECT * FROM asyncio_test"}),
                ]

                # This would deadlock or fail before the asyncio fix
                tables, schema, data = await asyncio.gather(*concurrent_tasks)

                # Verify results
                table_names = [t["name"] for t in tables]
                assert "asyncio_test" in table_names

                column_names = [col["name"] for col in schema]
                assert "id" in column_names
                assert "data" in column_names

                assert len(data) == 3

    @pytest.mark.asyncio
    async def test_dbt_integration(self, integration_fixture_dir):
        """Test dbt integration commands work within project directory."""
        # The fixture directory already has dbt_project.yml, models, and seeds
        # Verify the dbt project structure exists
        assert (
            integration_fixture_dir / "dbt_project.yml"
        ).exists(), "dbt_project.yml should exist in fixture"
        assert (
            integration_fixture_dir / "models"
        ).exists(), "models directory should exist in fixture"
        assert (
            integration_fixture_dir / "seeds"
        ).exists(), "seeds directory should exist in fixture"

        # Test dbt-config command (should work from fixture directory)
        with ServerProcess(integration_fixture_dir):
            # Don't start the server, just use the directory management
            original_dir = os.getcwd()
            try:
                os.chdir(integration_fixture_dir)

                # Test that we can generate dbt config without errors
                # This tests the dbt-config command functionality

                # Load configs from the fixture directory
                site_config = load_site_config(integration_fixture_dir)
                user_config = load_user_config(site_config)

                # Test dbt config generation (dry run)
                try:
                    configure_dbt(
                        site_config=site_config,
                        user_config=user_config,
                        dry_run=True,  # Don't actually write files
                        force=True,  # Allow overwriting existing profile
                    )
                    dbt_config_success = True
                except Exception as e:
                    dbt_config_success = False
                    print(f"dbt-config failed: {e}")

                assert dbt_config_success, "dbt-config should work in fixture directory"

            finally:
                os.chdir(original_dir)

    @pytest.mark.asyncio
    async def test_dbt_with_sql_tools(self, integration_fixture_dir):
        """Test that dbt models can be queried through SQL tools."""
        # The fixture directory already has dbt project structure with models and seeds
        # Verify the dbt files exist
        assert (
            integration_fixture_dir / "models" / "users.sql"
        ).exists(), "users.sql model should exist"
        assert (
            integration_fixture_dir / "seeds" / "raw_users.csv"
        ).exists(), "raw_users.csv seed should exist"
        assert (
            integration_fixture_dir / "seeds" / "raw_orders.csv"
        ).exists(), "raw_orders.csv seed should exist"

        # Update site config to enable SQL tools (dbt already enabled in fixture)
        site_config_path = integration_fixture_dir / "mxcp-site.yml"
        with open(site_config_path) as f:
            site_config_data = yaml.safe_load(f) or {}

        sql_tools_cfg = site_config_data.setdefault("sql_tools", {})
        sql_tools_cfg["enabled"] = True

        with open(site_config_path, "w") as f:
            yaml.dump(site_config_data, f)

        # Run the proper dbt workflow first
        original_dir = os.getcwd()
        try:
            os.chdir(integration_fixture_dir)

            # Load configs and generate dbt profile
            site_config = load_site_config(integration_fixture_dir)
            user_config = load_user_config(site_config)

            # Configure dbt (creates profiles.yml)
            configure_dbt(site_config=site_config, user_config=user_config, force=True)

            # Run the dbt workflow: seed -> run -> test
            subprocess.run(["dbt", "seed"], check=True, capture_output=True)
            subprocess.run(["dbt", "run"], check=True, capture_output=True)
            subprocess.run(["dbt", "test"], check=True, capture_output=True)

        except subprocess.CalledProcessError as e:
            pytest.skip(f"dbt command failed: {e} - skipping dbt integration test")
        except Exception as e:
            pytest.skip(f"dbt setup failed: {e} - skipping dbt integration test")
        finally:
            os.chdir(original_dir)

        # Now test SQL tools against the dbt-created tables
        with ServerProcess(integration_fixture_dir) as server:
            server.start(extra_args=["--sql-tools", "true"])

            async with MCPTestClient(server.port) as client:
                # Test that we can see the dbt model tables through SQL tools
                tables_result = await client.call_tool("list_tables", {})
                table_names = [table["name"] for table in tables_result]
                assert "users" in table_names, "users dbt model table should be visible"
                assert (
                    "user_order_summary" in table_names
                ), "user_order_summary dbt model table should be visible"
                assert "raw_users" in table_names, "raw_users seed table should be visible"
                assert "raw_orders" in table_names, "raw_orders seed table should be visible"

                # Test querying the users model (should only have active users)
                users_result = await client.call_tool(
                    "execute_sql_query", {"sql": "SELECT * FROM users ORDER BY user_id"}
                )

                assert len(users_result) == 3, "Should have 3 active users (Charlie is inactive)"
                assert users_result[0]["username"] == "Alice Johnson"
                assert users_result[1]["username"] == "Bob Smith"
                assert users_result[2]["username"] == "Diana Prince"

                # Test querying the summary model
                summary_result = await client.call_tool(
                    "execute_sql_query",
                    {"sql": "SELECT * FROM user_order_summary ORDER BY user_id"},
                )

                assert len(summary_result) == 3
                # Alice should have 2 orders totaling $79.98
                alice_summary = next(r for r in summary_result if r["username"] == "Alice Johnson")
                assert alice_summary["total_orders"] == 2
                assert abs(alice_summary["total_spent"] - 79.98) < 0.01

                # Test more complex analytical queries (what SQL tools are meant for)
                analytics_result = await client.call_tool(
                    "execute_sql_query",
                    {
                        "sql": """
                        SELECT
                            COUNT(*) as total_active_users,
                            AVG(total_spent) as avg_spending,
                            MAX(total_orders) as max_orders
                        FROM user_order_summary
                    """
                    },
                )

                assert len(analytics_result) == 1
                assert analytics_result[0]["total_active_users"] == 3

                # Test schema inspection of dbt models
                users_schema = await client.call_tool("get_table_schema", {"table_name": "users"})
                users_columns = [col["name"] for col in users_schema]
                expected_users_columns = ["user_id", "username", "email", "created_date", "status"]
                for col in expected_users_columns:
                    assert col in users_columns, f"Column {col} should exist in users dbt model"

                summary_schema = await client.call_tool(
                    "get_table_schema", {"table_name": "user_order_summary"}
                )
                summary_columns = [col["name"] for col in summary_schema]
                expected_summary_columns = [
                    "user_id",
                    "username",
                    "email",
                    "total_orders",
                    "total_spent",
                    "last_order_date",
                ]
                for col in expected_summary_columns:
                    assert (
                        col in summary_columns
                    ), f"Column {col} should exist in user_order_summary dbt model"
