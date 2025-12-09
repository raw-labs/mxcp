import pytest
import pytest_asyncio

from mxcp.sdk.auth.auth_service import AuthService
from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.providers.dummy import DummyProviderAdapter
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import SqliteTokenStore


@pytest_asyncio.fixture
async def auth_service(tmp_path):
    store = SqliteTokenStore(tmp_path / "auth.db")
    await store.initialize()
    session_manager = SessionManager(store)
    provider = DummyProviderAdapter(expected_code_verifier="verifier")
    service = AuthService(
        provider_adapter=provider,
        session_manager=session_manager,
        callback_url="http://localhost/auth/callback",
    )
    yield service
    await store.close()


@pytest.mark.asyncio
async def test_full_auth_flow(auth_service: AuthService) -> None:
    authorize_url, state_record = await auth_service.authorize(
        client_id="client-1",
        redirect_uri="http://client/app",
        scopes=["dummy.read"],
        code_challenge="challenge",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )

    assert "state=" in authorize_url
    assert state_record.redirect_uri == "http://client/app"

    auth_code, session = await auth_service.handle_callback(
        code="TEST_CODE_OK",
        state=state_record.state,
        code_verifier="verifier",
    )

    assert session.provider_access_token is not None
    assert auth_code.redirect_uri == "http://client/app"

    token_response = await auth_service.exchange_token(auth_code=auth_code.code)
    assert token_response.access_token == session.access_token
    assert token_response.refresh_token == session.refresh_token
    assert token_response.provider_access_token == session.provider_access_token
    assert token_response.expires_in is None or token_response.expires_in >= 0

    with pytest.raises(ProviderError):
        await auth_service.exchange_token(auth_code=auth_code.code)


@pytest.mark.asyncio
async def test_invalid_state_rejected(auth_service: AuthService) -> None:
    with pytest.raises(ProviderError):
        await auth_service.handle_callback(code="TEST_CODE_OK", state="unknown", code_verifier=None)
