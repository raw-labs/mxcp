import pytest
import subprocess
import os
from pathlib import Path

# Get the path to the e2e config directory with isolated test configuration
TEST_CONFIG_DIR = Path(__file__).parent.parent.parent / "fixtures" / "e2e-config"


@pytest.mark.asyncio
async def test_tcp_server_basic():
    """Test that LSP server can start in TCP mode (basic smoke test)"""
    
    # Change to test config directory
    original_cwd = os.getcwd()
    os.chdir(str(TEST_CONFIG_DIR))
    
    try:
        # Test that the TCP command with --port option runs without crashing
        # We use a very short timeout to just verify it starts without immediate error
        result = subprocess.run(
            ["mxcp", "lsp", "--port", "12345"],
            capture_output=True,
            text=True,
            timeout=1  # Very short timeout - just checking it doesn't crash immediately
        )
        
        # We expect a timeout since the server should keep running
        # If it returns immediately with an error code, that's a problem
        assert False, "Server should not exit immediately"
        
    except subprocess.TimeoutExpired:
        # This is expected - the server should keep running
        pass
    except Exception as e:
        # Any other exception is a problem
        assert False, f"Unexpected error starting TCP server: {e}"
    finally:
        os.chdir(original_cwd) 