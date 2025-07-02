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
        """Test reload_configuration when no values change - DuckDB is always reloaded."""
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
                
                # Mock the shutdown and init methods
                with patch.object(server, '_shutdown_runtime_components') as mock_shutdown:
                    with patch.object(server, '_init_python_runtime') as mock_init:
                        # Call reload
                        server.reload_configuration()
                        
                        # Shutdown SHOULD be called even when nothing changed (always reload DuckDB)
                        mock_shutdown.assert_called_once()
                        mock_init.assert_called_once()
    
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
    
    @patch('mxcp.config.user_config.load_user_config')
    @patch('mxcp.server.mcp.DuckDBSession')
    @patch('mxcp.server.mcp.EndpointLoader')
    @patch('mxcp.plugins.base.run_plugin_shutdown_hooks')
    def test_plugin_config_reload(self, mock_plugin_shutdown, mock_loader, mock_db, mock_load_user_config):
        """Test that plugins are reloaded when their config changes via external references."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with temp_working_directory(tmpdir):
                site_config_path = Path(tmpdir)
                
                # Set initial env var for plugin config
                os.environ['PLUGIN_API_KEY'] = 'initial_key'
                
                # Mock user config with plugin config using env reference
                mock_load_user_config.return_value = get_mock_user_config({
                    'plugin': {
                        'config': {
                            'test_plugin': {
                                'api_key': '${PLUGIN_API_KEY}',
                                'endpoint': 'https://api.example.com'
                            }
                        }
                    }
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
plugin:
  - name: test_plugin
    module: test_plugin_module
    config: test_plugin
""")
                (site_config_path / "mxcp-config.yml").write_text("""
transport:
  provider: streamable-http
""")
                
                # Mock DuckDB session
                mock_db_instance = MagicMock()
                mock_db_instance.plugins = {'test_plugin': MagicMock()}
                mock_db_instance.close = MagicMock()
                mock_db.return_value = mock_db_instance
                
                # Create server
                server = RAWMCP(site_config_path=site_config_path)
                
                # Verify initial plugin config
                plugin_cfg = server.user_config['projects']['test']['profiles']['default']['plugin']['config']['test_plugin']
                assert plugin_cfg['api_key'] == 'initial_key'
                
                # Change env var
                os.environ['PLUGIN_API_KEY'] = 'updated_key'
                
                # Call reload
                server.reload_configuration()
                
                # Verify plugin shutdown was called
                mock_plugin_shutdown.assert_called_once()
                
                # Verify new plugin config
                plugin_cfg = server.user_config['projects']['test']['profiles']['default']['plugin']['config']['test_plugin']
                assert plugin_cfg['api_key'] == 'updated_key'
                
                # Verify DB session was recreated (closed and new instance created)
                assert mock_db_instance.close.called
                assert mock_db.call_count >= 2  # Initial creation + reload
    
    @patch('mxcp.config.user_config.load_user_config')
    @patch('mxcp.server.mcp.DuckDBSession')
    @patch('mxcp.server.mcp.EndpointLoader')
    @patch('mxcp.runtime._run_shutdown_hooks')
    @patch('mxcp.plugins.base.run_plugin_shutdown_hooks')
    def test_end_to_end_reload_with_secrets_and_plugins(self, mock_plugin_shutdown, mock_py_shutdown, 
                                                        mock_loader, mock_db, mock_load_user_config):
        """Test end-to-end reload with Python endpoints using secrets and plugins using config."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with temp_working_directory(tmpdir):
                site_config_path = Path(tmpdir)
                
                # Create files for external references
                secret_file = Path(tmpdir) / "api_secret.txt"
                secret_file.write_text("initial_secret_value")
                
                # Set env vars
                os.environ['PLUGIN_TIMEOUT'] = '30'
                os.environ['ENDPOINT_FEATURE'] = 'feature_v1'
                
                # Mock user config with both secrets and plugin config
                mock_load_user_config.return_value = get_mock_user_config({
                    'secrets': [
                        {
                            'name': 'custom_api',
                            'type': 'custom',  # Non-DuckDB type
                            'parameters': {
                                'api_key': f'file://{secret_file}',
                                'feature_flag': '${ENDPOINT_FEATURE}'
                            }
                        }
                    ],
                    'plugin': {
                        'config': {
                            'api_plugin': {
                                'timeout': '${PLUGIN_TIMEOUT}',
                                'base_url': 'https://api.example.com'
                            }
                        }
                    }
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
secrets:
  - custom_api
plugin:
  - name: api_plugin
    module: api_plugin_module
    config: api_plugin
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
                
                # Verify initial values
                secrets = server.user_config['projects']['test']['profiles']['default']['secrets']
                secret_params = next(s['parameters'] for s in secrets if s['name'] == 'custom_api')
                assert secret_params['api_key'] == 'initial_secret_value'
                assert secret_params['feature_flag'] == 'feature_v1'
                
                plugin_cfg = server.user_config['projects']['test']['profiles']['default']['plugin']['config']['api_plugin']
                assert plugin_cfg['timeout'] == '30'
                
                # Change all external values
                secret_file.write_text("updated_secret_value")
                os.environ['PLUGIN_TIMEOUT'] = '60'
                os.environ['ENDPOINT_FEATURE'] = 'feature_v2'
                
                # Call reload
                server.reload_configuration()
                
                # Verify both shutdown hooks were called
                mock_py_shutdown.assert_called_once()
                mock_plugin_shutdown.assert_called_once()
                
                # Verify all values were updated
                secrets = server.user_config['projects']['test']['profiles']['default']['secrets']
                secret_params = next(s['parameters'] for s in secrets if s['name'] == 'custom_api')
                assert secret_params['api_key'] == 'updated_secret_value'
                assert secret_params['feature_flag'] == 'feature_v2'
                
                plugin_cfg = server.user_config['projects']['test']['profiles']['default']['plugin']['config']['api_plugin']
                assert plugin_cfg['timeout'] == '60'
    
    @patch('mxcp.config.user_config.load_user_config')
    @patch('mxcp.server.mcp.DuckDBSession')
    @patch('mxcp.server.mcp.EndpointLoader')
    @patch('mxcp.runtime._run_shutdown_hooks')
    def test_python_endpoint_with_non_duckdb_secrets_reload(self, mock_py_shutdown, mock_loader, mock_db, mock_load_user_config):
        """Test that Python endpoints can access non-DuckDB secret types after reload."""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with temp_working_directory(tmpdir):
                site_config_path = Path(tmpdir)
                
                # Create files for external references
                secret_file = Path(tmpdir) / "api_secret.txt"
                secret_file.write_text("initial_api_key")
                
                # Set env var
                os.environ['CUSTOM_SECRET_TYPE'] = 'python'
                
                # Mock user config with non-DuckDB secret types
                mock_load_user_config.return_value = get_mock_user_config({
                    'secrets': [
                        {
                            'name': 'custom_secret',
                            'type': 'custom',  # Non-DuckDB type
                            'parameters': {
                                'api_key': f'file://{secret_file}',
                                'endpoint': 'https://api.example.com'
                            }
                        },
                        {
                            'name': 'python_secret',
                            'type': '${CUSTOM_SECRET_TYPE}',  # Dynamic non-DuckDB type
                            'parameters': {
                                'value': 'python-only-secret',
                                'config': {
                                    'nested': 'value'
                                }
                            }
                        }
                    ]
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
secrets:
  - custom_secret
  - python_secret
""")
                (site_config_path / "mxcp-config.yml").write_text("""
transport:
  provider: streamable-http
""")
                
                # Mock DuckDB session
                mock_db_instance = MagicMock()
                mock_db_instance.close = MagicMock()
                mock_db.return_value = mock_db_instance
                
                # Create server
                server = RAWMCP(site_config_path=site_config_path)
                
                # Verify initial secret values
                secrets = server.user_config['projects']['test']['profiles']['default']['secrets']
                custom_secret = next(s for s in secrets if s['name'] == 'custom_secret')
                python_secret = next(s for s in secrets if s['name'] == 'python_secret')
                
                assert custom_secret['type'] == 'custom'
                assert custom_secret['parameters']['api_key'] == 'initial_api_key'
                assert python_secret['type'] == 'python'
                
                # Change external values
                secret_file.write_text('updated_api_key')
                os.environ['CUSTOM_SECRET_TYPE'] = 'python_v2'
                
                # Call reload
                server.reload_configuration()
                
                # Verify Python shutdown hooks were called
                mock_py_shutdown.assert_called_once()
                
                # Verify new secret values
                secrets = server.user_config['projects']['test']['profiles']['default']['secrets']
                custom_secret = next(s for s in secrets if s['name'] == 'custom_secret')
                python_secret = next(s for s in secrets if s['name'] == 'python_secret')
                
                assert custom_secret['parameters']['api_key'] == 'updated_api_key'
                assert python_secret['type'] == 'python_v2'  # Type changed via env var
                
                # Verify DB session was recreated
                assert mock_db_instance.close.called
                assert mock_db.call_count >= 2
    
    def teardown_method(self):
        """Clean up environment variables after each test."""
        # Clean up any test env vars
        for var in ['TEST_DB_PASSWORD', 'TEST_ERROR_VAR', 'PLUGIN_API_KEY', 'PLUGIN_TIMEOUT', 'ENDPOINT_FEATURE', 'CUSTOM_SECRET_TYPE']:
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