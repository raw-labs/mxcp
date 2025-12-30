from collections.abc import AsyncGenerator
from pathlib import Path
import time

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from mxcp.sdk.auth.middleware import AuthenticationMiddleware
from mxcp.sdk.auth.providers.dummy import DummyProviderAdapter
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import SqliteTokenStore


@pytest_asyncio.fixture
async def session_manager(tmp_path: Path) -> AsyncGenerator[SessionManager, None]:
    store = SqliteTokenStore(tmp_path / "auth.db", encryption_key=Fernet.generate_key())
    await store.initialize()
    manager = SessionManager(store)
    yield manager
    await store.close()


@pytest_asyncio.fixture
async def provider() -> DummyProviderAdapter:
    return DummyProviderAdapter()


@pytest.mark.asyncio
async def test_session_manager_happy_path(
    session_manager: SessionManager, provider: DummyProviderAdapter
) -> None:
    # SessionManager + ProviderAdapter path: valid token yields user context.
    user_info = await provider.fetch_user_info(access_token=provider._access_token)
    session = await session_manager.issue_session(
        provider=provider.provider_name,
        user_info=user_info,
        provider_access_token=provider._access_token,
        provider_refresh_token=provider._refresh_token,
        provider_expires_at=user_info.raw_profile.get("exp") if user_info.raw_profile else None,
        scopes=user_info.provider_scopes_granted,
    )

    middleware = AuthenticationMiddleware(
        session_manager=session_manager,
        provider_adapter=provider,
        token_getter=lambda: session.access_token,
    )

    user_context = await middleware.check_authentication()
    assert user_context is not None
    assert user_context.user_id == user_info.user_id
    assert user_context.external_token == provider._access_token


@pytest.mark.asyncio
async def test_session_manager_invalid_token_returns_none(
    session_manager: SessionManager, provider: DummyProviderAdapter
) -> None:
    # Invalid token should fail auth and return None.
    middleware = AuthenticationMiddleware(
        session_manager=session_manager,
        provider_adapter=provider,
        token_getter=lambda: "unknown",
    )

    assert await middleware.check_authentication() is None


@pytest.mark.asyncio
async def test_session_manager_missing_token_returns_none(
    session_manager: SessionManager, provider: DummyProviderAdapter
) -> None:
    # Missing token should fail auth and return None.
    middleware = AuthenticationMiddleware(
        session_manager=session_manager,
        provider_adapter=provider,
        token_getter=lambda: None,
    )

    assert await middleware.check_authentication() is None


@pytest.mark.asyncio
async def test_provider_token_refresh_on_skew_persists_rotation(
    session_manager: SessionManager, provider: DummyProviderAdapter, monkeypatch
) -> None:
    # Prepare session whose provider token is near expiry so refresh is attempted.
    old_provider_token = provider._access_token

    calls = {"refresh": 0}
    real_refresh = provider.refresh_token

    async def wrapped_refresh_token(*args, **kwargs):
        calls["refresh"] += 1
        return await real_refresh(*args, **kwargs)

    monkeypatch.setattr(provider, "refresh_token", wrapped_refresh_token)

    user_info = await provider.fetch_user_info(access_token=provider._access_token)
    session = await session_manager.issue_session(
        provider=provider.provider_name,
        user_info=user_info,
        provider_access_token=provider._access_token,
        provider_refresh_token=provider._refresh_token,
        provider_expires_at=time.time() + 10,
        scopes=user_info.provider_scopes_granted,
    )

    # Middleware should refresh before using the provider access token.
    middleware = AuthenticationMiddleware(
        session_manager=session_manager,
        provider_adapter=provider,
        token_getter=lambda: session.access_token,
        provider_token_skew_seconds=60,
        refresh_backoff_seconds=1,
    )

    user_context = await middleware.check_authentication()
    assert user_context is not None
    # New provider token must differ from the original.
    assert user_context.external_token != old_provider_token
    assert user_context.external_token == provider._access_token

    updated_session = await session_manager.get_session(session.access_token)
    # Rotation persisted; no backoff recorded on success.
    assert updated_session is not None
    assert updated_session.provider_access_token == provider._access_token
    assert updated_session.provider_refresh_backoff_until is None
    # Ensure refresh path was called exactly once.
    assert calls["refresh"] == 1


@pytest.mark.asyncio
async def test_provider_token_refresh_failure_sets_backoff_and_requires_reauth(
    session_manager: SessionManager, provider: DummyProviderAdapter
) -> None:
    # Build a session with an already expired provider token and bad refresh token.
    user_info = await provider.fetch_user_info(access_token=provider._access_token)
    session = await session_manager.issue_session(
        provider=provider.provider_name,
        user_info=user_info,
        provider_access_token=provider._access_token,
        provider_refresh_token="BAD_REFRESH",
        provider_expires_at=time.time() - 5,
        scopes=user_info.provider_scopes_granted,
    )

    # Refresh should fail and require re-auth; backoff should be set to avoid retry storms.
    middleware = AuthenticationMiddleware(
        session_manager=session_manager,
        provider_adapter=provider,
        token_getter=lambda: session.access_token,
        provider_token_skew_seconds=60,
        refresh_backoff_seconds=2,
    )

    assert await middleware.check_authentication() is None

    updated_session = await session_manager.get_session(session.access_token)
    assert updated_session is not None
    assert updated_session.provider_access_token is None
    assert updated_session.provider_refresh_token is None
    assert updated_session.provider_refresh_backoff_until is not None
    assert updated_session.provider_refresh_backoff_until > time.time()


@pytest.mark.asyncio
async def test_cached_userinfo_used_when_no_refresh_needed(
    session_manager: SessionManager, provider: DummyProviderAdapter, monkeypatch
) -> None:
    # Token is fresh enough; ensure we do NOT call fetch_user_info again.
    user_info = await provider.fetch_user_info(access_token=provider._access_token)
    session = await session_manager.issue_session(
        provider=provider.provider_name,
        user_info=user_info,
        provider_access_token=provider._access_token,
        provider_refresh_token=provider._refresh_token,
        provider_expires_at=time.time() + 3600,
        scopes=user_info.provider_scopes_granted,
    )

    async def fail_fetch_user_info(*args, **kwargs):
        raise AssertionError("fetch_user_info should not be called when not refreshing")

    monkeypatch.setattr(provider, "fetch_user_info", fail_fetch_user_info)

    middleware = AuthenticationMiddleware(
        session_manager=session_manager,
        provider_adapter=provider,
        token_getter=lambda: session.access_token,
    )

    user_context = await middleware.check_authentication()
    assert user_context is not None
    assert user_context.external_token == provider._access_token


@pytest.mark.asyncio
async def test_userinfo_refetched_once_after_refresh_when_enabled(
    session_manager: SessionManager, provider: DummyProviderAdapter, monkeypatch
) -> None:
    # Provider token is near expiry; enable post-refresh userinfo fetch.
    user_info = await provider.fetch_user_info(access_token=provider._access_token)
    session = await session_manager.issue_session(
        provider=provider.provider_name,
        user_info=user_info,
        provider_access_token=provider._access_token,
        provider_refresh_token=provider._refresh_token,
        provider_expires_at=time.time() + 5,
        scopes=user_info.provider_scopes_granted,
    )

    calls = {"count": 0}
    real_fetch = provider.fetch_user_info

    async def wrapped_fetch_user_info(*args, **kwargs):
        calls["count"] += 1
        return await real_fetch(*args, **kwargs)

    monkeypatch.setattr(provider, "fetch_user_info", wrapped_fetch_user_info)

    middleware = AuthenticationMiddleware(
        session_manager=session_manager,
        provider_adapter=provider,
        token_getter=lambda: session.access_token,
        provider_token_skew_seconds=60,
        fetch_userinfo_after_refresh=True,
    )

    user_context = await middleware.check_authentication()
    assert user_context is not None
    assert user_context.external_token == provider._access_token
    assert calls["count"] == 1
