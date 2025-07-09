import pytest
import os
import sys
from unittest.mock import patch, MagicMock
from mxcp.config.references import resolve_onepassword_url, interpolate_all, ONEPASSWORD_URL_PATTERN


class TestOnePasswordIntegration:
    """Test 1Password URL resolution functionality."""

    def test_onepassword_url_parsing(self):
        """Test that 1Password URLs are parsed correctly."""
        op_config = {
            'enabled': True,
            'token_env': 'OP_SERVICE_ACCOUNT_TOKEN'
        }
        
        # Mock the 1Password SDK
        with patch.dict(os.environ, {'OP_SERVICE_ACCOUNT_TOKEN': 'test-token'}):
            with patch('onepassword.Client') as mock_client_class:
                # Setup mock client
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                # Mock secrets.resolve
                mock_client.secrets.resolve.return_value = 'secret-value'
                
                # Test resolution
                result = resolve_onepassword_url('op://test-vault/test-item/password', op_config)
                
                assert result == 'secret-value'
                mock_client.secrets.resolve.assert_called_once_with('op://test-vault/test-item/password')

    def test_onepassword_url_otp_attribute(self):
        """Test OTP attribute resolution."""
        op_config = {
            'enabled': True,
            'token_env': 'OP_SERVICE_ACCOUNT_TOKEN'
        }
        
        with patch.dict(os.environ, {'OP_SERVICE_ACCOUNT_TOKEN': 'test-token'}):
            with patch('onepassword.Client') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                # Mock secrets.resolve for OTP
                mock_client.secrets.resolve.return_value = '123456'
                
                # Test OTP resolution
                result = resolve_onepassword_url('op://test-vault/test-item/otp?attribute=otp', op_config)
                
                assert result == '123456'
                mock_client.secrets.resolve.assert_called_once_with('op://test-vault/test-item/otp?attribute=totp')

    def test_onepassword_disabled(self):
        """Test that disabled 1Password raises appropriate error."""
        op_config = {'enabled': False}
        
        with pytest.raises(ValueError, match="1Password is not enabled"):
            resolve_onepassword_url('op://test-vault/test-item/password', op_config)

    def test_onepassword_url_pattern_validation(self):
        """Test URL pattern validation."""
        # Test valid patterns
        valid_urls = [
            'op://vault/item/field',
            'op://vault-name/item-name/field-name',
            'op://vault/item/field?attribute=otp',
            'op://my-vault/my-item/my-field?attribute=otp'
        ]
        
        for url in valid_urls:
            match = ONEPASSWORD_URL_PATTERN.match(url)
            assert match is not None, f"Valid URL should match: {url}"
        
        # Test invalid patterns
        invalid_urls = [
            'op://vault/item',  # Missing field
            'op://vault',       # Missing item and field
            'op://',            # Empty
            'vault://test',     # Wrong scheme
            'op://vault/item/field?invalid=param'  # Invalid attribute
        ]
        
        for url in invalid_urls:
            match = ONEPASSWORD_URL_PATTERN.match(url)
            assert match is None, f"Invalid URL should not match: {url}"

    def test_onepassword_missing_token(self):
        """Test error when token environment variable is missing."""
        op_config = {
            'enabled': True,
            'token_env': 'MISSING_TOKEN'
        }
        
        with pytest.raises(ValueError, match="1Password service account token not found"):
            resolve_onepassword_url('op://test-vault/test-item/password', op_config)

    def test_onepassword_sdk_error(self):
        """Test error handling when SDK raises an exception."""
        op_config = {
            'enabled': True,
            'token_env': 'OP_SERVICE_ACCOUNT_TOKEN'
        }
        
        with patch.dict(os.environ, {'OP_SERVICE_ACCOUNT_TOKEN': 'test-token'}):
            with patch('onepassword.Client') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                # Mock SDK raising an exception
                mock_client.secrets.resolve.side_effect = Exception("SDK error")
                
                with pytest.raises(ValueError, match="Failed to resolve 1Password URL"):
                    resolve_onepassword_url('op://test-vault/test-item/password', op_config)

    def test_onepassword_interpolation_in_config(self):
        """Test that 1Password URLs are interpolated in configuration."""
        config = {
            'database': {
                'host': 'localhost',
                'username': 'op://vault/db-creds/username',
                'password': 'op://vault/db-creds/password'
            },
            'api': {
                'key': 'op://vault/api-keys/production'
            }
        }
        
        op_config = {
            'enabled': True,
            'token_env': 'OP_SERVICE_ACCOUNT_TOKEN'
        }
        
        with patch.dict(os.environ, {'OP_SERVICE_ACCOUNT_TOKEN': 'test-token'}):
            with patch('onepassword.Client') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                # Mock different responses for different secret references
                def mock_resolve(secret_ref):
                    if secret_ref == 'op://vault/db-creds/username':
                        return 'db_user'
                    elif secret_ref == 'op://vault/db-creds/password':
                        return 'db_pass'
                    elif secret_ref == 'op://vault/api-keys/production':
                        return 'api_key_value'
                    else:
                        raise Exception(f"Unknown secret reference: {secret_ref}")
                
                mock_client.secrets.resolve.side_effect = mock_resolve
                
                # Test interpolation
                result = interpolate_all(config, vault_config=None, op_config=op_config)
                
                assert result['database']['username'] == 'db_user'
                assert result['database']['password'] == 'db_pass'
                assert result['api']['key'] == 'api_key_value'
                assert result['database']['host'] == 'localhost'  # Unchanged

    def test_onepassword_library_not_installed(self):
        """Test error when onepassword-sdk is not installed."""
        op_config = {
            'enabled': True,
            'token_env': 'OP_SERVICE_ACCOUNT_TOKEN'
        }
        
        # Provide the token so we get past the environment variable check
        with patch.dict(os.environ, {'OP_SERVICE_ACCOUNT_TOKEN': 'test-token'}):
            # Mock the import to raise ImportError
            original_import = __builtins__['__import__']
            def mock_import(name, *args, **kwargs):
                if name == 'onepassword':
                    raise ImportError("No module named 'onepassword'")
                return original_import(name, *args, **kwargs)
            
            with patch('builtins.__import__', side_effect=mock_import):
                with pytest.raises(ImportError, match="onepassword-sdk library is required"):
                    resolve_onepassword_url('op://test-vault/test-item/password', op_config) 