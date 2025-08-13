"""Tests for the unified references module."""

import os
import tempfile
from pathlib import Path

import pytest

from mxcp.core.refs.resolver import (
    detect_reference_type,
    find_references,
    interpolate_all,
    is_external_reference,
    resolve_env_var,
    resolve_file_url,
    resolve_value,
    resolve_vault_url,
)


class TestReferenceDetection:
    """Test reference detection functions."""

    def test_is_external_reference(self):
        """Test detecting external references."""
        assert is_external_reference("vault://secret/db#password")
        assert is_external_reference("file:///etc/ssl/cert.pem")
        assert is_external_reference("${ENV_VAR}")
        assert is_external_reference("prefix ${ENV_VAR} suffix")

        assert not is_external_reference("plain string")
        assert not is_external_reference(123)
        assert not is_external_reference(["list"])
        assert not is_external_reference({"dict": "value"})

    def test_detect_reference_type(self):
        """Test detecting reference types."""
        assert detect_reference_type("vault://secret/db#password") == "vault"
        assert detect_reference_type("file:///etc/ssl/cert.pem") == "file"
        assert detect_reference_type("${ENV_VAR}") == "env"
        assert detect_reference_type("prefix ${ENV_VAR} suffix") == "env"
        assert detect_reference_type("plain string") is None


class TestResolution:
    """Test resolution functions."""

    def test_resolve_env_var(self):
        """Test resolving environment variables."""
        os.environ["TEST_VAR"] = "test_value"
        os.environ["VAR1"] = "hello"
        os.environ["VAR2"] = "world"

        assert resolve_env_var("${TEST_VAR}") == "test_value"
        assert resolve_env_var("${VAR1} ${VAR2}!") == "hello world!"
        assert resolve_env_var("no vars here") == "no vars here"

        with pytest.raises(ValueError, match="Environment variable MISSING is not set"):
            resolve_env_var("${MISSING}")

    def test_resolve_file_url(self, tmp_path):
        """Test resolving file URLs."""
        # Create test file
        test_file = tmp_path / "secret.txt"
        test_file.write_text("secret_content")

        # Absolute path
        assert resolve_file_url(f"file://{test_file}") == "secret_content"

        # Relative path
        rel_file = Path("test_rel.txt")
        rel_file.write_text("relative_content")
        try:
            assert resolve_file_url("file://test_rel.txt") == "relative_content"
        finally:
            rel_file.unlink()

        # Errors
        with pytest.raises(FileNotFoundError):
            resolve_file_url("file:///nonexistent.txt")

        with pytest.raises(ValueError, match="Invalid file URL format"):
            resolve_file_url("not a file url")

    def test_resolve_value(self):
        """Test the unified resolve_value function."""
        os.environ["TEST_VAR"] = "test_value"

        # Env var
        assert resolve_value("${TEST_VAR}") == "test_value"

        # File URL (would need actual file)
        with pytest.raises(FileNotFoundError):
            resolve_value("file:///nonexistent.txt")

        # Vault URL (would need vault config)
        with pytest.raises(ValueError, match="Vault URL .* found but Vault is not enabled"):
            resolve_value("vault://secret/db#password")


class TestInterpolation:
    """Test interpolation functions."""

    def test_interpolate_all(self):
        """Test recursive interpolation."""
        os.environ["DB_HOST"] = "localhost"
        os.environ["DB_PORT"] = "5432"

        config = {
            "database": {"host": "${DB_HOST}", "port": "${DB_PORT}", "ssl": True},
            "api": {"endpoints": ["${DB_HOST}:${DB_PORT}/api", "/health"]},
            "simple": "no interpolation",
        }

        result = interpolate_all(config)

        assert result["database"]["host"] == "localhost"
        assert result["database"]["port"] == "5432"
        assert result["database"]["ssl"] is True
        assert result["api"]["endpoints"][0] == "localhost:5432/api"
        assert result["api"]["endpoints"][1] == "/health"
        assert result["simple"] == "no interpolation"

    def test_find_references(self):
        """Test finding all references in a config."""
        config = {
            "database": {
                "host": "localhost",
                "password": "vault://secret/db#password",
                "ssl_cert": "file:///etc/ssl/cert.pem",
            },
            "api": {"key": "${API_KEY}", "endpoints": ["https://api.com", "${API_URL}"]},
            "features": ["feature1", "${FEATURE_FLAG}"],
        }

        refs = find_references(config)

        # Should find 5 references
        assert len(refs) == 5

        # Check structure of results
        paths = [ref[0] for ref in refs]
        values = [ref[1] for ref in refs]
        types = [ref[2] for ref in refs]

        # Vault reference
        vault_idx = values.index("vault://secret/db#password")
        assert paths[vault_idx] == ["database", "password"]
        assert types[vault_idx] == "vault"

        # File reference
        file_idx = values.index("file:///etc/ssl/cert.pem")
        assert paths[file_idx] == ["database", "ssl_cert"]
        assert types[file_idx] == "file"

        # Env references
        env_values = {"${API_KEY}", "${API_URL}", "${FEATURE_FLAG}"}
        env_refs = [(p, v, t) for p, v, t in refs if v in env_values]
        assert len(env_refs) == 3
        assert all(t == "env" for _, _, t in env_refs)
