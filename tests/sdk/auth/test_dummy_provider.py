import pytest

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.providers.dummy import DummyProviderAdapter


def test_build_authorize_url_includes_state_and_pkce() -> None:
    # Authorize URL carries state, redirect, scopes, PKCE, and extra params.
    adapter = DummyProviderAdapter()
    url = adapter.build_authorize_url(
        redirect_uri="http://localhost/callback",
        state="abc123",
        scopes=["s1", "s2"],
        code_challenge="challenge",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )

    assert "state=abc123" in url
    assert "redirect_uri=http://localhost/callback" in url
    assert "scope=s1 s2" in url
    assert "code_challenge=challenge" in url
    assert "code_challenge_method=S256" in url
    assert "foo=bar" in url


@pytest.mark.asyncio
async def test_exchange_code_success_and_scopes() -> None:
    # Happy path code exchange returns tokens and requested scopes.
    adapter = DummyProviderAdapter(expected_code="OK", issued_scopes=["a", "b"])
    result = await adapter.exchange_code(
        code="OK",
        redirect_uri="http://localhost/callback",
        code_verifier=None,
        scopes=["a", "b"],
    )

    assert result.access_token.startswith("DUMMY_ACCESS_TOKEN")
    assert result.refresh_token == "DUMMY_REFRESH_TOKEN"
    assert result.provider_scopes_granted == ["a", "b"]
    assert result.expires_at is not None


@pytest.mark.asyncio
async def test_exchange_code_rejects_bad_code() -> None:
    # Unknown codes are rejected.
    adapter = DummyProviderAdapter(expected_code="GOOD")
    with pytest.raises(ProviderError) as excinfo:
        await adapter.exchange_code(
            code="BAD", redirect_uri="http://localhost/callback", code_verifier=None
        )
    assert excinfo.value.error == "invalid_grant"
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_exchange_code_rejects_bad_pkce() -> None:
    # PKCE verifier mismatch is rejected.
    adapter = DummyProviderAdapter(expected_code="GOOD", expected_code_verifier="verifier")
    with pytest.raises(ProviderError):
        await adapter.exchange_code(
            code="GOOD",
            redirect_uri="http://localhost/callback",
            code_verifier="wrong",
        )


@pytest.mark.asyncio
async def test_refresh_token_rotates_access_token() -> None:
    # Refresh returns a rotated access token and preserves refresh token.
    adapter = DummyProviderAdapter()
    initial = await adapter.refresh_token(refresh_token="DUMMY_REFRESH_TOKEN", scopes=None)
    rotated = await adapter.refresh_token(refresh_token="DUMMY_REFRESH_TOKEN", scopes=None)

    assert rotated.access_token != initial.access_token
    assert rotated.refresh_token == "DUMMY_REFRESH_TOKEN"
    assert rotated.provider_scopes_granted == adapter.issued_scopes


@pytest.mark.asyncio
async def test_fetch_user_info_success_and_failure() -> None:
    # User info succeeds for issued token and rejects unknown.
    adapter = DummyProviderAdapter()
    grant = await adapter.exchange_code(
        code="TEST_CODE_OK", redirect_uri="http://localhost/callback", code_verifier=None
    )
    user = await adapter.fetch_user_info(access_token=grant.access_token)

    assert user.user_id == "dummy-user"
    assert user.provider_scopes_granted == adapter.issued_scopes

    with pytest.raises(ProviderError):
        await adapter.fetch_user_info(access_token="invalid")


@pytest.mark.asyncio
async def test_revoke_token_validates_known_tokens() -> None:
    # Revoke succeeds for known tokens and rejects unknown tokens.
    adapter = DummyProviderAdapter()
    grant = await adapter.exchange_code(
        code="TEST_CODE_OK", redirect_uri="http://localhost/callback", code_verifier=None
    )

    assert await adapter.revoke_token(token=grant.access_token) is True

    with pytest.raises(ProviderError):
        await adapter.revoke_token(token="not-recognized")
