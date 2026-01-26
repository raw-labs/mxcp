import base64
import hashlib

import pytest
import pytest_asyncio

from mxcp.sdk.auth.auth_service import AuthService
from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.providers.dummy import DummyProviderAdapter
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import TokenStore


class _NoPkceDummyProvider(DummyProviderAdapter):
    pkce_methods_supported: list[str] = []


@pytest_asyncio.fixture
async def auth_service(token_store: TokenStore) -> AuthService:
    session_manager = SessionManager(token_store)
    provider = DummyProviderAdapter(expected_code_verifier=None)
    return AuthService(
        provider_adapter=provider,
        session_manager=session_manager,
        callback_url="http://localhost/auth/callback",
    )


def _s256_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("utf-8")


@pytest.mark.asyncio
async def test_upstream_pkce_is_generated_even_without_downstream_pkce(
    token_store: TokenStore,
) -> None:
    session_manager = SessionManager(token_store)
    provider = DummyProviderAdapter(expected_code_verifier=None)
    service = AuthService(
        provider_adapter=provider,
        session_manager=session_manager,
        callback_url="http://localhost/auth/callback",
    )

    authorize_url, state_record = await service.authorize(
        client_id="client-1",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge=None,
        code_challenge_method=None,
    )
    assert state_record.provider_code_verifier
    assert "code_challenge=" in authorize_url
    assert "code_challenge_method=S256" in authorize_url


@pytest.mark.asyncio
async def test_upstream_pkce_not_used_when_provider_does_not_support_it(
    token_store: TokenStore,
) -> None:
    session_manager = SessionManager(token_store)
    provider = _NoPkceDummyProvider(expected_code_verifier=None)
    service = AuthService(
        provider_adapter=provider,
        session_manager=session_manager,
        callback_url="http://localhost/auth/callback",
    )

    authorize_url, state_record = await service.authorize(
        client_id="client-1",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge=None,
        code_challenge_method=None,
    )
    assert state_record.provider_code_verifier is None
    assert "code_challenge=" not in authorize_url
    assert "code_challenge_method=" not in authorize_url


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
        await auth_service.handle_callback(code="TEST_CODE_OK", state="unknown")


@pytest.mark.asyncio
async def test_exchange_token_does_not_validate_pkce_verifier(auth_service: AuthService) -> None:
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
        code="TEST_CODE_OK", state=state_record.state
    )

    # Downstream PKCE (client ↔ MXCP token endpoint) is verified by the MCP framework
    # token handler *before* AuthService.exchange_token() is called. AuthService focuses
    # on auth-code validity, client/redirect binding, and one-time use. Therefore, a
    # "wrong" verifier here is intentionally ignored and the exchange still succeeds.
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
        code="TEST_CODE_OK", state=state_record.state
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
        code="TEST_CODE_OK", state=state_record.state
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
        code="TEST_CODE_OK", state=state_record.state
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
        code="TEST_CODE_OK", state=state_record.state
    )

    token_response = await auth_service.exchange_token(
        auth_code=auth_code.code,
        client_id="client-1",
        redirect_uri="http://client/app",
    )
    assert token_response.access_token == session.access_token


@pytest.mark.asyncio
async def test_authorize_stores_state_for_unknown_client(auth_service: AuthService) -> None:
    # Redirect/client validation happens in IssuerOAuthAuthorizationServer.authorize(),
    # not in AuthService.
    _, state_record = await auth_service.authorize(
        client_id="unknown-client",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge=None,
        code_challenge_method=None,
    )
    assert state_record.client_id == "unknown-client"
    assert state_record.redirect_uri == "http://client/app"


@pytest.mark.asyncio
async def test_authorize_stores_state_for_any_redirect_uri(auth_service: AuthService) -> None:
    # Redirect/client validation happens in IssuerOAuthAuthorizationServer.authorize(),
    # not in AuthService.
    _, state_record = await auth_service.authorize(
        client_id="client-1",
        redirect_uri="http://evil/app",
        scopes=["dummy.read"],
        code_challenge=None,
        code_challenge_method=None,
    )
    assert state_record.client_id == "client-1"
    assert state_record.redirect_uri == "http://evil/app"


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
        code="TEST_CODE_OK", state=state_record.state
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
        code="TEST_CODE_OK", state=state_record.state
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
async def test_authorize_allows_dcr_pattern_when_client_unknown(token_store: TokenStore) -> None:
    session_manager = SessionManager(token_store)
    provider = DummyProviderAdapter(expected_code_verifier=None)
    service = AuthService(
        provider_adapter=provider,
        session_manager=session_manager,
        callback_url="http://localhost/auth/callback",
    )

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


@pytest.mark.asyncio
async def test_authorize_accepts_any_redirect_uri_and_client_id(token_store: TokenStore) -> None:
    """Redirect validation is enforced by IssuerOAuthAuthorizationServer, not AuthService."""
    session_manager = SessionManager(token_store)
    provider = DummyProviderAdapter(expected_code_verifier=None)
    service = AuthService(
        provider_adapter=provider,
        session_manager=session_manager,
        callback_url="http://localhost/auth/callback",
    )

    _, state_record = await service.authorize(
        client_id="any-client",
        redirect_uri="http://evil/app",
        scopes=["dummy.read"],
        code_challenge=None,
        code_challenge_method=None,
    )
    assert state_record.client_id == "any-client"
    assert state_record.redirect_uri == "http://evil/app"
