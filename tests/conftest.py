"""
Global pytest configuration and fixtures.
"""

import os

import pytest
from cryptography.fernet import Fernet

from mxcp.sdk.auth.storage import SqliteTokenStore, TokenStore


def _sqlite_store_factory(tmp_path) -> TokenStore:
    db_path = tmp_path / "auth.db"
    key = Fernet.generate_key()
    store = SqliteTokenStore(db_path, encryption_key=key)
    return store


@pytest.fixture(params=[_sqlite_store_factory], ids=["sqlite"])
async def token_store(request, tmp_path) -> TokenStore:
    """Parametrized token store fixture to exercise all backends uniformly."""
    store: TokenStore = request.param(tmp_path)
    await store.initialize()
    try:
        yield store
    finally:
        await store.close()


@pytest.fixture(autouse=True)
def disable_analytics(request):
    """Disable PostHog analytics for all tests except analytics unit tests.

    This prevents tests from accidentally sending real analytics events
    to PostHog. The fixture is auto-used for every test.

    Analytics unit tests (test_analytics.py) are excluded because they
    manage the environment variable themselves and mock the PostHog client.
    """
    # Skip for analytics tests - they manage env var and mock PostHog themselves
    if "test_analytics" in request.fspath.basename:
        yield
        return

    original = os.environ.get("MXCP_DISABLE_ANALYTICS")
    os.environ["MXCP_DISABLE_ANALYTICS"] = "1"
    yield
    # Restore original value
    if original is None:
        os.environ.pop("MXCP_DISABLE_ANALYTICS", None)
    else:
        os.environ["MXCP_DISABLE_ANALYTICS"] = original
