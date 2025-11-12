"""Tests for external configuration reference tracking and resolution."""

import contextlib
import os

import pytest

from mxcp.server.core.refs.external import ExternalRef, ExternalRefTracker


class TestExternalRef:
    """Test the ExternalRef class."""

    def test_resolve_env_var(self):
        """Test resolving environment variable references."""
        # Single env var
        os.environ["TEST_VAR"] = "test_value"
        ref = ExternalRef(["config", "key"], "${TEST_VAR}", "env")
        assert ref.resolve() == "test_value"

        # Multiple env vars in string
        os.environ["VAR1"] = "hello"
        os.environ["VAR2"] = "world"
        ref = ExternalRef(["config", "key"], "${VAR1} ${VAR2}!", "env")
        assert ref.resolve() == "hello world!"

        # Missing env var
        ref = ExternalRef(["config", "key"], "${MISSING_VAR}", "env")
        with pytest.raises(ValueError, match="Environment variable MISSING_VAR is not set"):
            ref.resolve()

    def test_resolve_file_url(self, tmp_path):
        """Test resolving file:// URLs."""
        # Create a test file
        test_file = tmp_path / "test_secret.txt"
        test_file.write_text("secret_value")

        # Absolute path
        ref = ExternalRef(["config", "key"], f"file://{test_file}", "file")
        assert ref.resolve() == "secret_value"

        # File doesn't exist
        ref = ExternalRef(["config", "key"], "file:///nonexistent/file.txt", "file")
        with pytest.raises(FileNotFoundError):
            ref.resolve()

    def test_error_tracking(self):
        """Test that errors are tracked in the ref."""
        ref = ExternalRef(["config", "key"], "${MISSING_VAR}", "env")

        assert ref.last_error is None

        with contextlib.suppress(ValueError):
            ref.resolve()

        assert ref.last_error is not None
        assert "MISSING_VAR" in ref.last_error


class TestExternalRefTracker:
    """Test the ExternalRefTracker class."""

    def test_scan_config(self):
        """Test scanning configuration for external references via set_template."""
        tracker = ExternalRefTracker()

        config = {
            "database": {
                "host": "localhost",
                "password": "vault://secret/db#password",
                "port": 5432,
                "ssl_cert": "file:///etc/ssl/cert.pem",
            },
            "api": {"key": "${API_KEY}", "url": "https://api.example.com"},
            "features": ["feature1", "${FEATURE_FLAG}"],
            "nested": {"deep": {"value": "file://config.json"}},
        }

        # Use set_template to scan the config
        tracker.set_template({}, config)  # Empty site config, test user config

        # Should find 5 external references
        assert len(tracker.refs) == 5

        # Check vault reference
        vault_refs = [r for r in tracker.refs if r.ref_type == "vault"]
        assert len(vault_refs) == 1
        assert vault_refs[0].source == "vault://secret/db#password"
        assert vault_refs[0].path == ["user", "database", "password"]  # Note: prepended with 'user'

        # Check file references
        file_refs = [r for r in tracker.refs if r.ref_type == "file"]
        assert len(file_refs) == 2
        file_paths = {r.source for r in file_refs}
        assert "file:///etc/ssl/cert.pem" in file_paths
        assert "file://config.json" in file_paths

        # Check env references
        env_refs = [r for r in tracker.refs if r.ref_type == "env"]
        assert len(env_refs) == 2
        env_sources = {r.source for r in env_refs}
        assert "${API_KEY}" in env_sources
        assert "${FEATURE_FLAG}" in env_sources

    def test_set_template_and_resolve(self):
        """Test setting template configs and resolving references."""
        tracker = ExternalRefTracker()

        # Set up test environment
        os.environ["TEST_USER"] = "testuser"
        os.environ["TEST_PASS"] = "testpass"

        site_config = {"project": "test_project", "profile": "default"}

        user_config = {
            "projects": {
                "test_project": {
                    "profiles": {
                        "default": {
                            "secrets": [
                                {
                                    "name": "db",
                                    "parameters": {
                                        "username": "${TEST_USER}",
                                        "password": "${TEST_PASS}",
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        }

        tracker.set_template(site_config, user_config)

        # Should find 2 references
        assert len(tracker.refs) == 2

        # Resolve all references
        resolved_site, resolved_user = tracker.resolve_all()

        # Site config should be unchanged
        assert resolved_site == site_config

        # User config should have resolved values
        profile = resolved_user["projects"]["test_project"]["profiles"]["default"]
        assert profile["secrets"][0]["parameters"]["username"] == "testuser"
        assert profile["secrets"][0]["parameters"]["password"] == "testpass"

    def test_resolve_with_vault_config(self):
        """Test that vault config is extracted from template if not provided."""
        tracker = ExternalRefTracker()

        user_config = {
            "vault": {"url": "http://vault:8200", "token": "test-token"},
            "projects": {"test": {"profiles": {"default": {"api_key": "${API_KEY}"}}}},
        }

        os.environ["API_KEY"] = "test-key"
        tracker.set_template({}, user_config)

        # Resolve without providing vault_config
        _, resolved_user = tracker.resolve_all()

        # Should still resolve env var
        assert resolved_user["projects"]["test"]["profiles"]["default"]["api_key"] == "test-key"
        # Vault config should be preserved
        assert resolved_user["vault"] == user_config["vault"]

    def test_resolution_errors(self):
        """Test handling of resolution errors."""
        tracker = ExternalRefTracker()

        config = {"var1": "${MISSING1}", "var2": "${MISSING2}", "var3": "file:///nonexistent.txt"}

        tracker.set_template({}, config)

        # Should raise with all errors
        with pytest.raises(ValueError) as exc:
            tracker.resolve_all()

        error_msg = str(exc.value)
        assert "MISSING1" in error_msg
        assert "MISSING2" in error_msg
        assert "nonexistent.txt" in error_msg
