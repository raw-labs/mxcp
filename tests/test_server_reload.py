"""Test server hot reload functionality."""
import pytest
import os
import tempfile
import signal
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from mxcp.server.mcp import RAWMCP
from mxcp.config.site_config import SiteConfig
from mxcp.config.user_config import UserConfig


class TestServerReload:
    """Test the server's configuration reload functionality."""
    
    @pytest.fixture
    def mock_configs(self):
        """Create mock configurations for testing."""
        site_config = {
            "version": "1",
            "project": "test_project",
            "profile": "default",
            "profiles": {
                "default": {
                    "duckdb": {"path": ":memory:"},
                    "drift": {"path": "drift.json"},
                    "audit": {"enabled": False}
                }
            },
            "paths": {
                "tools": "tools",
                "resources": "resources",
                "prompts": "prompts",
                "python": "python",
                "sql": "sql",
                "plugins": "plugins",
                "drift": "drift",
                "audit": "audit",
                "data": "data",
                "evals": "evals"
            },
            "extensions": [],
            "dbt": {"enabled": False}
        }
        
        user_config = {
            "version": "1",
            "projects": {
                "test_project": {
                    "profiles": {
                        "default": {
                            "secrets": [{
                                "name": "test_secret",
                                "type": "generic",
                                "parameters": {
                                    "value": "${TEST_VALUE}"
                                }
                            }]
                        }
                    }
                }
            }
        }
        
        return site_config, user_config
    
    def _create_server_with_mocks(self, site_config, user_config):
        """Helper to create a server with all necessary mocks."""
        with patch('mxcp.server.mcp.EndpointLoader') as mock_loader:
            mock_loader.return_value.discover_endpoints.return_value = []
            
            with patch.object(RAWMCP, '_init_python_runtime'):
                with patch.object(RAWMCP, 'register_endpoints'):
                    with patch.object(RAWMCP, '_register_signal_handlers'):
                        with patch('mxcp.server.mcp.DuckDBSession'):
                            server = RAWMCP(user_config, site_config)
                            return server
    
    def test_reload_updates_external_values(self, mock_configs):
        """Test that reload updates external configuration values."""
        site_config, user_config = mock_configs
        
        # Set initial environment value
        os.environ['TEST_VALUE'] = 'initial_value'
        
        # Create server
        server = self._create_server_with_mocks(site_config, user_config)
        
        # Verify initial value was resolved
        profile = server.user_config['projects']['test_project']['profiles']['default']
        assert profile['secrets'][0]['parameters']['value'] == 'initial_value'
        
        # Change environment value
        os.environ['TEST_VALUE'] = 'updated_value'
        
        # Trigger reload
        with patch.object(server, '_shutdown_runtime_components'):
            with patch.object(server, '_init_python_runtime'):
                with patch('mxcp.server.mcp.DuckDBSession'):
                    server.reload_configuration()
        
        # Verify value was updated
        profile = server.user_config['projects']['test_project']['profiles']['default']
        assert profile['secrets'][0]['parameters']['value'] == 'updated_value'
    
    def test_reload_no_changes(self, mock_configs):
        """Test that reload does nothing when values haven't changed."""
        site_config, user_config = mock_configs
        
        # Set environment value
        os.environ['TEST_VALUE'] = 'same_value'
        
        # Create server
        server = self._create_server_with_mocks(site_config, user_config)
        
        # Mock the shutdown method to track if it's called
        shutdown_called = False
        def mock_shutdown():
            nonlocal shutdown_called
            shutdown_called = True
        
        with patch.object(server, '_shutdown_runtime_components', mock_shutdown):
            with patch.object(server, '_init_python_runtime'):
                server.reload_configuration()
        
        # Shutdown should NOT be called if no changes
        assert not shutdown_called
    
    def test_reload_with_file_reference(self, mock_configs, tmp_path):
        """Test reload with file:// references."""
        site_config, user_config = mock_configs
        
        # Create a test file
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("initial_secret")
        
        # Update config to use file reference
        user_config['projects']['test_project']['profiles']['default']['secrets'][0]['parameters']['value'] = f'file://{secret_file}'
        
        # Create server
        server = self._create_server_with_mocks(site_config, user_config)
        
        # Verify initial value
        profile = server.user_config['projects']['test_project']['profiles']['default']
        assert profile['secrets'][0]['parameters']['value'] == 'initial_secret'
        
        # Update file content
        time.sleep(0.01)  # Ensure mtime changes
        secret_file.write_text("updated_secret")
        
        # Trigger reload
        with patch.object(server, '_shutdown_runtime_components'):
            with patch.object(server, '_init_python_runtime'):
                with patch('mxcp.server.mcp.DuckDBSession'):
                    server.reload_configuration()
        
        # Verify value was updated
        profile = server.user_config['projects']['test_project']['profiles']['default']
        assert profile['secrets'][0]['parameters']['value'] == 'updated_secret'
    
    def test_reload_error_handling(self, mock_configs):
        """Test that reload handles errors gracefully."""
        site_config, user_config = mock_configs
        
        # Set initial environment value
        os.environ['TEST_VALUE'] = 'initial_value'
        
        # Create server
        server = self._create_server_with_mocks(site_config, user_config)
        
        # Verify initial state
        profile = server.user_config['projects']['test_project']['profiles']['default']
        assert profile['secrets'][0]['parameters']['value'] == 'initial_value'
        
        # Remove environment variable to cause error
        del os.environ['TEST_VALUE']
        
        # Reload should handle error gracefully
        with patch.object(server, '_shutdown_runtime_components'):
            with patch.object(server, '_init_python_runtime'):
                # Should not raise, just log error
                server.reload_configuration()
        
        # Original value should still be there
        profile = server.user_config['projects']['test_project']['profiles']['default']
        assert profile['secrets'][0]['parameters']['value'] == 'initial_value'
    
    def test_sighup_handler(self, mock_configs):
        """Test that SIGHUP signal triggers reload."""
        site_config, user_config = mock_configs
        
        # Set environment value
        os.environ['TEST_VALUE'] = 'initial_value'
        
        reload_called = threading.Event()
        
        # Create server
        server = self._create_server_with_mocks(site_config, user_config)
        
        # Mock reload_configuration to track calls
        def mock_reload():
            reload_called.set()
        
        with patch.object(server, 'reload_configuration', mock_reload):
            # Trigger SIGHUP handler directly (can't send real signals in tests)
            server._handle_reload_signal(signal.SIGHUP, None)
            
            # Wait for reload to be called (happens in separate thread)
            assert reload_called.wait(timeout=2.0)
    
    def teardown_method(self):
        """Clean up environment variables after each test."""
        if 'TEST_VALUE' in os.environ:
            del os.environ['TEST_VALUE'] 