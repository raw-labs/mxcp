"""Session management for MXCP authentication.

This module provides the `SessionManager` class which handles MXCP session
lifecycle, token management, and the mapping between MXCP tokens and provider tokens.

The session manager extracts session management concerns from `GeneralOAuthAuthorizationServer`,
providing a cleaner separation of responsibilities.

It also manages OAuth state for the authorization flow, storing state metadata
needed to complete the OAuth callback.
"""

import asyncio
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .storage import TokenStore

logger = logging.getLogger(__name__)


@dataclass
class OAuthState:
    """OAuth state for tracking authorization flow.

    This stores the metadata needed to complete an OAuth callback,
    including the original redirect URI and PKCE parameters.

    Attributes:
        state: The state parameter (used as key).
        client_id: The MCP client ID initiating the flow.
        redirect_uri: The client's redirect URI to return to after auth.
        callback_url: The MXCP callback URL registered with the IdP.
        code_challenge: PKCE code challenge (for public clients).
        code_verifier: PKCE code verifier (for Keycloak, etc.).
        redirect_uri_provided_explicitly: Whether redirect_uri was explicit.
        provider: The OAuth provider name.
        scopes: Requested scopes.
        created_at: When this state was created.
        expires_at: When this state expires.
    """

    state: str
    client_id: str
    redirect_uri: str
    callback_url: str
    code_challenge: str | None = None
    code_verifier: str | None = None
    redirect_uri_provided_explicitly: bool = True
    provider: str | None = None
    scopes: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 600)  # 10 min default

    def is_expired(self) -> bool:
        """Check if this state has expired."""
        return time.time() > self.expires_at


@dataclass
class Session:
    """Represents an authenticated MXCP session.

    A session tracks the mapping between an MXCP access token and the
    provider's access token, along with associated metadata.

    Attributes:
        session_id: Unique identifier for the session.
        mxcp_token: The opaque MXCP access token issued to the client.
        mxcp_token_hash: SHA-256 hash of the MXCP token (for secure storage).
        client_id: The OAuth client ID that owns this session.
        provider_token: The provider's access token (encrypted at rest).
        provider_refresh_token: The provider's refresh token (encrypted at rest).
        scopes: List of scopes granted for this session.
        expires_at: Unix timestamp when this session expires.
        created_at: Unix timestamp when this session was created.
        last_accessed_at: Unix timestamp of last access.
    """

    session_id: str
    mxcp_token: str
    mxcp_token_hash: str
    client_id: str
    provider_token: str | None = None
    provider_refresh_token: str | None = None
    scopes: list[str] = field(default_factory=list)
    expires_at: float | None = None
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)

    @staticmethod
    def hash_token(token: str) -> str:
        """Create a SHA-256 hash of a token for secure storage.

        Args:
            token: The plaintext token to hash.

        Returns:
            Hex-encoded SHA-256 hash of the token.
        """
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def create(
        cls,
        client_id: str,
        provider_token: str | None = None,
        provider_refresh_token: str | None = None,
        scopes: list[str] | None = None,
        expires_in: int | None = None,
    ) -> "Session":
        """Create a new session with a fresh MXCP token.

        Args:
            client_id: The OAuth client ID.
            provider_token: The provider's access token.
            provider_refresh_token: The provider's refresh token.
            scopes: List of granted scopes.
            expires_in: Seconds until expiry (None for no expiry).

        Returns:
            A new Session instance.
        """
        mxcp_token = f"mcp_{secrets.token_hex(32)}"
        now = time.time()

        return cls(
            session_id=secrets.token_hex(16),
            mxcp_token=mxcp_token,
            mxcp_token_hash=cls.hash_token(mxcp_token),
            client_id=client_id,
            provider_token=provider_token,
            provider_refresh_token=provider_refresh_token,
            scopes=scopes or [],
            expires_at=(now + expires_in) if expires_in is not None else None,
            created_at=now,
            last_accessed_at=now,
        )

    def is_expired(self) -> bool:
        """Check if the session has expired.

        Returns:
            True if the session is expired, False otherwise.
        """
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        """Update the last_accessed_at timestamp."""
        self.last_accessed_at = time.time()


class SessionManager:
    """Manages MXCP sessions, token mappings, and OAuth state.

    The SessionManager handles:
    - Creating new sessions after successful OAuth flow
    - Validating MXCP tokens and loading sessions
    - Mapping MXCP tokens to provider tokens
    - Session cleanup and expiry
    - OAuth state management for authorization flow

    This class extracts session management from GeneralOAuthAuthorizationServer,
    providing a clean interface for middleware and other components.

    Attributes:
        token_store: Optional persistent storage for sessions.
        default_token_lifetime: Default lifetime for access tokens in seconds.
    """

    def __init__(
        self,
        token_store: "TokenStore | None" = None,
        default_token_lifetime: int = 3600,
    ):
        """Initialize the session manager.

        Args:
            token_store: Persistent storage backend for sessions.
            default_token_lifetime: Default token lifetime in seconds.
        """
        self.token_store = token_store
        self.default_token_lifetime = default_token_lifetime

        # In-memory session cache (token_hash -> Session)
        self._sessions: dict[str, Session] = {}
        # Token to hash mapping for fast lookup (mxcp_token -> token_hash)
        self._token_to_hash: dict[str, str] = {}

        # OAuth state storage (state -> OAuthState)
        self._oauth_states: dict[str, OAuthState] = {}

        # Authorization code storage (code -> (session_id, expires_at))
        self._auth_codes: dict[str, tuple[str, float]] = {}

        self._lock = asyncio.Lock()

        # Track initialization state
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the session manager and underlying storage."""
        if self._initialized:
            return

        if self.token_store:
            await self.token_store.initialize()
            logger.info("SessionManager initialized with persistent storage")
        else:
            logger.info("SessionManager initialized with in-memory storage only")

        self._initialized = True

    async def close(self) -> None:
        """Close the session manager and release resources."""
        if self.token_store:
            await self.token_store.close()
            logger.info("SessionManager closed")

    async def create_session(
        self,
        client_id: str,
        provider_token: str | None = None,
        provider_refresh_token: str | None = None,
        scopes: list[str] | None = None,
        expires_in: int | None = None,
    ) -> Session:
        """Create a new authenticated session.

        Args:
            client_id: The OAuth client ID.
            provider_token: The provider's access token.
            provider_refresh_token: The provider's refresh token.
            scopes: List of granted scopes.
            expires_in: Token lifetime in seconds (uses default if None).

        Returns:
            The newly created Session.
        """
        effective_expires_in = expires_in if expires_in is not None else self.default_token_lifetime

        session = Session.create(
            client_id=client_id,
            provider_token=provider_token,
            provider_refresh_token=provider_refresh_token,
            scopes=scopes,
            expires_in=effective_expires_in,
        )

        async with self._lock:
            # Store in memory cache
            self._sessions[session.mxcp_token_hash] = session
            self._token_to_hash[session.mxcp_token] = session.mxcp_token_hash

            # Persist if storage is available
            if self.token_store:
                await self.token_store.store_session(session)

        logger.info(f"Created session for client: {client_id}")
        return session

    async def get_session(self, mxcp_token: str) -> Session | None:
        """Get a session by MXCP token.

        Args:
            mxcp_token: The MXCP access token.

        Returns:
            The Session if found and valid, None otherwise.
        """
        token_hash = Session.hash_token(mxcp_token)

        async with self._lock:
            # Check memory cache first
            session = self._sessions.get(token_hash)

            # If not in cache, try loading from storage
            if session is None and self.token_store:
                session = await self.token_store.load_session_by_token_hash(token_hash)
                if session:
                    # Populate cache
                    self._sessions[token_hash] = session
                    self._token_to_hash[session.mxcp_token] = token_hash

            if session is None:
                return None

            # Check expiry
            if session.is_expired():
                await self._delete_session_internal(session)
                return None

            # Update last accessed
            session.touch()

            return session

    async def get_provider_token(self, mxcp_token: str) -> str | None:
        """Get the provider token for an MXCP token.

        This is the primary method for middleware to retrieve the external
        provider token needed for user context fetching.

        Args:
            mxcp_token: The MXCP access token.

        Returns:
            The provider's access token if found, None otherwise.
        """
        session = await self.get_session(mxcp_token)
        if session:
            return session.provider_token
        return None

    async def delete_session(self, mxcp_token: str) -> bool:
        """Delete a session by MXCP token.

        Args:
            mxcp_token: The MXCP access token.

        Returns:
            True if session was deleted, False if not found.
        """
        session = await self.get_session(mxcp_token)
        if session:
            await self._delete_session_internal(session)
            return True
        return False

    async def _delete_session_internal(self, session: Session) -> None:
        """Internal method to delete a session from cache and storage.

        Args:
            session: The session to delete.
        """
        # Remove from memory cache
        self._sessions.pop(session.mxcp_token_hash, None)
        self._token_to_hash.pop(session.mxcp_token, None)

        # Remove from persistent storage
        if self.token_store:
            await self.token_store.delete_session(session.session_id)

        logger.debug(f"Deleted session: {session.session_id}")

    async def cleanup_expired_sessions(self) -> int:
        """Remove all expired sessions.

        Returns:
            Number of sessions removed.
        """
        deleted_count = 0

        async with self._lock:
            # Clean up in-memory sessions
            expired_hashes = [
                token_hash
                for token_hash, session in self._sessions.items()
                if session.is_expired()
            ]

            for token_hash in expired_hashes:
                session = self._sessions.pop(token_hash, None)
                if session:
                    self._token_to_hash.pop(session.mxcp_token, None)
                    deleted_count += 1

            # Clean up persistent storage
            if self.token_store:
                storage_deleted = await self.token_store.cleanup_expired_sessions()
                # Note: storage_deleted may include sessions not in memory cache
                deleted_count = max(deleted_count, storage_deleted)

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired sessions")

        return deleted_count

    # ─────────────────────────────────────────────────────────────────────────
    # OAuth State Management
    # ─────────────────────────────────────────────────────────────────────────

    def create_oauth_state(
        self,
        client_id: str,
        redirect_uri: str,
        callback_url: str,
        code_challenge: str | None = None,
        code_verifier: str | None = None,
        redirect_uri_provided_explicitly: bool = True,
        provider: str | None = None,
        scopes: list[str] | None = None,
        expires_in: int = 600,
    ) -> OAuthState:
        """Create and store a new OAuth state for authorization flow.

        Args:
            client_id: The MCP client ID.
            redirect_uri: The client's redirect URI.
            callback_url: The MXCP callback URL.
            code_challenge: PKCE code challenge.
            code_verifier: PKCE code verifier.
            redirect_uri_provided_explicitly: Whether redirect was explicit.
            provider: The OAuth provider name.
            scopes: Requested scopes.
            expires_in: State lifetime in seconds.

        Returns:
            The created OAuthState with generated state parameter.
        """
        state_value = secrets.token_hex(16)
        now = time.time()

        oauth_state = OAuthState(
            state=state_value,
            client_id=client_id,
            redirect_uri=redirect_uri,
            callback_url=callback_url,
            code_challenge=code_challenge,
            code_verifier=code_verifier,
            redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
            provider=provider,
            scopes=scopes or [],
            created_at=now,
            expires_at=now + expires_in,
        )

        self._oauth_states[state_value] = oauth_state
        logger.debug(f"Created OAuth state for client: {client_id}")
        return oauth_state

    def get_oauth_state(self, state: str) -> OAuthState | None:
        """Get OAuth state by state parameter.

        Args:
            state: The state parameter from the callback.

        Returns:
            The OAuthState if found and not expired, None otherwise.
        """
        oauth_state = self._oauth_states.get(state)

        if oauth_state is None:
            return None

        if oauth_state.is_expired():
            self._oauth_states.pop(state, None)
            logger.warning(f"OAuth state expired: {state[:8]}...")
            return None

        return oauth_state

    def consume_oauth_state(self, state: str) -> OAuthState | None:
        """Get and remove OAuth state (one-time use).

        Args:
            state: The state parameter from the callback.

        Returns:
            The OAuthState if found and valid, None otherwise.
        """
        oauth_state = self.get_oauth_state(state)
        if oauth_state:
            self._oauth_states.pop(state, None)
        return oauth_state

    def cleanup_expired_oauth_states(self) -> int:
        """Remove expired OAuth states.

        Returns:
            Number of states removed.
        """
        expired = [
            state for state, oauth_state in self._oauth_states.items()
            if oauth_state.is_expired()
        ]
        for state in expired:
            self._oauth_states.pop(state, None)

        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired OAuth states")

        return len(expired)

    # ─────────────────────────────────────────────────────────────────────────
    # Authorization code operations (for OAuth code → token exchange)
    # ─────────────────────────────────────────────────────────────────────────

    def store_auth_code(
        self,
        code: str,
        session_id: str,
        expires_in: int = 600,
    ) -> None:
        """Store an authorization code mapped to a session.

        Authorization codes are short-lived, one-time use tokens that clients
        exchange for access tokens in the OAuth flow.

        Args:
            code: The authorization code.
            session_id: The session ID this code will resolve to.
            expires_in: Code lifetime in seconds (default 10 minutes).
        """
        expires_at = time.time() + expires_in
        self._auth_codes[code] = (session_id, expires_at)
        logger.debug(f"Stored auth code for session: {session_id[:8]}...")

    def get_auth_code(self, code: str) -> str | None:
        """Get the session ID for an authorization code.

        Does NOT consume the code - use consume_auth_code for one-time retrieval.

        Args:
            code: The authorization code.

        Returns:
            The session ID if code is valid and not expired, None otherwise.
        """
        entry = self._auth_codes.get(code)
        if entry is None:
            return None

        session_id, expires_at = entry
        if time.time() > expires_at:
            self._auth_codes.pop(code, None)
            logger.warning(f"Auth code expired: {code[:8]}...")
            return None

        return session_id

    def consume_auth_code(self, code: str) -> str | None:
        """Get and remove an authorization code (one-time use).

        Args:
            code: The authorization code.

        Returns:
            The session ID if code was valid, None otherwise.
        """
        session_id = self.get_auth_code(code)
        if session_id:
            self._auth_codes.pop(code, None)
            logger.debug(f"Consumed auth code for session: {session_id[:8]}...")
        return session_id

    def cleanup_expired_auth_codes(self) -> int:
        """Remove expired authorization codes.

        Returns:
            Number of codes removed.
        """
        now = time.time()
        expired = [
            code for code, (_, expires_at) in self._auth_codes.items()
            if now > expires_at
        ]
        for code in expired:
            self._auth_codes.pop(code, None)

        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired auth codes")

        return len(expired)


