import pytest

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.providers.dummy import DummyProviderAdapter


@pytest.mark.asyncio
async def test_authorize_url_includes_core_params() -> None:
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
    adapter = DummyProviderAdapter(expected_code="CODE_OK", issued_scopes=["alpha", "beta"])

    grant = await adapter.exchange_code(
        code="CODE_OK",
        redirect_uri="http://localhost/callback",
        scopes=["alpha", "beta"],
    )

    assert grant.access_token
    assert grant.refresh_token
    assert "alpha" in grant.provider_scopes_granted
    assert grant.expires_at is not None

    user_info = await adapter.fetch_user_info(access_token=grant.access_token)
    assert user_info.user_id == "dummy-user"
    assert user_info.provider_scopes_granted == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_exchange_rejects_wrong_code() -> None:
    adapter = DummyProviderAdapter(expected_code="CODE_OK")

    with pytest.raises(ProviderError):
        await adapter.exchange_code(
            code="BAD_CODE",
            redirect_uri="http://localhost/callback",
        )


@pytest.mark.asyncio
async def test_exchange_rejects_wrong_pkce() -> None:
    adapter = DummyProviderAdapter(expected_code_verifier="expected-verifier")

    with pytest.raises(ProviderError):
        await adapter.exchange_code(
            code="TEST_CODE_OK",
            redirect_uri="http://localhost/callback",
            code_verifier="wrong",
        )


@pytest.mark.asyncio
async def test_refresh_rotates_access_token() -> None:
    adapter = DummyProviderAdapter()
    grant = await adapter.exchange_code(
        code="TEST_CODE_OK",
        redirect_uri="http://localhost/callback",
    )

    refreshed = await adapter.refresh_token(
        refresh_token=grant.refresh_token or "",
        scopes=["dummy.read"],
    )

    assert refreshed.access_token.endswith("_refreshed")
    assert refreshed.refresh_token == grant.refresh_token


@pytest.mark.asyncio
async def test_fetch_user_info_rejects_unknown_token() -> None:
    adapter = DummyProviderAdapter()
    with pytest.raises(ProviderError):
        await adapter.fetch_user_info(access_token="UNKNOWN")


@pytest.mark.asyncio
async def test_revoke_token_accepts_known_tokens_and_rejects_unknown() -> None:
    adapter = DummyProviderAdapter()
    grant = await adapter.exchange_code(
        code="TEST_CODE_OK",
        redirect_uri="http://localhost/callback",
    )

    assert await adapter.revoke_token(token=grant.access_token)

    with pytest.raises(ProviderError):
        await adapter.revoke_token(token="totally-unknown")
