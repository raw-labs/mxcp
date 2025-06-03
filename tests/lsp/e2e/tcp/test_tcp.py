import os
import asyncio
import socket
import subprocess
from pathlib import Path

import pytest
from lsprotocol.types import InitializeParams, ClientCapabilities
from pytest_lsp import LanguageClient
from pygls.protocol import JsonRPCProtocol

# Get the path to the e2e config directory with isolated test configuration
TEST_CONFIG_DIR = Path(__file__).parent.parent.parent / "fixtures" / "e2e-config"


def find_free_port() -> int:
    """Find a free port for testing"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


class ClientProtocol(JsonRPCProtocol):
    """Client protocol that doesn't exit on connection loss"""
    def connection_lost(self, exc):
        pass  # Don't exit on connection loss


class TCPClient(LanguageClient):
    """Simple TCP client for testing"""
    def __init__(self):
        super().__init__(protocol_cls=ClientProtocol)
        self._transport = None
    
    async def connect_tcp(self, host: str, port: int):
        """Connect to TCP server"""
        for _ in range(30):  # 3 second timeout
            try:
                self._transport, _ = await asyncio.get_event_loop().create_connection(
                    lambda: self.protocol, host, port
                )
                return
            except ConnectionRefusedError:
                await asyncio.sleep(0.1)
        raise ConnectionError(f"Could not connect to {host}:{port}")


@pytest.mark.asyncio
async def test_tcp_server_basic():
    """Test that LSP server starts in TCP mode and accepts connections"""
    port = find_free_port()
    
    # Change to test config directory
    original_cwd = os.getcwd()
    os.chdir(str(TEST_CONFIG_DIR))
    
    # Start server
    server = subprocess.Popen(
        ["mxcp", "lsp", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    try:
        await asyncio.sleep(1)  # Let server start
        
        # Verify server is running
        assert server.poll() is None, "Server should be running"
        
        # Connect and test basic LSP functionality
        client = TCPClient()
        await client.connect_tcp("localhost", port)
        
        # Initialize - simplest LSP interaction
        result = await client.initialize_async(InitializeParams(capabilities=ClientCapabilities()))
        
        # Verify we got a proper LSP response
        assert result is not None
        assert hasattr(result, 'capabilities')
        
        # Clean shutdown
        client.initialized({})
        await client.shutdown_async(None)
        client.exit(None)
        
    finally:
        os.chdir(original_cwd)
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait() 