"""
Tests for mxcp.core.config module.

This module tests the new plugin-based configuration architecture including:
- ResolverEngine functionality
- Individual resolver plugins
- Reference resolution and tracking
- Configuration loading and validation
- Integration scenarios
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# Import all the new architecture components
from mxcp.sdk.core.config import (
    EnvResolver,
    FileResolver,
    OnePasswordResolver,
    ResolverEngine,
    ResolverPlugin,
    ResolverRegistry,
    VaultResolver,
    load_resolver_config,
)


class TestResolverEngine:
    """Test the main ResolverEngine functionality."""

    def test_engine_initialization(self):
        """Test creating a ResolverEngine with default config."""
        engine = ResolverEngine()
        assert engine.resolver_config is not None
        assert isinstance(engine.registry, ResolverRegistry)
        assert len(engine.list_resolvers()) >= 2  # At least env and file

    def test_engine_from_dict(self):
        """Test creating ResolverEngine from dictionary config."""
        config = {
            "config": {
                "vault": {
                    "enabled": True,
                    "address": "https://vault.example.com",
                    "token_env": "VAULT_TOKEN",
                }
            }
        }

        # Without the token, vault won't be registered
        engine = ResolverEngine.from_dict(config)
        resolvers = engine.list_resolvers()
        assert "env" in resolvers
        assert "file" in resolvers

    def test_engine_context_manager(self):
        """Test ResolverEngine as context manager."""
        config = {"config": {}}

        with ResolverEngine.from_dict(config) as engine:
            assert len(engine.list_resolvers()) >= 2

        # Should not raise any exceptions on cleanup

    def test_engine_cleanup(self):
        """Test explicit cleanup functionality."""
        engine = ResolverEngine()
        engine.cleanup()  # Should not raise exceptions

    def test_register_custom_resolver(self):
        """Test registering a custom resolver."""
        engine = ResolverEngine()

        # Create a simple test resolver
        class TestResolver(ResolverPlugin):
            @property
            def name(self) -> str:
                return "test"

            @property
            def url_patterns(self) -> list:
                return [r"test://.*"]

            def can_resolve(self, reference: str) -> bool:
                return reference.startswith("test://")

            def resolve(self, reference: str) -> str:
                return "test_value"

        test_resolver = TestResolver()
        engine.register_resolver(test_resolver)

        assert "test" in engine.list_resolvers()
        assert engine.registry.find_resolver_for_reference("test://example") is not None


class TestBuiltinResolvers:
    """Test the built-in resolver implementations."""

    def test_env_resolver(self):
        """Test environment variable resolver."""
        resolver = EnvResolver()

        assert resolver.name == "env"
        assert resolver.can_resolve("${TEST_VAR}")
        assert not resolver.can_resolve("not_a_var")

        # Test resolution with actual env var
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = resolver.resolve("${TEST_VAR}")
            assert result == "test_value"

        # Test missing env var
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Environment variable not found"):
                resolver.resolve("${MISSING_VAR}")

    def test_file_resolver(self):
        """Test file resolver."""
        resolver = FileResolver()

        assert resolver.name == "file"
        assert resolver.can_resolve("file:///path/to/file")
        assert not resolver.can_resolve("not_a_file")

        # Test resolution with actual file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test_content")
            f.flush()

            result = resolver.resolve(f"file://{f.name}")
            assert result == "test_content"

            os.unlink(f.name)

        # Test missing file
        with pytest.raises(FileNotFoundError):
            resolver.resolve("file:///nonexistent/file")

    def test_vault_resolver_validation(self):
        """Test Vault resolver configuration validation."""
        # Test without configuration
        resolver = VaultResolver()
        assert not resolver.validate_config()

        # Test with disabled config
        resolver = VaultResolver({"enabled": False})
        assert not resolver.validate_config()

        # Test with invalid config (no address)
        resolver = VaultResolver({"enabled": True})
        assert not resolver.validate_config()

    def test_onepassword_resolver_validation(self):
        """Test OnePassword resolver configuration validation."""
        # Test without configuration
        resolver = OnePasswordResolver()
        assert not resolver.validate_config()

        # Test with disabled config
        resolver = OnePasswordResolver({"enabled": False})
        assert not resolver.validate_config()

        # Test with missing token
        resolver = OnePasswordResolver({"enabled": True})
        assert not resolver.validate_config()


class TestReferenceResolution:
    """Test reference resolution and tracking."""

    def test_env_reference_resolution(self):
        """Test resolving environment variable references."""
        engine = ResolverEngine()

        config = {"database": {"host": "${DB_HOST}", "port": 5432, "name": "mydb"}}

        with patch.dict(os.environ, {"DB_HOST": "localhost"}):
            resolved = engine.process_config(config)

            assert resolved["database"]["host"] == "localhost"
            assert resolved["database"]["port"] == 5432
            assert resolved["database"]["name"] == "mydb"

    def test_file_reference_resolution(self):
        """Test resolving file references."""
        engine = ResolverEngine()

        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("secret_password")
            f.flush()

            config = {"database": {"password": f"file://{f.name}"}}

            resolved = engine.process_config(config)
            assert resolved["database"]["password"] == "secret_password"

            os.unlink(f.name)

    def test_mixed_reference_types(self):
        """Test resolving mixed reference types."""
        engine = ResolverEngine()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("file_secret")
            f.flush()

            config = {
                "app": {
                    "env_var": "${APP_NAME}",
                    "file_secret": f"file://{f.name}",
                    "static_value": "unchanged",
                }
            }

            with patch.dict(os.environ, {"APP_NAME": "myapp"}):
                resolved = engine.process_config(config)

                assert resolved["app"]["env_var"] == "myapp"
                assert resolved["app"]["file_secret"] == "file_secret"
                assert resolved["app"]["static_value"] == "unchanged"

            os.unlink(f.name)

    def test_reference_tracking(self):
        """Test reference tracking functionality."""
        engine = ResolverEngine()

        config = {"database": {"host": "${DB_HOST}", "port": 5432}}

        with patch.dict(os.environ, {"DB_HOST": "localhost"}):
            engine.process_config(config, track_references=True)

            references = engine.get_resolved_references()
            assert len(references) == 1

            ref = references[0]
            assert ref.path == ["database", "host"]
            assert ref.original_value == "${DB_HOST}"
            assert ref.resolved_value == "localhost"
            assert ref.resolver_name == "env"
            assert ref.error is None

    def test_failed_reference_tracking(self):
        """Test tracking of failed references."""
        engine = ResolverEngine()

        config = {"database": {"host": "${MISSING_VAR}"}}

        with patch.dict(os.environ, {}, clear=True):
            # Should not raise exception, just track the failure
            resolved = engine.process_config(config, track_references=True)

            # Value should remain unchanged
            assert resolved["database"]["host"] == "${MISSING_VAR}"

            # Should have tracked the failure
            failed_refs = engine.get_failed_references()
            assert len(failed_refs) == 1

            failed_ref = failed_refs[0]
            assert failed_ref.path == ["database", "host"]
            assert failed_ref.original_value == "${MISSING_VAR}"
            assert failed_ref.error is not None

    def test_reference_summary(self):
        """Test reference summary functionality."""
        engine = ResolverEngine()

        config = {"good_var": "${GOOD_VAR}", "bad_var": "${BAD_VAR}"}

        with patch.dict(os.environ, {"GOOD_VAR": "good_value"}):
            engine.process_config(config, track_references=True)

            summary = engine.get_reference_summary()

            assert summary["total_references"] == 2
            assert summary["successful_references"] == 1
            assert summary["failed_references"] == 1
            assert "env" in summary["by_resolver_type"]
            assert "env" in summary["registered_resolvers"]


class TestConfigurationLoading:
    """Test configuration loading functionality."""

    def test_load_empty_config(self):
        """Test loading empty configuration."""
        config = load_resolver_config(None)
        assert config is not None
        # Config is now a Pydantic model, not a dict
        assert hasattr(config, "vault")
        assert hasattr(config, "onepassword")

    def test_load_config_from_file(self):
        """Test loading configuration from file."""
        config_data = {
            "config": {"vault": {"enabled": True, "address": "https://vault.example.com"}}
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            f.flush()

            config = load_resolver_config(Path(f.name))
            # Config is now a Pydantic model with attribute access
            assert config.vault is not None
            assert config.vault.enabled is True
            assert config.vault.address == "https://vault.example.com"

            os.unlink(f.name)


class TestEndToEndScenarios:
    """Test complete end-to-end scenarios."""

    def test_complete_workflow(self):
        """Test a complete configuration workflow."""
        # Create a complex configuration
        config = {
            "database": {"host": "${DB_HOST}", "port": 5432, "name": "myapp"},
            "api": {"keys": ["${API_KEY}", "static_key"], "timeout": 30},
        }

        with patch.dict(os.environ, {"DB_HOST": "localhost", "API_KEY": "secret123"}):
            # Use context manager for proper cleanup
            with ResolverEngine() as engine:
                resolved = engine.process_config(config, track_references=True)

                # Verify resolution
                assert resolved["database"]["host"] == "localhost"
                assert resolved["database"]["port"] == 5432
                assert resolved["api"]["keys"] == ["secret123", "static_key"]
                assert resolved["api"]["timeout"] == 30

                # Verify tracking
                references = engine.get_resolved_references()
                assert len(references) == 2

                env_refs = engine.get_references_by_type("env")
                assert len(env_refs) == 2

                summary = engine.get_reference_summary()
                assert summary["total_references"] == 2
                assert summary["successful_references"] == 2
                assert summary["failed_references"] == 0

    def test_production_like_config(self):
        """Test a production-like configuration scenario."""
        resolver_config = {
            "config": {
                "vault": {
                    "enabled": True,
                    "address": "https://vault.example.com",
                    "token_env": "VAULT_TOKEN",
                },
                "onepassword": {"enabled": True, "token_env": "OP_SERVICE_ACCOUNT_TOKEN"},
            }
        }

        app_config = {
            "database": {
                "host": "${DB_HOST}",
                "username": "app_user",
                "password": "vault://secret/db#password",
            },
            "api": {"key": "op://vault/api/key", "timeout": 30},
        }

        with patch.dict(
            os.environ,
            {
                "DB_HOST": "prod-db.example.com",
                "VAULT_TOKEN": "vault-token",
                "OP_SERVICE_ACCOUNT_TOKEN": "op-token",
            },
        ):
            # Create engine with configuration
            engine = ResolverEngine.from_dict(resolver_config)

            # Verify resolvers are registered
            resolvers = engine.list_resolvers()
            assert "env" in resolvers
            assert "file" in resolvers

            # Process config (vault and op will fail without real services, but env should work)
            resolved = engine.process_config(app_config, track_references=True)

            # Environment variable should be resolved
            assert resolved["database"]["host"] == "prod-db.example.com"
            assert resolved["database"]["username"] == "app_user"

            # Check that references were tracked
            references = engine.get_resolved_references()
            env_refs = [r for r in references if r.resolver_name == "env"]
            assert len(env_refs) == 1

            summary = engine.get_reference_summary()
            assert summary["total_references"] >= 1  # At least the env var


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
