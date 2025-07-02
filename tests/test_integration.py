"""Integration tests for RAWMCP server with real MCP protocol calls.

These tests start an actual server subprocess and communicate with it using
the MCP protocol to test the full stack including configuration reloads.
"""
import pytest
import asyncio
import subprocess
import signal
import time
import os
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import httpx
import yaml

# Import MCP SDK for making protocol calls
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.session import ClientSession
    HAS_MCP_SDK = True
except ImportError:
    HAS_MCP_SDK = False
    # Fallback to direct HTTP calls if MCP SDK not available


class MCPTestClient:
    """Client for making MCP protocol calls to a running server."""
    
    def __init__(self, port: int = 8765):
        self.port = port
        self.base_url = f"http://localhost:{port}"
        self.client = httpx.AsyncClient(timeout=30.0)
        self.message_id = 0
        self.session_id = None  # Track session ID
    
    async def __aenter__(self):
        # Initialize the connection when entering context
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    def _next_id(self) -> str:
        """Get next message ID for JSON-RPC."""
        self.message_id += 1
        return str(self.message_id)
    
    async def _read_sse_stream(self, response: httpx.Response) -> Dict[str, Any]:
        """Read and parse SSE stream response."""
        full_content = ""
        line_count = 0
        
        async for line in response.aiter_lines():
            line_count += 1
            full_content += line + "\n"
            
            if line.startswith('data: '):
                json_data = line[6:]  # Remove 'data: ' prefix
                try:
                    result = json.loads(json_data)
                    # If we got a valid JSON-RPC response, return it
                    if "jsonrpc" in result:
                        return result
                except json.JSONDecodeError as e:
                    continue
        
        # If no lines were received, the server might have returned an empty stream
        if line_count == 0:
            return {"jsonrpc": "2.0", "result": {}}
        
        # If we couldn't parse any data, show what we got
        raise ValueError(f"No valid JSON-RPC data found in SSE stream after {line_count} lines. Content: {full_content}")
    
    async def _send_request(self, method: str, params: Dict[str, Any]) -> tuple[Dict[str, Any], httpx.Response]:
        """Send a JSON-RPC request and handle the response. Returns (result, response)."""
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        
        # Add session ID header if we have one
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        
        # Use stream=True to handle SSE responses properly
        async with self.client.stream(
            "POST",
            f"{self.base_url}/mcp/",
            json=request,
            headers=headers
        ) as response:
            
            # Check for 202 Accepted (which means no body)
            if response.status_code == 202:
                return {}, type('Response', (), {'headers': response.headers})()
            
            # If not successful, try to get error details
            if not response.is_success:
                try:
                    error_text = await response.aread()
                except:
                    pass
                response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get("content-type", "")
            
            # Store session ID if present (on first response)
            session_id = response.headers.get("Mcp-Session-Id")
            
            if "text/event-stream" in content_type:
                # Handle SSE stream
                result = await self._read_sse_stream(response)
            else:
                # Handle regular JSON
                content = await response.aread()
                if content:
                    result = json.loads(content)
                else:
                    result = {"jsonrpc": "2.0", "result": {}}
            
            if "error" in result:
                raise Exception(f"MCP error: {result['error']}")
            
            # Return the result and a response-like object with headers
            return result.get("result", {}), type('Response', (), {'headers': response.headers})()
    
    async def initialize(self):
        """Initialize the MCP connection."""
        result, response = await self._send_request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {}
            },
            "clientInfo": {
                "name": "MXCP Integration Test Client",
                "version": "1.0.0"
            }
        })
        
        # Extract session ID from response headers
        self.session_id = response.headers.get("Mcp-Session-Id")
        if self.session_id:
            pass
        
        # Send initialized notification to complete handshake
        await self._send_notification("notifications/initialized", {})
        
        return result
    
    async def _send_notification(self, method: str, params: Dict[str, Any]):
        """Send a JSON-RPC notification (no response expected)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
            # No "id" field for notifications
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        
        # Add session ID header if we have one
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        
        response = await self.client.post(
            f"{self.base_url}/mcp/",
            json=notification,
            headers=headers
        )
        
        # For notifications, we expect 202 Accepted
        if response.status_code != 202:
            print(f"Unexpected status for notification: {response.status_code}")
            print(f"Response: {response.text}")
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool via MCP protocol."""
        result, _ = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        
        # Extract the actual result from MCP format
        if "content" in result and isinstance(result["content"], list) and len(result["content"]) > 0:
            content = result["content"][0]
            if content.get("type") == "text" and "text" in content:
                # Parse the JSON text content
                try:
                    return json.loads(content["text"])
                except json.JSONDecodeError:
                    # If it's not JSON, return the text as-is
                    return {"result": content["text"]}
        
        # Fallback to returning the raw result
        return result
    
    async def list_tools(self) -> list:
        """List available tools."""
        result, _ = await self._send_request("tools/list", {})
        return result.get("tools", [])


class ServerProcess:
    """Manager for RAWMCP server subprocess."""
    
    def __init__(self, working_dir: Path, port: int = 8765):
        self.working_dir = working_dir
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.original_dir = os.getcwd()
    
    def start(self, extra_args: list = None):
        """Start the server process."""
        os.chdir(self.working_dir)
        
        cmd = [
            "mxcp", "serve",
            "--port", str(self.port),
            "--transport", "streamable-http"
        ]
        if extra_args:
            cmd.extend(extra_args)
        
        # Set MXCP_CONFIG to use our test config
        env = os.environ.copy()
        env["MXCP_CONFIG"] = str(self.working_dir / "mxcp-config.yml")
        
        # print(f"Starting server in {self.working_dir}")
        # print(f"Command: {' '.join(cmd)}")
        # print(f"MXCP_CONFIG: {env['MXCP_CONFIG']}")
        
        self.process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Combine stdout and stderr
            text=True
        )
        
        # Start a thread to read server output
        import threading
        def read_output():
            for line in self.process.stdout:
                # Enable output for debugging when needed
                if os.environ.get("MXCP_TEST_DEBUG"):
                    print(f"[SERVER] {line.strip()}")
                pass
        
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
                result = sock.connect_ex(('localhost', self.port))
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
        
        os.chdir(self.original_dir)
    
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
        "transport": {
            "provider": "streamable-http",
            "http": {
                "port": 8765,
                "host": "localhost"
            }
        },
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
                                    "endpoint": "https://api.example.com"
                                }
                            }
                        ]
                    }
                }
            }
        }
    }
    
    with open(fixture_path / "mxcp-config.yml", "w") as f:
        yaml.dump(user_config, f)
    
    # Create site config
    site_config = {
        "mxcp": 1,
        "project": "integration_test",
        "profile": "default",
        "profiles": {
            "default": {
                "duckdb": {
                    "path": ":memory:"
                }
            }
        },
        "secrets": ["test_secret"]
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
            "source": {
                "file": "../python/test_endpoints.py"
            },
            "parameters": [],
            "return": {
                "type": "object"
            }
        }
    }
    
    with open(fixture_path / "tools" / "check_secret.yml", "w") as f:
        yaml.dump(check_secret_tool, f)
    
    echo_tool = {
        "mxcp": 1,
        "tool": {
            "name": "echo_message",
            "description": "Echo a message",
            "language": "python",
            "source": {
                "file": "../python/test_endpoints.py"
            },
            "parameters": [
                {
                    "name": "message",
                    "type": "string",
                    "description": "Message to echo"
                }
            ],
            "return": {
                "type": "object"
            }
        }
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
            
            async with MCPTestClient() as client:
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
            
            async with MCPTestClient() as client:
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
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        config["projects"]["integration_test"]["profiles"]["default"]["secrets"][0]["parameters"] = {
            "api_key": f"file://{secret_file}",
            "endpoint": f"file://{endpoint_file}"
        }
        
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        
        with ServerProcess(integration_fixture_dir) as server:
            server.start()
            
            async with MCPTestClient() as client:
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
                    "x_custom_header": "header_value"  # Flat structure
                }
            },
            {
                "name": "python_secret",
                "type": "python",
                "parameters": {
                    "value": "python_only_value",
                    "nested_value": "deep_value"  # Flat structure instead of nested
                }
            }
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
                "source": {
                    "file": "../python/test_endpoints.py"
                },
                "parameters": [],
                "return": {
                    "type": "object"
                }
            }
        }
        
        with open(integration_fixture_dir / "tools" / "check_all_secrets.yml", "w") as f:
            yaml.dump(tool_def, f)
        
        with ServerProcess(integration_fixture_dir) as server:
            server.start()
            
            async with MCPTestClient() as client:
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
            
            async with MCPTestClient() as client:
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


@pytest.mark.skipif(not HAS_MCP_SDK, reason="MCP SDK not available")
class TestIntegrationWithMCPSDK:
    """Integration tests using the official MCP SDK (if available)."""
    
    @pytest.mark.asyncio
    async def test_stdio_transport(self, integration_fixture_dir):
        """Test using stdio transport with MCP SDK."""
        # This would test stdio transport mode
        # Implementation depends on MCP SDK availability
        pass 
        pass 