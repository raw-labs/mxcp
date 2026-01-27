"""Issuer-mode OAuthAuthorizationServerProvider backed by AuthService and SessionManager."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from typing import Any

from mcp.server.auth import provider as provider_module
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl, ValidationError

from mxcp.sdk.auth.auth_service import AuthService
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import ClientRecord, StoredSession

OAuthTokenType = Any
OAuthToken: Any = provider_module.OAuthToken  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)


class IssuerOAuthAuthorizationServer(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """Bridges AuthService/SessionManager to the MCP OAuth provider protocol."""

    def __init__(
        self,
        *,
        auth_service: AuthService,
        session_manager: SessionManager,
        clients: Mapping[str, OAuthClientInformationFull] | None = None,
    ) -> None:
        self.auth_service = auth_service
        self.session_manager = session_manager
        # Bootstrap clients (e.g. pre-configured clients from config). These will be
        # persisted to the TokenStore on first initialization and then cleared.
        self._bootstrap_clients: dict[str, OAuthClientInformationFull] = dict(clients or {})
        self._lock = asyncio.Lock()
        self._store_initialized = False
        # Track which dynamically-registered clients we've already warned about.
        # In issuer-mode, client-provided OAuth scopes (DCR metadata or /authorize params)
        # must not influence upstream IdP scope requests.
        self._warned_dcr_scopes: set[str] = set()

    async def initialize(self) -> None:
        """Initialize underlying storage for tokens/state."""
        await self._ensure_store_initialized()

    async def close(self) -> None:
        """Close underlying persistence used by this OAuth server."""
        if not self._store_initialized:
            return
        try:
            await self.session_manager.token_store.close()
        finally:
            self._store_initialized = False
            self._bootstrap_clients = {}

    def _oauth_client_to_client_record(
        self, client_info: OAuthClientInformationFull
    ) -> ClientRecord:
        if not client_info.client_id:
            raise ValueError("client_id is required")
        token_endpoint_auth_method = client_info.token_endpoint_auth_method
        if token_endpoint_auth_method is None:
            # MCP token endpoint middleware requires a concrete auth method; infer a
            # safe default when clients/config omit it.
            token_endpoint_auth_method = (
                "client_secret_post" if client_info.client_secret else "none"
            )
        redirect_uris = [str(u) for u in (client_info.redirect_uris or [])]
        return ClientRecord(
            client_id=client_info.client_id,
            client_secret=client_info.client_secret,
            token_endpoint_auth_method=token_endpoint_auth_method,
            redirect_uris=redirect_uris,
            grant_types=list(client_info.grant_types or []),
            response_types=list(client_info.response_types or []),
            scope=client_info.scope,
            client_name=client_info.client_name,
            created_at=time.time(),
        )

    def _client_record_to_oauth_client(
        self, record: ClientRecord
    ) -> OAuthClientInformationFull | None:
        try:
            redirect_uris = [AnyUrl(uri) for uri in (record.redirect_uris or [])]
        except ValidationError:
            return None
        return OAuthClientInformationFull(
            client_id=record.client_id,
            client_secret=record.client_secret,
            token_endpoint_auth_method=record.token_endpoint_auth_method,
            redirect_uris=redirect_uris,
            grant_types=record.grant_types,
            response_types=record.response_types,
            scope=record.scope,
            client_name=record.client_name,
        )

    # ----- client registration -----
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        await self._ensure_store_initialized()
        record = await self.session_manager.token_store.load_client(client_id)
        if not record:
            return None
        return self._client_record_to_oauth_client(record)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await self._ensure_store_initialized()
        if client_info.client_id is None:
            raise AuthorizeError("invalid_request", "Client ID is required")
        async with self._lock:
            if not client_info.redirect_uris:
                # Security: issuer-mode must bind clients to explicit redirect URIs
                # (either via config or DCR). Without registered redirect URIs, we
                # cannot safely validate redirects.
                raise AuthorizeError("invalid_request", "redirect_uris is required")

            # DCR may include a `scope` field. We accept it as client metadata but do
            # not use it to request upstream provider scopes (those come from server
            # configuration and will later be mapped to MXCP permissions).
            if client_info.client_id not in self._warned_dcr_scopes and client_info.scope:
                self._warned_dcr_scopes.add(client_info.client_id)
                logger.warning(
                    "Dynamic client registration included scopes; ignoring for provider authorization"
                )
            await self.session_manager.token_store.store_client(
                self._oauth_client_to_client_record(client_info)
            )

    # ----- authorize -----
    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        await self._ensure_store_initialized()
        if client is None:
            raise AuthorizeError("unauthorized_client", "Client not found")

        if client.client_id is None:
            raise AuthorizeError("unauthorized_client", "Client ID is missing")

        # IMPORTANT: persisted client registration is the source of truth.
        # Re-load from TokenStore to enforce strict redirect binding.
        persisted = await self.get_client(client.client_id)
        if not persisted:
            raise AuthorizeError("unauthorized_client", "Client not found")
        if not persisted.redirect_uris:
            raise AuthorizeError("invalid_request", "Client has no registered redirect URIs")

        redirect_uri_str = str(params.redirect_uri) if params.redirect_uri else ""
        if not redirect_uri_str:
            raise AuthorizeError("invalid_request", "Missing redirect URI")

        registered_redirects = [str(u) for u in (persisted.redirect_uris or [])]
        if redirect_uri_str not in registered_redirects:
            raise AuthorizeError("invalid_request", "Redirect URI not registered for client")

        # IMPORTANT: We intentionally ignore OAuth client requested scopes (from the
        # /authorize request). In MXCP issuer-mode, downstream provider scopes are
        # derived from server/provider configuration (and later mapped into MXCP
        # permissions). Client-supplied `scope` must not influence what we request
        # from the upstream IdP.
        if params.scopes:
            logger.warning("OAuth authorize request included scopes; ignoring")
        # Provider scopes come from server/provider configuration. We store them in
        # the issued state so that, if the upstream token endpoint omits the `scope`
        # field (which is allowed by OAuth 2.0), we can still treat the granted
        # scopes as “the requested scopes” rather than incorrectly assuming zero.
        scope_str = getattr(self.auth_service.provider_adapter, "scope", "")
        scopes: list[str] = scope_str.split() if isinstance(scope_str, str) and scope_str else []

        pkce_method = "S256" if params.code_challenge else None
        authorize_url, _ = await self.auth_service.authorize(
            client_id=client.client_id,
            redirect_uri=redirect_uri_str,
            scopes=scopes,
            code_challenge=params.code_challenge,
            code_challenge_method=pkce_method,
            client_state=params.state,  # Store client's original state
            extra_params={},
        )
        return authorize_url

    # ----- callback handling (custom helper, not part of interface) -----
    async def handle_callback(self, code: str, state: str) -> str:
        await self._ensure_store_initialized()
        logger.info("IssuerProvider.handle_callback: received callback")
        auth_code, _session, client_state = await self.auth_service.handle_callback(
            code=code, state=state
        )
        redirect_uri = auth_code.redirect_uri or ""
        # Never return the internal MXCP/IdP state to the client. If the MCP client did not
        # provide an original state, omit the state param in the redirect.
        return construct_redirect_uri(redirect_uri, code=auth_code.code, state=client_state)

    async def handle_callback_error(
        self, *, state: str, error: str, error_description: str | None = None
    ) -> str | None:
        """Handle provider error callbacks by redirecting back to the client."""
        await self._ensure_store_initialized()
        state_record = await self.session_manager.consume_state(state)
        if not state_record or not state_record.redirect_uri:
            return None
        return construct_redirect_uri(
            state_record.redirect_uri,
            error=error,
            error_description=error_description,
            state=state_record.client_state,
        )

    # ----- auth code loading / exchange -----
    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        await self._ensure_store_initialized()
        code_record = await self.session_manager.load_auth_code(authorization_code)
        if not code_record:
            return None

        try:
            redirect_uri = AnyUrl(code_record.redirect_uri) if code_record.redirect_uri else None
        except ValidationError:
            return None

        if not redirect_uri:
            raise TokenError("invalid_grant", "Missing redirect URI on authorization code")

        if code_record.expires_at < time.time():
            await self.session_manager.try_delete_auth_code(authorization_code)
            return None

        if redirect_uri and client and client.redirect_uris:
            registered = [str(uri) for uri in client.redirect_uris]
            if str(redirect_uri) not in registered:
                raise TokenError("invalid_grant", "Redirect URI mismatch")

        client_id = code_record.client_id or (client.client_id if client else None)
        if not client_id:
            raise TokenError("invalid_grant", "Missing client_id on authorization code")

        return AuthorizationCode(
            code=code_record.code,
            scopes=code_record.scopes or [],
            expires_at=code_record.expires_at,
            client_id=client_id,
            # Returned for MCP token handler PKCE verification.
            code_challenge=code_record.code_challenge or "",
            redirect_uri=redirect_uri or AnyUrl("http://localhost"),  # pragma: allowlist secret
            redirect_uri_provided_explicitly=bool(code_record.redirect_uri),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthTokenType:
        await self._ensure_store_initialized()
        # PKCE verification is handled by the MCP token handler before this method is called
        token_response = await self.auth_service.exchange_token(
            auth_code=authorization_code.code,
            client_id=client.client_id if client else None,
            redirect_uri=str(authorization_code.redirect_uri),
        )

        return OAuthToken(
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            token_type="Bearer",
            expires_in=token_response.expires_in,
            scope=" ".join(authorization_code.scopes),
        )

    # ----- refresh tokens -----
    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        await self._ensure_store_initialized()
        session = await self.session_manager.token_store.load_session_by_refresh_token(
            refresh_token
        )
        if not session:
            return None
        if session.expires_at and session.expires_at < time.time():
            await self.session_manager.revoke_session(session.access_token)
            return None
        if not client or not client.client_id:
            raise TokenError("invalid_client", "Client ID missing for refresh token")
        provider_scopes = session.user_info.provider_scopes_granted or []
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id if client else "",
            scopes=provider_scopes,
            expires_at=int(session.expires_at) if session.expires_at else None,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthTokenType:
        await self._ensure_store_initialized()
        session = await self.session_manager.token_store.load_session_by_refresh_token(
            refresh_token.token
        )
        if not session:
            raise TokenError("invalid_grant", "Refresh token not found")

        if session.expires_at and session.expires_at < time.time():
            await self.session_manager.revoke_session(session.access_token)
            raise TokenError("invalid_grant", "Refresh token expired")

        # Rotate session
        await self.session_manager.revoke_session(session.access_token)
        provider_scopes = session.user_info.provider_scopes_granted or []
        new_session = await self._issue_rotated_session(session)

        return OAuthToken(
            access_token=new_session.access_token,
            refresh_token=new_session.refresh_token,
            token_type="Bearer",
            expires_in=(
                int(new_session.expires_at - time.time()) if new_session.expires_at else None
            ),
            scope=" ".join(scopes or provider_scopes),
        )

    # ----- access token verification -----
    async def load_access_token(self, token: str) -> AccessToken | None:
        await self._ensure_store_initialized()
        session = await self.session_manager.get_session(token)
        if not session:
            return None
        if session.expires_at and session.expires_at < time.time():
            await self.session_manager.revoke_session(session.access_token)
            return None
        provider_scopes = session.user_info.provider_scopes_granted or []
        return AccessToken(
            token=session.access_token,
            client_id="",
            scopes=provider_scopes,
            expires_at=int(session.expires_at) if session.expires_at else None,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        await self._ensure_store_initialized()
        if isinstance(token, AccessToken):
            await self.session_manager.revoke_session(token.token)
            return
        if not isinstance(token, RefreshToken):
            raise TypeError(f"Unsupported token type: {type(token)!r}")

        # For refresh tokens, find the session and remove it by access token
        session = await self.session_manager.token_store.load_session_by_refresh_token(token.token)
        if session:
            await self.session_manager.revoke_session(session.access_token)

    # ----- helpers -----
    async def _issue_rotated_session(self, session: StoredSession) -> StoredSession:
        ttl_seconds: int | None = None
        if session.expires_at:
            ttl_seconds = max(0, int(session.expires_at - time.time()))
        return await self.session_manager.issue_session(
            provider=session.provider,
            user_info=session.user_info,
            provider_access_token=session.provider_access_token,
            provider_refresh_token=session.provider_refresh_token,
            provider_expires_at=session.provider_expires_at,
            access_token_ttl_seconds=ttl_seconds,
        )

    async def _ensure_store_initialized(self) -> None:
        if self._store_initialized:
            return
        async with self._lock:
            if self._store_initialized:
                return
            await self.session_manager.token_store.initialize()
            # Persist any pre-configured clients passed at construction time. This makes
            # configured clients available via TokenStore lookups and ensures DCR clients
            # survive process restarts.
            if self._bootstrap_clients:
                for client in self._bootstrap_clients.values():
                    if client.client_id:
                        await self.session_manager.token_store.store_client(
                            self._oauth_client_to_client_record(client)
                        )
                self._bootstrap_clients = {}
            self._store_initialized = True
