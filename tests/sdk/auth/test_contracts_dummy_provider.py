import pytest

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.providers.dummy import DummyProviderAdapter


def test_authorize_url_includes_core_params() -> None:
    # Authorize URL includes state, redirect, scopes, PKCE, and extra params.
    adapter = DummyProviderAdapter()

    url = adapter.build_authorize_url(
        redirect_uri="http://localhost/callback",
        state="STATE123",
        scopes=["one", "two"],
        code_challenge="challenge",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )

    assert "state=STATE123" in url
    assert "redirect_uri=http://localhost/callback" in url
    assert "scope=one two" in url
    assert "code_challenge=challenge" in url
    assert "code_challenge_method=S256" in url
    assert "foo=bar" in url


@pytest.mark.asyncio
async def test_exchange_and_fetch_user_info_success() -> None:
    # Happy path: exchange code, then fetch user info with returned access token.
    adapter = DummyProviderAdapter(expected_code="CODE_OK", issued_scopes=["alpha", "beta"])

    grant = await adapter.exchange_code(
        code="CODE_OK",
        redirect_uri="http://localhost/callback",
        scopes=["alpha", "beta"],
    )

    assert grant.access_token
    assert grant.refresh_token
    assert grant.provider_scopes_granted is not None
    assert "alpha" in grant.provider_scopes_granted
    assert grant.expires_at is not None

    user_info = await adapter.fetch_user_info(access_token=grant.access_token)
    assert user_info.user_id == "dummy-user"
    assert user_info.provider_scopes_granted == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_exchange_rejects_wrong_code() -> None:
    # Wrong authorization code is rejected.
    adapter = DummyProviderAdapter(expected_code="CODE_OK")

    with pytest.raises(ProviderError) as excinfo:
        await adapter.exchange_code(
            code="BAD_CODE",
            redirect_uri="http://localhost/callback",
        )
    assert excinfo.value.error == "invalid_grant"
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_exchange_rejects_wrong_pkce() -> None:
    # Wrong PKCE verifier is rejected.
    adapter = DummyProviderAdapter(expected_code_verifier="expected-verifier")

    with pytest.raises(ProviderError) as excinfo:
        await adapter.exchange_code(
            code="TEST_CODE_OK",
            redirect_uri="http://localhost/callback",
            code_verifier="wrong",
        )
    assert excinfo.value.error == "invalid_grant"
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_refresh_rotates_access_token() -> None:
    # Refresh rotates the access token and keeps the refresh token stable.
    adapter = DummyProviderAdapter()
    first = await adapter.refresh_token(refresh_token="DUMMY_REFRESH_TOKEN", scopes=None)
    second = await adapter.refresh_token(refresh_token="DUMMY_REFRESH_TOKEN", scopes=None)

    assert second.access_token != first.access_token
    assert second.refresh_token == "DUMMY_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_fetch_user_info_rejects_unknown_token() -> None:
    # Unknown access tokens are rejected.
    adapter = DummyProviderAdapter()
    with pytest.raises(ProviderError) as excinfo:
        await adapter.fetch_user_info(access_token="UNKNOWN")
    assert excinfo.value.error == "invalid_token"
    assert excinfo.value.status_code == 401
