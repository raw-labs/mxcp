import os
from unittest.mock import MagicMock, patch

import pytest

from mxcp.config.references import interpolate_all, resolve_vault_url


class TestVaultIntegration:
    """Test Vault URL resolution functionality."""

    def test_vault_url_parsing(self):
        """Test that vault URLs are parsed correctly."""
        vault_config = {
            "enabled": True,
            "address": "https://vault.example.com",
            "token_env": "VAULT_TOKEN",
        }

        # Mock hvac and environment
        with patch.dict(os.environ, {"VAULT_TOKEN": "test-token"}):
            with patch("hvac.Client") as mock_hvac_client:
                # Setup mock client
                mock_client = MagicMock()
                mock_client.is_authenticated.return_value = True
                mock_client.secrets.kv.v2.read_secret_version.return_value = {
                    "data": {"data": {"username": "test_user", "password": "test_pass"}}
                }
                mock_hvac_client.return_value = mock_client

                # Test successful resolution
                result = resolve_vault_url("vault://secret/database#username", vault_config)
                assert result == "test_user"

                # Verify client was configured correctly
                mock_hvac_client.assert_called_with(
                    url="https://vault.example.com", token="test-token"
                )

    def test_vault_url_invalid_format(self):
        """Test that invalid vault URLs raise appropriate errors."""
        vault_config = {"enabled": True, "address": "https://vault.example.com"}

        # Test missing key
        with pytest.raises(ValueError, match="must specify a key after '#'"):
            resolve_vault_url("vault://secret/database", vault_config)

        # Test invalid format
        with pytest.raises(ValueError, match="Invalid vault URL format"):
            resolve_vault_url("invalid://url", vault_config)

    def test_vault_disabled(self):
        """Test that vault URLs fail when vault is disabled."""
        vault_config = {"enabled": False}

        with pytest.raises(ValueError, match="Vault is not enabled"):
            resolve_vault_url("vault://secret/test#key", vault_config)

    def test_vault_missing_config(self):
        """Test that vault URLs fail when vault config is missing."""
        with pytest.raises(ValueError, match="Vault is not enabled"):
            resolve_vault_url("vault://secret/test#key", None)

    def test_vault_missing_token(self):
        """Test that vault URLs fail when token is missing."""
        vault_config = {
            "enabled": True,
            "address": "https://vault.example.com",
            "token_env": "VAULT_TOKEN",
        }

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Vault token not found"):
                resolve_vault_url("vault://secret/test#key", vault_config)

    def test_vault_hvac_not_installed(self):
        """Test that appropriate error is raised when hvac is not installed."""
        vault_config = {
            "enabled": True,
            "address": "https://vault.example.com",
            "token_env": "VAULT_TOKEN",
        }

        with patch.dict(os.environ, {"VAULT_TOKEN": "test-token"}):
            # Mock the import to raise ImportError
            def mock_import(name, *args, **kwargs):
                if name == "hvac":
                    raise ImportError("No module named 'hvac'")
                return __import__(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                with pytest.raises(ImportError, match="hvac library is required"):
                    resolve_vault_url("vault://secret/test#key", vault_config)

    def test_vault_kv_v1_fallback(self):
        """Test that KV v1 is used as fallback when v2 fails."""
        vault_config = {
            "enabled": True,
            "address": "https://vault.example.com",
            "token_env": "VAULT_TOKEN",
        }

        with patch.dict(os.environ, {"VAULT_TOKEN": "test-token"}):
            with patch("hvac.Client") as mock_hvac_client:
                # Setup mock client
                mock_client = MagicMock()
                mock_client.is_authenticated.return_value = True

                # Make v2 fail, v1 succeed
                mock_client.secrets.kv.v2.read_secret_version.side_effect = Exception(
                    "v2 not available"
                )
                mock_client.secrets.kv.v1.read_secret.return_value = {
                    "data": {"username": "test_user_v1"}
                }
                mock_hvac_client.return_value = mock_client

                result = resolve_vault_url("vault://secret/database#username", vault_config)
                assert result == "test_user_v1"

    def test_interpolate_values_with_vault(self):
        """Test that _interpolate_values handles vault URLs correctly."""
        vault_config = {
            "enabled": True,
            "address": "https://vault.example.com",
            "token_env": "VAULT_TOKEN",
        }

        config = {
            "database": {
                "username": "vault://secret/db#username",
                "password": "vault://secret/db#password",
                "host": "localhost",
            }
        }

        with patch.dict(os.environ, {"VAULT_TOKEN": "test-token"}):
            with patch("hvac.Client") as mock_hvac_client:
                # Setup mock client
                mock_client = MagicMock()
                mock_client.is_authenticated.return_value = True
                mock_client.secrets.kv.v2.read_secret_version.return_value = {
                    "data": {"data": {"username": "db_user", "password": "db_pass"}}
                }
                mock_hvac_client.return_value = mock_client

                result = interpolate_all(config, vault_config)

                assert result["database"]["username"] == "db_user"
                assert result["database"]["password"] == "db_pass"
                assert result["database"]["host"] == "localhost"

    def test_mixed_interpolation(self):
        """Test that both env vars and vault URLs work together."""
        vault_config = {
            "enabled": True,
            "address": "https://vault.example.com",
            "token_env": "VAULT_TOKEN",
        }

        config = {
            "database": {
                "username": "vault://secret/db#username",
                "host": "${DB_HOST}",
                "port": 5432,
            }
        }

        with patch.dict(os.environ, {"VAULT_TOKEN": "test-token", "DB_HOST": "db.example.com"}):
            with patch("hvac.Client") as mock_hvac_client:
                # Setup mock client
                mock_client = MagicMock()
                mock_client.is_authenticated.return_value = True
                mock_client.secrets.kv.v2.read_secret_version.return_value = {
                    "data": {"data": {"username": "db_user"}}
                }
                mock_hvac_client.return_value = mock_client

                result = interpolate_all(config, vault_config)

                assert result["database"]["username"] == "db_user"
                assert result["database"]["host"] == "db.example.com"
                assert result["database"]["port"] == 5432

    def test_vault_authentication_failure(self):
        """Test that authentication failure is handled properly."""
        vault_config = {
            "enabled": True,
            "address": "https://vault.example.com",
            "token_env": "VAULT_TOKEN",
        }

        with patch.dict(os.environ, {"VAULT_TOKEN": "invalid-token"}):
            with patch("hvac.Client") as mock_hvac_client:
                # Setup mock client that fails authentication
                mock_client = MagicMock()
                mock_client.is_authenticated.return_value = False
                mock_hvac_client.return_value = mock_client

                with pytest.raises(ValueError, match="Failed to authenticate with Vault"):
                    resolve_vault_url("vault://secret/test#key", vault_config)

    def test_vault_secret_not_found(self):
        """Test that missing secrets are handled properly."""
        vault_config = {
            "enabled": True,
            "address": "https://vault.example.com",
            "token_env": "VAULT_TOKEN",
        }

        with patch.dict(os.environ, {"VAULT_TOKEN": "test-token"}):
            with patch("hvac.Client") as mock_hvac_client:
                # Setup mock client
                mock_client = MagicMock()
                mock_client.is_authenticated.return_value = True
                mock_client.secrets.kv.v2.read_secret_version.return_value = {
                    "data": {"data": {"other_key": "other_value"}}
                }
                mock_hvac_client.return_value = mock_client

                with pytest.raises(ValueError, match="Key 'missing_key' not found in Vault secret"):
                    resolve_vault_url("vault://secret/test#missing_key", vault_config)
