from __future__ import annotations

from typing import Any

import pytest
import respx

from mxcp.sdk.auth.models import OIDCVerifierAuthConfigModel
from mxcp.sdk.auth.verifier import OIDCTokenVerifier


CONFIG_URL = "http://oidc.test/.well-known/openid-configuration"


def _discovery_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "issuer": "http://oidc.test",
        "authorization_endpoint": "http://oidc.test/authorize",
        "token_endpoint": "http://oidc.test/token",
    }
    payload.update(overrides)
    return payload


def _make_verifier() -> OIDCTokenVerifier:
    return OIDCTokenVerifier(
        OIDCVerifierAuthConfigModel(
            config_url=CONFIG_URL,
            client_id="client-id",
            client_secret="client-secret",
            scope="openid",
        )
    )


@respx.mock
@pytest.mark.asyncio
async def test_oidc_verifier_jwt_path(monkeypatch: pytest.MonkeyPatch) -> None:
    discovery = respx.get(CONFIG_URL).respond(
        200, json=_discovery_payload(jwks_uri="http://oidc.test/jwks")
    )

    async def _fake_verify(self: OIDCTokenVerifier, token: str) -> dict[str, Any] | None:
        return {
            "sub": "user-1",
            "scope": "openid profile",
            "client_id": "client-1",
            "exp": 123,
        }

    monkeypatch.setattr(OIDCTokenVerifier, "_verify_jwt", _fake_verify, raising=True)

    verifier = _make_verifier()
    access = await verifier.verify_token("a.b.c")

    assert discovery.called
    assert access is not None
    assert access.client_id == "client-1"
    assert access.scopes == ["openid", "profile"]
    assert access.expires_at == 123


@respx.mock
@pytest.mark.asyncio
async def test_oidc_verifier_falls_back_to_introspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery = respx.get(CONFIG_URL).respond(
        200,
        json=_discovery_payload(
            jwks_uri="http://oidc.test/jwks",
            introspection_endpoint="http://oidc.test/introspect",
        ),
    )
    introspection = respx.post("http://oidc.test/introspect").respond(
        200, json={"active": True, "sub": "user-2", "scope": "openid"}
    )

    async def _fake_verify(self: OIDCTokenVerifier, token: str) -> dict[str, Any] | None:
        return None

    monkeypatch.setattr(OIDCTokenVerifier, "_verify_jwt", _fake_verify, raising=True)

    verifier = _make_verifier()
    access = await verifier.verify_token("a.b.c")

    assert discovery.called
    assert introspection.called
    assert access is not None
    assert access.scopes == ["openid"]

    request = introspection.calls[0].request
    body = request.content.decode()
    assert "token=a.b.c" in body
    assert "client_id=client-id" in body
    assert "client_secret=client-secret" in body


@respx.mock
@pytest.mark.asyncio
async def test_oidc_verifier_falls_back_to_userinfo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery = respx.get(CONFIG_URL).respond(
        200,
        json=_discovery_payload(
            jwks_uri="http://oidc.test/jwks",
            introspection_endpoint="http://oidc.test/introspect",
            userinfo_endpoint="http://oidc.test/userinfo",
        ),
    )
    introspection = respx.post("http://oidc.test/introspect").respond(200, json={"active": False})
    userinfo = respx.get("http://oidc.test/userinfo").respond(200, json={"sub": "user-3"})

    async def _fake_verify(self: OIDCTokenVerifier, token: str) -> dict[str, Any] | None:
        return None

    monkeypatch.setattr(OIDCTokenVerifier, "_verify_jwt", _fake_verify, raising=True)

    verifier = _make_verifier()
    access = await verifier.verify_token("a.b.c")

    assert discovery.called
    assert introspection.called
    assert userinfo.called
    assert access is not None

    userinfo_request = userinfo.calls[0].request
    assert userinfo_request.headers.get("authorization") == "Bearer a.b.c"


@respx.mock
@pytest.mark.asyncio
async def test_oidc_verifier_returns_none_without_paths() -> None:
    discovery = respx.get(CONFIG_URL).respond(200, json=_discovery_payload())

    verifier = _make_verifier()
    access = await verifier.verify_token("opaque-token")

    assert discovery.called
    assert access is None
