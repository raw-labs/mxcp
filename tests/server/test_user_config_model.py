"""Unit tests for UserConfigModel defaults and validators."""

from mxcp.server.core.config.models import UserConfigModel


def _base_user_config() -> dict:
    return {
        "mxcp": 1,
        "projects": {
            "demo": {
                "profiles": {
                    "default": {
                        "secrets": [],
                    }
                }
            }
        },
    }


def test_user_config_model_defaults():
    """Minimal configs should pick up sensible defaults."""
    model = UserConfigModel.model_validate(_base_user_config())

    assert model.transport.provider == "streamable-http"
    assert model.transport.http.port == 8000
    assert model.transport.http.host == "localhost"
    assert model.logging.enabled is True
    assert "demo" in model.projects
    assert "default" in model.projects["demo"].profiles
    profile = model.projects["demo"].profiles["default"]
    assert profile.secrets == []
    assert profile.plugin.config == {}
    assert profile.auth.provider == "none"


def test_user_auth_persistence_default(tmp_path):
    """Auth providers should automatically receive persistence defaults."""
    data = _base_user_config()
    data["projects"]["demo"]["profiles"]["default"]["auth"] = {"provider": "github"}

    model = UserConfigModel.model_validate(data)
    auth = model.projects["demo"].profiles["default"].auth
    assert auth.provider == "github"
    assert auth.persistence is not None
    assert auth.persistence.path.endswith("oauth.db")


def test_transport_overrides_respected():
    """Explicit transport overrides should be preserved."""
    data = _base_user_config()
    data["transport"] = {
        "provider": "sse",
        "http": {"host": "0.0.0.0", "port": 9000, "stateless": True},
    }

    model = UserConfigModel.model_validate(data)
    assert model.transport.provider == "sse"
    assert model.transport.http.host == "0.0.0.0"
    assert model.transport.http.port == 9000
    assert model.transport.http.stateless is True
