import pytest
import pytest_asyncio

from mxcp.sdk.auth.middleware import AuthenticationMiddleware
from mxcp.sdk.auth.providers.dummy import DummyProviderAdapter
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import SqliteTokenStore


class _Token:
    def __init__(self, token: str) -> None:
        self.token = token


@pytest_asyncio.fixture
async def session_manager(tmp_path):
    store = SqliteTokenStore(tmp_path / "auth.db")
    await store.initialize()
    manager = SessionManager(store)
    yield manager
    await store.close()


@pytest_asyncio.fixture
async def provider():
    return DummyProviderAdapter()


@pytest.mark.asyncio
async def test_session_manager_happy_path(
    session_manager: SessionManager, provider: DummyProviderAdapter
) -> None:
    user_info = await provider.fetch_user_info(access_token=provider._access_token)  # type: ignore[attr-defined]
    session = await session_manager.issue_session(
        provider=provider.provider_name,
        user_info=user_info,
        provider_access_token=provider._access_token,  # type: ignore[attr-defined]
        provider_refresh_token=provider._refresh_token,  # type: ignore[attr-defined]
        provider_expires_at=user_info.raw_profile.get("exp") if user_info.raw_profile else None,
        scopes=user_info.provider_scopes_granted,
    )

    middleware = AuthenticationMiddleware(
        oauth_handler=None,
        oauth_server=None,
        session_manager=session_manager,
        provider_adapter=provider,
        token_getter=lambda: _Token(session.access_token),
    )

    user_context = await middleware.check_authentication()
    assert user_context is not None
    assert user_context.user_id == user_info.user_id
    assert user_context.external_token == provider._access_token  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_session_manager_invalid_token_returns_none(
    session_manager: SessionManager, provider: DummyProviderAdapter
) -> None:
    middleware = AuthenticationMiddleware(
        oauth_handler=None,
        oauth_server=None,
        session_manager=session_manager,
        provider_adapter=provider,
        token_getter=lambda: _Token("unknown"),
    )

    assert await middleware.check_authentication() is None


@pytest.mark.asyncio
async def test_session_manager_missing_token_returns_none(
    session_manager: SessionManager, provider: DummyProviderAdapter
) -> None:
    middleware = AuthenticationMiddleware(
        oauth_handler=None,
        oauth_server=None,
        session_manager=session_manager,
        provider_adapter=provider,
        token_getter=lambda: None,
    )

    assert await middleware.check_authentication() is None
