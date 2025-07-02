"""Test configuration reload functionality via signals."""
import pytest
import os
import signal
import time
import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from contextlib import contextmanager
from mxcp.server.mcp import RAWMCP


def get_mock_user_config(extra_profile_config=None):
    """Get a complete mock user config structure.
    
    Args:
        extra_profile_config: Optional dict to merge into the default profile
    """
    config = {
        'transport': {
            'provider': 'streamable-http'
        },
        'projects': {
            'test': {
                'profiles': {
                    'default': {}
                }
            }
        }
    }
    
    if extra_profile_config:
        config['projects']['test']['profiles']['default'].update(extra_profile_config)
    
    return config


@contextmanager
def temp_working_directory(path):
    """Context manager to temporarily change working directory."""
    original_cwd = os.getcwd()
    try:
        os.chdir(path)
        yield path
    finally:
        os.chdir(original_cwd)


class TestConfigReload:
    """Test hot reload via SIGHUP signal."""
    
    @patch('mxcp.config.user_config.load_user_config')
    @patch('mxcp.server.mcp.DuckDBSession')
    @patch('mxcp.server.mcp.EndpointLoader')
    def test_sighup_handler_registration(self, mock_loader, mock_db, mock_load_user_config):
        """Test that SIGHUP handler is properly registered."""
        # Mock user config loading to avoid env var issues
        mock_load_user_config.return_value = get_mock_user_config()
        
        # Create a minimal server instance
        with tempfile.TemporaryDirectory() as tmpdir:
            with temp_working_directory(tmpdir):
                site_config_path = Path(tmpdir)
                
                # Create minimal config files
                (site_config_path / "mxcp-site.yml").write_text("""
mxcp: 1
project: test
profile: default
profiles:
  default:
    duckdb:
      path: ":memory:"
""")
                (site_config_path / "mxcp-config.yml").write_text("""
transport:
  provider: streamable-http
""")
                
                server = RAWMCP(site_config_path=site_config_path)
                
                # Check that SIGHUP handler is registered
                if hasattr(signal, 'SIGHUP'):
                    # Get the current handler
                    current_handler = signal.getsignal(signal.SIGHUP)
                    assert current_handler == server._handle_reload_signal
    
    @patch('mxcp.config.user_config.load_user_config')
    @patch('mxcp.server.mcp.DuckDBSession')
    @patch('mxcp.server.mcp.EndpointLoader')
    def test_reload_configuration_with_file_changes(self, mock_loader, mock_db, mock_load_user_config):
        """Test reload_configuration when file values change."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with temp_working_directory(tmpdir):
                site_config_path = Path(tmpdir)
                secret_file = Path(tmpdir) / "secret.txt"
                secret_file.write_text("initial_secret")
                
                # Mock user config with file reference in secrets
                mock_load_user_config.return_value = get_mock_user_config({
                    'secrets': [{
                        'name': 'db_password',
                        'type': 'generic',
                        'parameters': {
                            'value': f'file://{secret_file}'
                        }
                    }]
                })
                
                # Create config files
                (site_config_path / "mxcp-site.yml").write_text("""
mxcp: 1
project: test
profile: default
profiles:
  default:
    duckdb:
      path: ":memory:"
""")
                (site_config_path / "mxcp-config.yml").write_text("""
transport:
  provider: streamable-http
""")
                
                # Mock DuckDB session
                mock_db_instance = MagicMock()
                mock_db.return_value = mock_db_instance
                
                # Create server
                server = RAWMCP(site_config_path=site_config_path)
                
                # Verify initial value was resolved
                profile = server.user_config['projects']['test']['profiles']['default']
                assert profile['secrets'][0]['parameters']['value'] == 'initial_secret'
                
                # Change the secret file
                secret_file.write_text("updated_secret")
                
                # Mock the shutdown and init methods
                with patch.object(server, '_shutdown_runtime_components') as mock_shutdown:
                    with patch.object(server, '_init_python_runtime') as mock_init:
                        # Call reload
                        server.reload_configuration()
                        
                        # Verify methods were called
                        mock_shutdown.assert_called_once()
                        mock_init.assert_called_once()
                        
                        # Verify new value
                        profile = server.user_config['projects']['test']['profiles']['default']
                        assert profile['secrets'][0]['parameters']['value'] == 'updated_secret'
    
    @patch('mxcp.config.user_config.load_user_config')
    @patch('mxcp.server.mcp.DuckDBSession')
    @patch('mxcp.server.mcp.EndpointLoader')
    def test_reload_no_changes(self, mock_loader, mock_db, mock_load_user_config):
        """Test reload_configuration when no values change."""
        # Mock user config
        mock_load_user_config.return_value = get_mock_user_config()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with temp_working_directory(tmpdir):
                site_config_path = Path(tmpdir)
                
                # Create static config (no external refs)
                (site_config_path / "mxcp-site.yml").write_text("""
mxcp: 1
project: test
profile: default
profiles:
  default:
    duckdb:
      path: ":memory:"
""")
                (site_config_path / "mxcp-config.yml").write_text("""
transport:
  provider: streamable-http
""")
                
                # Mock DuckDB session
                mock_db_instance = MagicMock()
                mock_db.return_value = mock_db_instance
                
                # Create server
                server = RAWMCP(site_config_path=site_config_path)
                
                # Mock the shutdown method
                with patch.object(server, '_shutdown_runtime_components') as mock_shutdown:
                    # Call reload
                    server.reload_configuration()
                    
                    # Shutdown should NOT be called when nothing changed
                    mock_shutdown.assert_not_called()
    
    @patch('mxcp.config.user_config.load_user_config')
    @patch('mxcp.server.mcp.DuckDBSession')
    @patch('mxcp.server.mcp.EndpointLoader')
    def test_reload_with_env_changes(self, mock_loader, mock_db, mock_load_user_config):
        """Test reload when environment variables change."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with temp_working_directory(tmpdir):
                site_config_path = Path(tmpdir)
                
                # Set initial env var
                os.environ['TEST_DB_PASSWORD'] = 'initial_pass'
                
                # Mock user config with env reference
                mock_load_user_config.return_value = get_mock_user_config({
                    'secrets': [{
                        'name': 'db_password',
                        'type': 'generic', 
                        'parameters': {
                            'value': '${TEST_DB_PASSWORD}'
                        }
                    }]
                })
                
                # Create config files
                (site_config_path / "mxcp-site.yml").write_text("""
mxcp: 1
project: test
profile: default
profiles:
  default:
    duckdb:
      path: ":memory:"
""")
                (site_config_path / "mxcp-config.yml").write_text("""
transport:
  provider: streamable-http
""")
                
                # Mock DuckDB session
                mock_db_instance = MagicMock()
                mock_db.return_value = mock_db_instance
                
                # Create server
                server = RAWMCP(site_config_path=site_config_path)
                
                # Verify initial value
                profile = server.user_config['projects']['test']['profiles']['default']
                assert profile['secrets'][0]['parameters']['value'] == 'initial_pass'
                
                # Change env var
                os.environ['TEST_DB_PASSWORD'] = 'updated_pass'
                
                # Mock the shutdown and init methods
                with patch.object(server, '_shutdown_runtime_components') as mock_shutdown:
                    with patch.object(server, '_init_python_runtime') as mock_init:
                        # Call reload
                        server.reload_configuration()
                        
                        # Verify reload happened
                        mock_shutdown.assert_called_once()
                        mock_init.assert_called_once()
                        
                        # Verify new value
                        profile = server.user_config['projects']['test']['profiles']['default']
                        assert profile['secrets'][0]['parameters']['value'] == 'updated_pass'
    
    @patch('mxcp.config.user_config.load_user_config')
    @patch('mxcp.server.mcp.DuckDBSession')
    @patch('mxcp.server.mcp.EndpointLoader')
    def test_reload_error_handling(self, mock_loader, mock_db, mock_load_user_config):
        """Test that reload handles errors gracefully when external references fail."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with temp_working_directory(tmpdir):
                site_config_path = Path(tmpdir)
                
                # Set initial env var
                os.environ['TEST_ERROR_VAR'] = 'initial_value'
                
                # Mock user config with env reference
                mock_load_user_config.return_value = get_mock_user_config({
                    'api_key': '${TEST_ERROR_VAR}'
                })
                
                # Create config files
                (site_config_path / "mxcp-site.yml").write_text("""
mxcp: 1
project: test
profile: default
profiles:
  default:
    duckdb:
      path: ":memory:"
""")
                (site_config_path / "mxcp-config.yml").write_text("""
transport:
  provider: streamable-http
""")
                
                # Mock DuckDB session
                mock_db_instance = MagicMock()
                mock_db.return_value = mock_db_instance
                
                # Create server
                server = RAWMCP(site_config_path=site_config_path)
                
                # Verify initial value
                profile = server.user_config['projects']['test']['profiles']['default']
                assert profile['api_key'] == 'initial_value'
                
                # Remove env var to cause error
                del os.environ['TEST_ERROR_VAR']
                
                # Mock the shutdown method
                with patch.object(server, '_shutdown_runtime_components') as mock_shutdown:
                    # Call reload - should handle error gracefully
                    server.reload_configuration()
                    
                    # Shutdown should NOT be called when error occurs
                    mock_shutdown.assert_not_called()
                    
                    # Original value should still be there
                    profile = server.user_config['projects']['test']['profiles']['default']
                    assert profile['api_key'] == 'initial_value'
    
    @patch('mxcp.config.user_config.load_user_config')
    def test_reload_thread_safety(self, mock_load_user_config):
        """Test that reload is thread-safe."""
        # Mock user config
        mock_load_user_config.return_value = get_mock_user_config()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with temp_working_directory(tmpdir):
                site_config_path = Path(tmpdir)
                
                # Create config
                (site_config_path / "mxcp-site.yml").write_text("""
mxcp: 1
project: test
profile: default
profiles:
  default:
    duckdb:
      path: ":memory:"
""")
                (site_config_path / "mxcp-config.yml").write_text("""
transport:
  provider: streamable-http
""")
                
                # Mock dependencies
                with patch('mxcp.server.mcp.DuckDBSession'):
                    with patch('mxcp.server.mcp.EndpointLoader'):
                        server = RAWMCP(site_config_path=site_config_path)
                        
                        # Replace the lock with a trackable one
                        lock_acquired = threading.Event()
                        original_lock = server.db_lock
                        
                        class TrackableLock:
                            def __enter__(self):
                                lock_acquired.set()
                                return original_lock.__enter__()
                            
                            def __exit__(self, *args):
                                return original_lock.__exit__(*args)
                        
                        server.db_lock = TrackableLock()
                        
                        # Call reload in a thread
                        reload_thread = threading.Thread(target=server.reload_configuration)
                        reload_thread.start()
                        
                        # Wait for lock to be acquired
                        assert lock_acquired.wait(timeout=2.0), "Lock was not acquired"
                        
                        # Ensure thread completes
                        reload_thread.join(timeout=2.0)
                        assert not reload_thread.is_alive()
    
    def teardown_method(self):
        """Clean up environment variables after each test."""
        # Clean up any test env vars
        for var in ['TEST_DB_PASSWORD', 'TEST_ERROR_VAR']:
            if var in os.environ:
                del os.environ[var]


class TestShutdownHooks:
    """Test shutdown hook functionality during reload."""
    
    @patch('mxcp.config.user_config.load_user_config')
    @patch('mxcp.server.mcp.DuckDBSession')
    @patch('mxcp.server.mcp.EndpointLoader')
    def test_python_shutdown_hooks_called(self, mock_loader, mock_db, mock_load_user_config):
        """Test that Python shutdown hooks are called during reload."""
        # Mock user config
        mock_load_user_config.return_value = get_mock_user_config()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with temp_working_directory(tmpdir):
                site_config_path = Path(tmpdir)
                
                # Create config
                (site_config_path / "mxcp-site.yml").write_text("""
mxcp: 1
project: test
profile: default
profiles:
  default:
    duckdb:
      path: ":memory:"
""")
                (site_config_path / "mxcp-config.yml").write_text("""
transport:
  provider: streamable-http
""")
                
                # Mock DuckDB session
                mock_db_instance = MagicMock()
                mock_db.return_value = mock_db_instance
                
                # Create server
                server = RAWMCP(site_config_path=site_config_path)
                
                # Mock shutdown functions
                with patch('mxcp.runtime._run_shutdown_hooks') as mock_py_shutdown:
                    with patch('mxcp.plugins.base.run_plugin_shutdown_hooks') as mock_plugin_shutdown:
                        # Call shutdown
                        server._shutdown_runtime_components()
                        
                        # Verify both were called
                        mock_py_shutdown.assert_called_once()
                        mock_plugin_shutdown.assert_called_once()
                        
                        # Verify DB was closed
                        mock_db_instance.close.assert_called_once()


# Integration test fixture
@pytest.fixture
def live_server_config(tmp_path):
    """Create a minimal configuration for a live server test."""
    # Create secret file
    secret_file = tmp_path / "db_secret.txt"
    secret_file.write_text("test_password_v1")
    
    # Create config files
    site_config = tmp_path / "mxcp-site.yml"
    site_config.write_text(f"""
mxcp: 1
project: test_reload
profile: default
profiles:
  default:
    duckdb:
      path: ":memory:"
      password: file://{secret_file}
""")
    
    user_config = tmp_path / "mxcp-config.yml"
    user_config.write_text("""
transport:
  provider: streamable-http
  http:
    host: localhost
    port: 18765
""")
    
    return {
        'config_dir': tmp_path,
        'secret_file': secret_file,
        'site_config': site_config,
        'user_config': user_config
    }


@pytest.mark.slow
@pytest.mark.skipif(not hasattr(signal, 'SIGHUP'), reason="SIGHUP not available on this platform")
class TestLiveServerReload:
    """Integration tests with a live server process (marked as slow)."""
    
    def test_live_server_sighup_reload(self, live_server_config):
        """Test sending SIGHUP to a live server process."""
        # This would require starting an actual server subprocess
        # and sending it signals - marked as slow and optional
        pytest.skip("Live server testing requires manual setup") 