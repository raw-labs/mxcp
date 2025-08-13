"""Integration tests for file:// URL functionality and hot reload."""

import json
import os
import signal
import tempfile
import time
from pathlib import Path

import pytest

from mxcp.core.refs.external import ExternalRefTracker
from mxcp.core.refs.resolver import interpolate_all, resolve_file_url


class TestFileURLIntegration:
    """Integration tests for file:// URL resolution."""

    def test_file_url_with_real_files(self, tmp_path):
        """Test file:// URLs with actual files on disk."""
        # Create credential files
        db_password_file = tmp_path / "db_password.txt"
        db_password_file.write_text("supersecret123")

        api_key_file = tmp_path / "api_key.json"
        api_key_file.write_text(json.dumps({"key": "abc-123-def"}))

        # Test simple text file
        result = resolve_file_url(f"file://{db_password_file}")
        assert result == "supersecret123"

        # Test JSON file (still returns as string)
        result = resolve_file_url(f"file://{api_key_file}")
        assert result == '{"key": "abc-123-def"}'

    def test_file_url_whitespace_handling(self, tmp_path):
        """Test that whitespace is properly stripped from files."""
        # File with trailing newline (common in Unix)
        file_with_newline = tmp_path / "with_newline.txt"
        file_with_newline.write_text("secret_value\n")

        result = resolve_file_url(f"file://{file_with_newline}")
        assert result == "secret_value"

        # File with spaces and tabs
        file_with_spaces = tmp_path / "with_spaces.txt"
        file_with_spaces.write_text("  \t secret_value \t  \n")

        result = resolve_file_url(f"file://{file_with_spaces}")
        assert result == "secret_value"

    def test_file_url_permissions(self, tmp_path):
        """Test file:// URL behavior with different file permissions."""
        # Create a file
        restricted_file = tmp_path / "restricted.txt"
        restricted_file.write_text("restricted_content")

        # Make it unreadable (Unix only)
        if os.name != "nt":  # Skip on Windows
            os.chmod(restricted_file, 0o000)

            with pytest.raises(ValueError, match="Permission denied"):
                resolve_file_url(f"file://{restricted_file}")

            # Restore permissions for cleanup
            os.chmod(restricted_file, 0o644)

    def test_file_url_symlinks(self, tmp_path):
        """Test file:// URLs with symbolic links."""
        # Create actual file
        actual_file = tmp_path / "actual.txt"
        actual_file.write_text("actual_content")

        # Create symlink
        symlink = tmp_path / "link.txt"
        try:
            symlink.symlink_to(actual_file)

            # Should follow symlink
            result = resolve_file_url(f"file://{symlink}")
            assert result == "actual_content"
        except OSError:
            # Symlinks might not be available on all systems
            pytest.skip("Symlinks not supported on this system")

    def test_interpolate_with_files(self, tmp_path):
        """Test interpolation with mixed file:// and env references."""
        # Create files
        db_pass_file = tmp_path / "db_pass.txt"
        db_pass_file.write_text("db_secret_123")

        ssl_cert_file = tmp_path / "cert.pem"
        ssl_cert_file.write_text("-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----")

        # Set env var
        os.environ["DB_HOST"] = "postgres.example.com"

        config = {
            "database": {
                "host": "${DB_HOST}",
                "password": f"file://{db_pass_file}",
                "ssl": {"enabled": True, "cert": f"file://{ssl_cert_file}"},
            }
        }

        result = interpolate_all(config)

        assert result["database"]["host"] == "postgres.example.com"
        assert result["database"]["password"] == "db_secret_123"
        assert result["database"]["ssl"]["cert"].startswith("-----BEGIN CERTIFICATE-----")


class TestFileHotReload:
    """Test hot reload functionality with file changes."""

    def test_external_ref_tracker_file_changes(self, tmp_path):
        """Test that ExternalRefTracker detects file content changes."""
        # Create initial file
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("initial_secret")

        # Create configs - put file reference in user config since that's what ExternalRefTracker scans
        site_config = {"project": "test", "profile": "default", "profiles": {"default": {}}}

        user_config = {
            "transport": {"provider": "streamable-http"},
            "database": {"password": f"file://{secret_file}"},
        }

        # Initialize tracker
        tracker = ExternalRefTracker()
        tracker.set_template(site_config, user_config)

        # First resolution
        resolved_site, resolved_user = tracker.resolve_all()
        assert resolved_user["database"]["password"] == "initial_secret"

        # Change file content
        secret_file.write_text("updated_secret")

        # Re-resolve should pick up new value
        resolved_site2, resolved_user2 = tracker.resolve_all()
        assert resolved_user2["database"]["password"] == "updated_secret"

    def test_mixed_external_refs_reload(self, tmp_path):
        """Test reloading with mixed file://, env, and static values."""
        # Create files
        api_key_file = tmp_path / "api_key.txt"
        api_key_file.write_text("key_v1")

        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("cert_v1")

        # Set env vars
        os.environ["SERVICE_PORT"] = "8080"

        # Put config in user_config since that's what ExternalRefTracker scans
        site_config = {"project": "test", "profile": "default", "profiles": {"default": {}}}

        user_config = {
            "api": {
                "key": f"file://{api_key_file}",
                "port": "${SERVICE_PORT}",
                "host": "api.example.com",  # Static value
                "ssl_cert": f"file://{cert_file}",
            }
        }

        tracker = ExternalRefTracker()
        tracker.set_template(site_config, user_config)

        # Initial resolution
        resolved_site, resolved_user = tracker.resolve_all()
        assert resolved_user["api"]["key"] == "key_v1"
        assert resolved_user["api"]["port"] == "8080"
        assert resolved_user["api"]["host"] == "api.example.com"
        assert resolved_user["api"]["ssl_cert"] == "cert_v1"

        # Update files and env
        api_key_file.write_text("key_v2")
        cert_file.write_text("cert_v2")
        os.environ["SERVICE_PORT"] = "9090"

        # Re-resolve
        resolved_site2, resolved_user2 = tracker.resolve_all()
        assert resolved_user2["api"]["key"] == "key_v2"
        assert resolved_user2["api"]["port"] == "9090"
        assert resolved_user2["api"]["host"] == "api.example.com"  # Static unchanged
        assert resolved_user2["api"]["ssl_cert"] == "cert_v2"

    def test_file_deletion_handling(self, tmp_path):
        """Test behavior when referenced file is deleted."""
        # Create file
        temp_file = tmp_path / "temp.txt"
        temp_file.write_text("temporary")

        config = {"value": f"file://{temp_file}"}

        # First resolution should work
        result = interpolate_all(config)
        assert result["value"] == "temporary"

        # Delete file
        temp_file.unlink()

        # Resolution should fail gracefully
        with pytest.raises(FileNotFoundError):
            interpolate_all(config)


@pytest.mark.slow
class TestFileMonitoringAlternatives:
    """Test alternative approaches to file monitoring."""

    def test_file_mtime_tracking(self, tmp_path):
        """Demo how we could track file modification times if needed."""
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("v1")

        # Track initial mtime
        initial_mtime = secret_file.stat().st_mtime

        # Small delay to ensure mtime changes
        time.sleep(0.01)

        # Update file
        secret_file.write_text("v2")
        new_mtime = secret_file.stat().st_mtime

        # mtime should have changed
        assert new_mtime > initial_mtime

        # This demonstrates we COULD implement polling-based reload
        # but signal-based is cleaner


# Fixtures for integration testing
@pytest.fixture
def credential_files(tmp_path):
    """Create a set of credential files for testing."""
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()

    files = {
        "db_password": creds_dir / "db_password.txt",
        "api_key": creds_dir / "api_key.txt",
        "ssl_cert": creds_dir / "server.crt",
        "ssl_key": creds_dir / "server.key",
    }

    # Write test content
    files["db_password"].write_text("test_db_pass_123")
    files["api_key"].write_text("sk-1234567890abcdef")
    files["ssl_cert"].write_text(
        "-----BEGIN CERTIFICATE-----\ntest_cert\n-----END CERTIFICATE-----"
    )
    files["ssl_key"].write_text("-----BEGIN PRIVATE KEY-----\ntest_key\n-----END PRIVATE KEY-----")

    return files
