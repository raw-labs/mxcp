"""
Global pytest configuration and fixtures.
"""

import os

import pytest


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
