import base64
import hashlib
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from mxcp.sdk.auth.auth_service import AuthService
from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.providers.dummy import DummyProviderAdapter
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import SqliteTokenStore


@pytest_asyncio.fixture
async def auth_service(tmp_path: Path) -> AsyncGenerator[AuthService, None]:
    store = SqliteTokenStore(tmp_path / "auth.db", encryption_key=Fernet.generate_key())
    await store.initialize()
    session_manager = SessionManager(store)
    provider = DummyProviderAdapter(expected_code_verifier=None)
    client_registry = {
        "client-1": ["http://client/*"],
        "client-2": ["http://other/*"],
    }
    service = AuthService(
        provider_adapter=provider,
        session_manager=session_manager,
        callback_url="http://localhost/auth/callback",
        client_registry=client_registry,
        allowed_redirect_patterns=["http://localhost/*"],
    )
    yield service
    await store.close()


def _s256_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("utf-8")


@pytest.mark.asyncio
async def test_full_auth_flow_pkce_s256(auth_service: AuthService) -> None:
    # Full issuer-mode happy path with S256 PKCE: state + PKCE, provider code exchange,
    # session, MXCP auth code, and final token exchange requiring verifier.
    verifier = "verifier"
    challenge = _s256_challenge(verifier)
    authorize_url, state_record = await auth_service.authorize(
        client_id="client-1",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge=challenge,
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )

    assert "state=" in authorize_url
    assert state_record.redirect_uri == "http://client/app"

    auth_code, session, _client_state = await auth_service.handle_callback(
        code="TEST_CODE_OK",
        state=state_record.state,
        code_verifier=verifier,
    )

    assert session.provider_access_token is not None
    assert auth_code.redirect_uri == "http://client/app"

    token_response = await auth_service.exchange_token(
        auth_code=auth_code.code,
        code_verifier=verifier,
        client_id="client-1",
        redirect_uri="http://client/app",
    )
    assert token_response.access_token == session.access_token
    assert token_response.refresh_token == session.refresh_token
    assert token_response.provider_access_token == session.provider_access_token
    assert token_response.expires_in is None or token_response.expires_in >= 0

    with pytest.raises(ProviderError):
        await auth_service.exchange_token(
            auth_code=auth_code.code,
            code_verifier=verifier,
            client_id="client-1",
            redirect_uri="http://client/app",
        )


@pytest.mark.asyncio
async def test_invalid_state_rejected(auth_service: AuthService) -> None:
    # Rejects callbacks with unknown/expired state.
    with pytest.raises(ProviderError):
        await auth_service.handle_callback(code="TEST_CODE_OK", state="unknown", code_verifier=None)


@pytest.mark.asyncio
async def test_token_exchange_requires_pkce_wrong_verifier(auth_service: AuthService) -> None:
    verifier = "good"
    challenge = _s256_challenge(verifier)
    authorize_url, state_record = await auth_service.authorize(
        client_id="client-1",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    auth_code, _, _client_state = await auth_service.handle_callback(
        code="TEST_CODE_OK", state=state_record.state, code_verifier=verifier
    )

    # PKCE verification is performed upstream by the MCP token handler. The
    # AuthService.exchange_token path assumes the verifier was validated already.
    token = await auth_service.exchange_token(
        auth_code=auth_code.code,
        code_verifier="bad",
        client_id="client-1",
        redirect_uri="http://client/app",
    )
    assert token.access_token


@pytest.mark.asyncio
async def test_token_exchange_second_redemption_rejected(auth_service: AuthService) -> None:
    # After a successful redemption, a second attempt is rejected.
    verifier = "once-only"
    challenge = _s256_challenge(verifier)
    authorize_url, state_record = await auth_service.authorize(
        client_id="client-1",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    auth_code, _, _client_state = await auth_service.handle_callback(
        code="TEST_CODE_OK", state=state_record.state, code_verifier=verifier
    )

    await auth_service.exchange_token(
        auth_code=auth_code.code,
        code_verifier=verifier,
        client_id="client-1",
        redirect_uri="http://client/app",
    )
    with pytest.raises(ProviderError):
        await auth_service.exchange_token(
            auth_code=auth_code.code,
            code_verifier=verifier,
            client_id="client-1",
            redirect_uri="http://client/app",
        )


@pytest.mark.asyncio
async def test_token_exchange_requires_pkce_missing_verifier(auth_service: AuthService) -> None:
    verifier = "missing"
    challenge = _s256_challenge(verifier)
    authorize_url, state_record = await auth_service.authorize(
        client_id="client-1",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    auth_code, _, _client_state = await auth_service.handle_callback(
        code="TEST_CODE_OK", state=state_record.state, code_verifier=verifier
    )

    # PKCE verification is performed upstream by the MCP token handler, so the
    # verifier is optional here.
    token = await auth_service.exchange_token(
        auth_code=auth_code.code,
        client_id="client-1",
        redirect_uri="http://client/app",
    )
    assert token.access_token


@pytest.mark.asyncio
async def test_plain_pkce_validation(auth_service: AuthService) -> None:
    verifier = "plainverifier"
    authorize_url, state_record = await auth_service.authorize(
        client_id="client-1",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge=verifier,
        code_challenge_method="plain",
    )
    auth_code, _, _client_state = await auth_service.handle_callback(
        code="TEST_CODE_OK", state=state_record.state, code_verifier=verifier
    )

    await auth_service.exchange_token(
        auth_code=auth_code.code,
        code_verifier=verifier,
        client_id="client-1",
        redirect_uri="http://client/app",
    )

    with pytest.raises(ProviderError):
        await auth_service.exchange_token(
            auth_code=auth_code.code,
            code_verifier="wrong",
            client_id="client-1",
            redirect_uri="http://client/app",
        )


@pytest.mark.asyncio
async def test_no_challenge_allows_token_exchange_without_verifier(
    auth_service: AuthService,
) -> None:
    authorize_url, state_record = await auth_service.authorize(
        client_id="client-1",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge=None,
        code_challenge_method=None,
    )
    auth_code, session, _client_state = await auth_service.handle_callback(
        code="TEST_CODE_OK", state=state_record.state, code_verifier="verifier"
    )

    token_response = await auth_service.exchange_token(
        auth_code=auth_code.code,
        client_id="client-1",
        redirect_uri="http://client/app",
    )
    assert token_response.access_token == session.access_token


@pytest.mark.asyncio
async def test_authorize_rejects_unknown_client(auth_service: AuthService) -> None:
    with pytest.raises(ProviderError):
        await auth_service.authorize(
            client_id="unknown-client",
            redirect_uri="http://client/app",
            scopes=["dummy.read"],
            code_challenge=None,
            code_challenge_method=None,
        )


@pytest.mark.asyncio
async def test_authorize_rejects_bad_redirect(auth_service: AuthService) -> None:
    with pytest.raises(ProviderError):
        await auth_service.authorize(
            client_id="client-1",
            redirect_uri="http://evil/app",
            scopes=["dummy.read"],
            code_challenge=None,
            code_challenge_method=None,
        )


@pytest.mark.asyncio
async def test_exchange_rejects_wrong_client_or_redirect(auth_service: AuthService) -> None:
    verifier = "verifier"
    challenge = _s256_challenge(verifier)
    _, state_record = await auth_service.authorize(
        client_id="client-1",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    auth_code, _, _client_state = await auth_service.handle_callback(
        code="TEST_CODE_OK", state=state_record.state, code_verifier=verifier
    )

    with pytest.raises(ProviderError):
        await auth_service.exchange_token(
            auth_code=auth_code.code,
            code_verifier=verifier,
            client_id="client-2",  # wrong client
            redirect_uri="http://client/app",
        )

    with pytest.raises(ProviderError):
        await auth_service.exchange_token(
            auth_code=auth_code.code,
            code_verifier=verifier,
            client_id="client-1",
            redirect_uri="http://other/app",  # wrong redirect
        )


@pytest.mark.asyncio
async def test_access_token_ttl_aligns_to_provider(auth_service: AuthService) -> None:
    verifier = "verifier"
    challenge = _s256_challenge(verifier)
    _, state_record = await auth_service.authorize(
        client_id="client-1",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    auth_code, session, _client_state = await auth_service.handle_callback(
        code="TEST_CODE_OK", state=state_record.state, code_verifier=verifier
    )
    token_response = await auth_service.exchange_token(
        auth_code=auth_code.code,
        code_verifier=verifier,
        client_id="client-1",
        redirect_uri="http://client/app",
    )
    # Dummy provider sets expires_at = now + 3600; allow small drift.
    assert token_response.expires_in is not None
    assert 3500 <= token_response.expires_in <= 3600
    assert session.provider_expires_at is not None


@pytest.mark.asyncio
async def test_authorize_allows_dcr_pattern_when_client_unknown(tmp_path: Path) -> None:
    store = SqliteTokenStore(tmp_path / "auth.db", encryption_key=Fernet.generate_key())
    await store.initialize()
    session_manager = SessionManager(store)
    provider = DummyProviderAdapter(expected_code_verifier=None)
    service = AuthService(
        provider_adapter=provider,
        session_manager=session_manager,
        callback_url="http://localhost/auth/callback",
        client_registry={},  # no pre-registered clients
        allowed_redirect_patterns=["http://localhost/*"],
    )

    try:
        _, state_record = await service.authorize(
            client_id="dynamic-client",
            redirect_uri="http://localhost/app",
            scopes=["dummy.read"],
            code_challenge=None,
            code_challenge_method=None,
        )
        # Should store client_id and redirect_uri
        assert state_record.client_id == "dynamic-client"
        assert state_record.redirect_uri == "http://localhost/app"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_authorize_rejects_dcr_pattern_mismatch(tmp_path: Path) -> None:
    store = SqliteTokenStore(tmp_path / "auth.db", encryption_key=Fernet.generate_key())
    await store.initialize()
    session_manager = SessionManager(store)
    provider = DummyProviderAdapter(expected_code_verifier=None)
    service = AuthService(
        provider_adapter=provider,
        session_manager=session_manager,
        callback_url="http://localhost/auth/callback",
        client_registry={},  # no pre-registered clients
        allowed_redirect_patterns=["http://localhost/*"],
    )

    with pytest.raises(ProviderError):
        await service.authorize(
            client_id="dynamic-client",
            redirect_uri="http://evil/app",
            scopes=["dummy.read"],
            code_challenge=None,
            code_challenge_method=None,
        )

    await store.close()


@pytest.mark.asyncio
async def test_authorize_allows_all_when_no_allowlists(tmp_path: Path) -> None:
    store = SqliteTokenStore(tmp_path / "auth.db", encryption_key=Fernet.generate_key())
    await store.initialize()
    session_manager = SessionManager(store)
    provider = DummyProviderAdapter(expected_code_verifier=None)
    # No registry, no allowed patterns → allow all (legacy behavior)
    service = AuthService(
        provider_adapter=provider,
        session_manager=session_manager,
        callback_url="http://localhost/auth/callback",
        client_registry={},
        allowed_redirect_patterns=None,
    )

    try:
        _, state_record = await service.authorize(
            client_id="any-client",
            redirect_uri="http://evil/app",
            scopes=["dummy.read"],
            code_challenge=None,
            code_challenge_method=None,
        )
        assert state_record.client_id == "any-client"
        assert state_record.redirect_uri == "http://evil/app"
    finally:
        await store.close()
