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
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
import yaml

# Import MCP SDK for making protocol calls
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


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

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
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
        self.process: Optional[subprocess.Popen] = None
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
        "profiles": {"default": {"duckdb": {"path": ":memory:"}}},
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
    async def test_integer_parameter_conversion(self, integration_fixture_dir):
        """Test that integer parameters are properly converted from JSON float values."""
        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                # Test with float value 0.0 - this should be converted to int(0)
                result = await client.call_tool("check_integer_parameter", {"top_n": 0.0})

                # If the bug exists, test_passed will be False and we'll get an error
                if not result["test_passed"]:
                    pytest.fail(
                        f"Integer conversion bug detected: {result.get('error', 'Unknown error')}"
                    )

                assert result["top_n"] == 0
                assert result["type_received"] == "<class 'int'>"
                assert result["selected_items"] == []
                assert result["test_passed"] is True

                # Test with float value 2.0 - this should be converted to int(2)
                result = await client.call_tool("check_integer_parameter", {"top_n": 2.0})

                if not result["test_passed"]:
                    pytest.fail(
                        f"Integer conversion bug detected: {result.get('error', 'Unknown error')}"
                    )

                assert result["top_n"] == 2
                assert result["type_received"] == "<class 'int'>"
                assert result["selected_items"] == ["first", "second"]
                assert result["test_passed"] is True

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
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        config["projects"]["integration_test"]["profiles"]["default"]["secrets"][0][
            "parameters"
        ] = {"api_key": f"file://{secret_file}", "endpoint": f"file://{endpoint_file}"}

        with open(config_path, "w") as f:
            yaml.dump(config, f)

        with ServerProcess(integration_fixture_dir) as server:
            server.start()

            async with MCPTestClient(server.port) as client:
                # Check initial values
                result1 = await client.call_tool("check_secret", {})
                assert result1["api_key"] == "file_secret_v1"
                assert result1["endpoint"] == "https://api.v1.example.com"

                # Update external values
                secret_file.write_text("file_secret_v2")
                endpoint_file.write_text("https://api.v2.example.com")

                # Reload
                server.reload()

                # Add a small additional delay to ensure the reload thread completes
                await asyncio.sleep(0.5)

                # Check updated values
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
                initial_length = result["length"]

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
    async def test_non_duckdb_secret_types(self, integration_fixture_dir):
        """Test that non-DuckDB secret types work correctly."""
        # Update config to have multiple secret types
        config_path = integration_fixture_dir / "mxcp-config.yml"
        with open(config_path, "r") as f:
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
        with open(site_config_path, "r") as f:
            site_config = yaml.safe_load(f)

        site_config["secrets"] = ["custom_secret", "python_secret"]

        with open(site_config_path, "w") as f:
            yaml.dump(site_config, f)

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
