import asyncio
import concurrent.futures
import contextlib
import functools
import hashlib
import json
import logging
import os
import re
import signal
import threading
import time
import traceback
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar, cast

from makefun import create_function
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl, Field, create_model
from starlette.responses import JSONResponse

from mxcp.sdk.audit import AuditLogger
from mxcp.sdk.auth import ExternalOAuthHandler, GeneralOAuthAuthorizationServer
from mxcp.sdk.auth._types import HttpTransportConfig
from mxcp.sdk.auth.context import get_user_context
from mxcp.sdk.auth.middleware import AuthenticationMiddleware
from mxcp.sdk.auth.providers.atlassian import AtlassianOAuthHandler
from mxcp.sdk.auth.providers.github import GitHubOAuthHandler
from mxcp.sdk.auth.providers.google import GoogleOAuthHandler
from mxcp.sdk.auth.providers.keycloak import KeycloakOAuthHandler
from mxcp.sdk.auth.providers.salesforce import SalesforceOAuthHandler
from mxcp.sdk.auth.url_utils import URLBuilder
from mxcp.sdk.core import PACKAGE_VERSION
from mxcp.sdk.executor import ExecutionContext
from mxcp.sdk.telemetry import (
    decrement_gauge,
    get_current_trace_id,
    increment_gauge,
    record_counter,
    set_span_attribute,
)
from mxcp.server.admin import AdminAPIRunner
from mxcp.server.core.config._types import (
    SiteConfig,
    UserAuthConfig,
    UserConfig,
    UserHttpTransportConfig,
)
from mxcp.server.core.config.site_config import get_active_profile, load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.core.refs.external import ExternalRefTracker
from mxcp.server.core.reload import ReloadManager, ReloadRequest
from mxcp.server.core.telemetry import configure_telemetry_from_config, shutdown_telemetry
from mxcp.server.definitions.endpoints._types import (
    ParamDefinition,
    PromptDefinition,
    ResourceDefinition,
    ToolDefinition,
)
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.definitions.endpoints.utils import EndpointType
from mxcp.server.executor.engine import RuntimeEnvironment, create_runtime_environment
from mxcp.server.interfaces.cli.utils import (
    get_env_admin_socket_enabled,
    get_env_admin_socket_path,
)
from mxcp.server.schemas.audit import ENDPOINT_EXECUTION_SCHEMA
from mxcp.server.services.endpoints import (
    execute_endpoint_with_engine,
    execute_endpoint_with_engine_and_policy,
)
from mxcp.server.services.endpoints.validator import validate_endpoint

logger = logging.getLogger(__name__)

# Type variable for the decorator
T = TypeVar("T", bound=Callable[..., Awaitable[Any]])


def with_draining_and_request_tracking(func: T) -> T:
    """Decorator that handles draining wait and request counter tracking.

    This decorator wraps async methods to:
    1. Wait while draining is in progress
    2. Increment active request counter
    3. Execute the wrapped method
    4. Decrement the counter in finally block

    The wrapped method must be a method of a class that has:
    - self.draining (bool)
    - self.active_requests (int)
    - self.requests_lock (threading.Lock)
    """

    @functools.wraps(func)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        # Wait if draining is in progress, then atomically register this request.
        # The check and increment must be atomic to prevent requests from being
        # registered after draining has started checking for zero active requests.
        wait_start = time.time()
        wait_timeout = 30  # seconds

        while True:
            # Atomically check draining flag and register request if not draining
            with self.requests_lock:
                if not self.draining:
                    # Safe to register - draining hasn't started or has finished
                    self.active_requests += 1
                    break

            # Draining is in progress, wait and retry
            if time.time() - wait_start > wait_timeout:
                raise RuntimeError(
                    "Service is reloading and taking longer than expected. Please retry in a few seconds."
                )
            await asyncio.sleep(0.1)

        try:
            return await func(self, *args, **kwargs)
        finally:
            # Decrement request counter
            with self.requests_lock:
                self.active_requests -= 1

    return cast(T, wrapper)


def translate_transport_config(
    user_transport_config: UserHttpTransportConfig | None,
) -> HttpTransportConfig | None:
    """Translate user HTTP transport config to SDK transport config.

    Args:
        user_transport_config: User configuration transport section

    Returns:
        SDK-compatible HTTP transport configuration
    """
    if not user_transport_config:
        return None

    return {
        "port": user_transport_config.get("port"),
        "host": user_transport_config.get("host"),
        "scheme": user_transport_config.get("scheme"),
        "base_url": user_transport_config.get("base_url"),
        "trust_proxy": user_transport_config.get("trust_proxy"),
        "stateless": user_transport_config.get("stateless"),
    }


def create_oauth_handler(
    user_auth_config: UserAuthConfig,
    host: str = "localhost",
    port: int = 8000,
    user_config: UserConfig | None = None,
) -> ExternalOAuthHandler | None:
    """Create an OAuth handler from user configuration.

    This helper translates user config to SDK types and instantiates the appropriate handler.

    Args:
        user_auth_config: User authentication configuration
        host: The server host to use for callback URLs
        port: The server port to use for callback URLs
        user_config: Full user configuration for transport settings (optional)

    Returns:
        OAuth handler instance or None if provider is 'none'
    """
    provider = user_auth_config.get("provider", "none")

    if provider == "none":
        return None

    # Extract transport config if available
    transport_config = None
    if user_config and "transport" in user_config:
        transport = user_config["transport"]
        user_transport = transport.get("http") if transport else None
        transport_config = translate_transport_config(user_transport)

    if provider == "github":

        github_config = user_auth_config.get("github")
        if not github_config:
            raise ValueError("GitHub provider selected but no GitHub configuration found")
        return GitHubOAuthHandler(github_config, transport_config, host=host, port=port)

    elif provider == "atlassian":

        atlassian_config = user_auth_config.get("atlassian")
        if not atlassian_config:
            raise ValueError("Atlassian provider selected but no Atlassian configuration found")
        return AtlassianOAuthHandler(atlassian_config, transport_config, host=host, port=port)

    elif provider == "salesforce":

        salesforce_config = user_auth_config.get("salesforce")
        if not salesforce_config:
            raise ValueError("Salesforce provider selected but no Salesforce configuration found")
        return SalesforceOAuthHandler(salesforce_config, transport_config, host=host, port=port)

    elif provider == "keycloak":

        keycloak_config = user_auth_config.get("keycloak")
        if not keycloak_config:
            raise ValueError("Keycloak provider selected but no Keycloak configuration found")
        return KeycloakOAuthHandler(keycloak_config, transport_config, host=host, port=port)

    elif provider == "google":

        google_config = user_auth_config.get("google")
        if not google_config:
            raise ValueError("Google provider selected but no Google configuration found")
        return GoogleOAuthHandler(google_config, transport_config, host=host, port=port)

    else:
        raise ValueError(f"Unsupported auth provider: {provider}")


def create_url_builder(user_config: UserConfig) -> URLBuilder:
    """Create a URL builder from user configuration.

    Args:
        user_config: User configuration dictionary

    Returns:
        Configured URLBuilder instance
    """
    transport = user_config.get("transport", {})
    user_transport_config = transport.get("http", {}) if transport else {}
    transport_config = translate_transport_config(user_transport_config)
    return URLBuilder(transport_config)


class RAWMCP:
    """MXCP MCP Server implementation that bridges MXCP endpoints with MCP protocol."""

    # Type annotations for instance attributes
    site_config: SiteConfig
    user_config: UserConfig
    _site_config_template: SiteConfig
    _user_config_template: UserConfig
    host: str
    port: int
    profile_name: str
    transport: str
    readonly: bool
    _model_cache: dict[str, Any]
    transport_mode: str | None

    def __init__(
        self,
        site_config_path: Path | None = None,
        profile: str | None = None,
        transport: str | None = None,
        host: str | None = None,
        port: int | None = None,
        stateless_http: bool | None = None,
        json_response: bool = False,
        enable_sql_tools: bool | None = None,
        readonly: bool = False,
        debug: bool = False,
    ):
        """Initialize the MXCP MCP server.

        The server loads configuration templates from disk to enable external reference
        tracking and hot reloading. Configuration templates are loaded with resolve_refs=False,
        meaning external references (${ENV_VAR}, vault://, file://) remain as strings.
        These templates are then resolved using selective interpolation - only resolving
        references for the active profile and top-level config, preventing errors from
        undefined environment variables in inactive profiles.

        Command-line options override config file settings.

        Args:
            site_config_path: Optional path to find mxcp-site.yml. Defaults to current directory.
                             Used for both initial load and hot reload functionality.
            profile: Optional profile name to use. Overrides the profile from site config.
            transport: Optional transport override. Defaults to user config setting.
            host: Optional host override. Defaults to user config setting.
            port: Optional port override. Defaults to user config setting.
            stateless_http: Optional stateless mode override. Defaults to user config setting.
            json_response: Whether to use JSON responses instead of SSE
            enable_sql_tools: Optional SQL tools override. Defaults to site config setting.
            readonly: Whether to open DuckDB connection in read-only mode
            debug: Enable debug logging
        """
        # Store the path for hot reload
        self.site_config_path = site_config_path or Path.cwd()
        self.debug = debug

        # Server runtime metadata
        self._start_time = datetime.now(timezone.utc)
        self._pid = os.getpid()

        # Load configuration templates from disk (unresolved for external reference tracking)
        logger.info("Loading configuration templates...")
        logger.debug(f"Loading from {self.site_config_path}")

        # Templates are loaded with resolve_refs=False, keeping external references as strings
        # e.g., "${MY_VAR}", "vault://secret/path", "file://config.json"
        # This enables:
        # 1. External reference tracking for hot reload
        # 2. File change detection
        # 3. Selective interpolation (only active profile + top-level)
        self._site_config_template = load_site_config(self.site_config_path)
        self._user_config_template = load_user_config(
            self._site_config_template, resolve_refs=False
        )

        # Store command-line overrides
        self._cli_overrides = {
            "profile": profile,
            "transport": transport,
            "host": host,
            "port": port,
            "stateless_http": stateless_http,
            "enable_sql_tools": enable_sql_tools,
            "readonly": readonly,
            "json_response": json_response,
        }

        # Initialize external reference tracker for hot reload
        self.ref_tracker = ExternalRefTracker()

        # Initialize reload manager
        self.reload_manager = ReloadManager(self)

        # Initialize runtime environment (will be created in initialize_runtime_components)
        self.runtime_environment: RuntimeEnvironment | None = None
        self._model_cache = {}

        # Public attributes for admin API
        self.telemetry_enabled: bool = False
        self.audit_logger: Any | None = None

        # Resolve configurations
        self._resolve_and_apply_configs()

        # Initialize telemetry
        self._initialize_telemetry()

        # Initialize runtime components
        self.initialize_runtime_components()

        # Initialize OAuth authentication
        self._initialize_oauth()

        # Initialize FastMCP
        self._initialize_fastmcp()

        # Load and validate endpoints
        self._load_endpoints()

        # Initialize audit logger
        self._initialize_audit_logger()

        # Track transport mode and other state
        self.transport_mode = None
        self._shutdown_called = False

        # Request tracking for safe reloading
        self.active_requests = 0
        self.requests_lock = threading.Lock()
        self.draining = False

        # Initialize admin API (but don't start yet - will be started in run())
        self.admin_api = AdminAPIRunner(
            server=self,
            socket_path=get_env_admin_socket_path(),
            enabled=get_env_admin_socket_enabled(),
        )

        # Register signal handlers
        self._register_signal_handlers()

    def _resolve_and_apply_configs(self) -> None:
        """Resolve external references with selective interpolation and apply CLI overrides.

        External references (${ENV_VAR}, vault://, file://) are resolved using selective
        interpolation, which only resolves references for the active profile and top-level
        config. This prevents errors from undefined environment variables in inactive profiles.
        """
        # Check if configs contain unresolved references
        config_str = json.dumps(self._site_config_template) + json.dumps(self._user_config_template)
        needs_resolution = any(pattern in config_str for pattern in ["${", "vault://", "file://"])

        # Determine active profile (CLI override > site config)
        active_profile = str(
            self._cli_overrides["profile"] or self._site_config_template["profile"]
        )
        project_name = self._site_config_template["project"]

        if needs_resolution:
            # Set templates and resolve with selective interpolation
            logger.info(
                f"Resolving external configuration references for project={project_name}, profile={active_profile}..."
            )
            self.ref_tracker.set_template(
                cast(dict[str, Any], self._site_config_template),
                cast(dict[str, Any], self._user_config_template),
            )
            self._config_templates_loaded = True

            # Use selective interpolation - only resolve active profile + top-level config
            resolved_site, resolved_user = self.ref_tracker.resolve_all(
                project_name=project_name,
                profile_name=active_profile,
            )
            self.site_config = cast(SiteConfig, resolved_site)
            self.user_config = cast(UserConfig, resolved_user)
        else:
            # Already resolved
            self.site_config = self._site_config_template
            self.user_config = self._user_config_template
            self._config_templates_loaded = False

        # Store resolved profile name
        self.profile_name = active_profile
        self.active_profile = get_active_profile(
            self.user_config, self.site_config, self.profile_name
        )

        # Extract transport config with overrides
        transport_config = self.user_config.get("transport") or {}
        self.transport = str(
            self._cli_overrides["transport"]
            or (transport_config.get("provider") if transport_config else "streamable-http")
            or "streamable-http"
        )

        http_config = transport_config.get("http") if transport_config else {}
        self.host = str(
            self._cli_overrides["host"]
            or (http_config.get("host") if http_config else "localhost")
            or "localhost"
        )
        port_value = (
            self._cli_overrides["port"]
            or (http_config.get("port") if http_config else 8000)
            or 8000
        )
        self.port = int(port_value)

        config_stateless = http_config.get("stateless", False) if http_config else False
        self.stateless_http = (
            self._cli_overrides["stateless_http"]
            if self._cli_overrides["stateless_http"] is not None
            else config_stateless
        )

        self.json_response = self._cli_overrides["json_response"]
        self.readonly = bool(self._cli_overrides["readonly"])

        # SQL tools setting
        sql_tools_config = self.site_config.get("sql_tools") or {}
        site_sql_tools = sql_tools_config.get("enabled", False) if sql_tools_config else False
        self.enable_sql_tools = (
            self._cli_overrides["enable_sql_tools"]
            if self._cli_overrides["enable_sql_tools"] is not None
            else site_sql_tools
        )

    def get_endpoint_counts(self) -> dict[str, int]:
        """Get counts of valid endpoints by type."""
        tool_count = sum(
            1
            for _, endpoint, error in self._all_endpoints
            if error is None and endpoint is not None and "tool" in endpoint
        )
        resource_count = sum(
            1
            for _, endpoint, error in self._all_endpoints
            if error is None and endpoint is not None and "resource" in endpoint
        )
        prompt_count = sum(
            1
            for _, endpoint, error in self._all_endpoints
            if error is None and endpoint is not None and "prompt" in endpoint
        )

        return {
            "tools": tool_count,
            "resources": resource_count,
            "prompts": prompt_count,
            "total": tool_count + resource_count + prompt_count,
        }

    def _load_endpoints(self) -> None:
        """Load and categorize endpoints."""

        self.loader = EndpointLoader(self.site_config)

        # Store all endpoints for reference
        self._all_endpoints = self.loader.discover_endpoints()

        # Split into valid and failed
        self.endpoints = [
            (path, endpoint) for path, endpoint, error in self._all_endpoints if error is None
        ]
        self.skipped_endpoints = [
            {"path": str(path), "error": error}
            for path, _, error in self._all_endpoints
            if error is not None
        ]

        # Log results
        logger.info(
            f"Discovered {len(self.endpoints)} valid endpoints, {len(self.skipped_endpoints)} failed endpoints"
        )
        if self.skipped_endpoints:
            for skipped in self.skipped_endpoints:
                logger.warning(f"Failed to load endpoint {skipped['path']}: {skipped['error']}")

    def _initialize_oauth(self) -> None:
        """Initialize OAuth authentication using profile-specific auth config."""
        auth_config = self.active_profile.get("auth", {})
        self.oauth_handler = create_oauth_handler(
            auth_config,
            host=self.host,
            port=self.port,
            user_config=self.user_config,
        )
        self.oauth_server = None
        self.auth_settings = None

        if self.oauth_handler:
            self.oauth_server = GeneralOAuthAuthorizationServer(
                self.oauth_handler, auth_config, cast(dict[str, Any], self.user_config)
            )

            # Use URL builder for OAuth endpoints
            url_builder = create_url_builder(self.user_config)
            base_url = url_builder.get_base_url(host=self.host, port=self.port)

            # Get authorization configuration
            auth_authorization = auth_config.get("authorization", {})
            required_scopes = auth_authorization.get("required_scopes", [])

            logger.info(
                f"Authorization configured - required scopes: {required_scopes or 'none (authentication only)'}"
            )

            self.auth_settings = AuthSettings(
                issuer_url=cast(AnyHttpUrl, base_url),
                resource_server_url=None,
                client_registration_options=ClientRegistrationOptions(
                    enabled=True,
                    valid_scopes=None,  # Accept any scope
                    default_scopes=required_scopes if required_scopes else None,
                ),
                required_scopes=required_scopes if required_scopes else None,
            )
            logger.info(
                f"OAuth authentication enabled with provider: {auth_config.get('provider')}"
            )
        else:
            logger.info("OAuth authentication disabled")

    def _initialize_fastmcp(self) -> None:
        """Initialize the FastMCP server."""
        fastmcp_kwargs: dict[str, Any] = {
            "name": "MXCP Server",
            "stateless_http": self.stateless_http,
            "json_response": self.json_response,
            "host": self.host,
            "port": self.port,
        }

        logger.info(f"Initializing FastMCP with host={self.host}, port={self.port}")

        if self.auth_settings and self.oauth_server:
            fastmcp_kwargs["auth"] = self.auth_settings
            fastmcp_kwargs["auth_server_provider"] = self.oauth_server

        self.mcp = FastMCP(**fastmcp_kwargs)

        # Initialize authentication middleware
        self.auth_middleware = AuthenticationMiddleware(self.oauth_handler, self.oauth_server)

        # Register OAuth routes if enabled
        if self.oauth_handler and self.oauth_server:
            self._register_oauth_routes()

    def _initialize_audit_logger(self) -> None:
        """Initialize audit logger if enabled."""

        profile_config = self.site_config["profiles"][self.profile_name]
        audit_config = profile_config.get("audit") or {}
        if audit_config and audit_config.get("enabled", False):
            log_path_str = audit_config.get("path", "")
            log_path = Path(log_path_str) if log_path_str else Path("audit.log")
            # Ensure parent directory exists
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self.audit_logger = asyncio.run(AuditLogger.jsonl(log_path))
            # Register the endpoint execution schema
            asyncio.run(self._register_audit_schema())
        else:
            self.audit_logger = asyncio.run(AuditLogger.disabled())

    async def _register_audit_schema(self) -> None:
        """Register the application's audit schema."""
        if not self.audit_logger:
            return

        try:
            # Check if schema already exists
            existing = await self.audit_logger.get_schema(
                ENDPOINT_EXECUTION_SCHEMA.schema_name, ENDPOINT_EXECUTION_SCHEMA.version
            )
            if not existing:
                await self.audit_logger.create_schema(ENDPOINT_EXECUTION_SCHEMA)
                logger.info(f"Registered audit schema: {ENDPOINT_EXECUTION_SCHEMA.get_schema_id()}")
        except Exception as e:
            logger.warning(f"Failed to register audit schema: {e}")

    def _register_signal_handlers(self) -> None:
        """Register signal handlers for graceful shutdown and reload."""
        if hasattr(signal, "SIGHUP"):
            # SIGHUP triggers a full system reload
            signal.signal(signal.SIGHUP, self._handle_reload_signal)
            logger.info("Registered SIGHUP handler for system reload.")

        # Handle SIGTERM (e.g., from `kill`) and SIGINT (e.g., from Ctrl+C)
        signal.signal(signal.SIGTERM, self._handle_exit_signal)
        signal.signal(signal.SIGINT, self._handle_exit_signal)

    def _handle_exit_signal(self, signum: int, frame: Any) -> None:
        """Handle termination signals to ensure graceful shutdown."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown()

    def _handle_reload_signal(self, signum: int, frame: Any) -> None:
        """Handle SIGHUP signal to reload the configuration."""
        logger.info("Received SIGHUP signal, initiating configuration reload...")

        # Request configuration reload and wait for it to complete
        request = self.reload_configuration()

        # Wait for the reload to complete
        completed = request.wait_for_completion(timeout=60.0)  # 60 second timeout

        if completed:
            logger.info("SIGHUP reload completed successfully")
        else:
            logger.error("SIGHUP reload timed out after 60 seconds")

    def shutdown_runtime_components(self) -> None:
        """
        Gracefully shuts down all reloadable, configuration-dependent components.
        Uses the new SDK execution engine which handles all shutdown hooks automatically.

        This does NOT affect the authentication provider or endpoint registrations.
        """
        logger.info("Shutting down runtime components...")

        # Shut down runtime environment (handles all executor-specific shutdown including plugins)
        if self.runtime_environment:
            self.runtime_environment.shutdown()
            self.runtime_environment = None

        logger.info("Runtime components shutdown complete.")

    def initialize_runtime_components(self) -> None:
        """
        Initializes runtime components using the new SDK execution engine.
        """
        logger.info("Initializing runtime components...")

        # Create runtime environment (contains execution engine + shared resources)
        logger.info("Creating runtime environment...")
        self.runtime_environment = create_runtime_environment(
            self.user_config, self.site_config, self.profile_name, readonly=self.readonly
        )
        logger.info("Runtime environment created.")

        # Cache for dynamically created models
        self._model_cache = {}

        logger.info("Runtime components initialization complete.")

    def _initialize_telemetry(self) -> None:
        """Initialize telemetry based on user config settings."""
        logger.info("Initializing telemetry...")

        # Get project name from site config
        project_name = self.site_config["project"]

        # Configure telemetry for the current profile and get enabled status
        self.telemetry_enabled = configure_telemetry_from_config(
            self.user_config, project_name, self.profile_name
        )

        # Record system startup metrics
        record_counter(
            "mxcp.up",
            attributes={
                "version": PACKAGE_VERSION,
                "profile": self.profile_name,
                "project": project_name,
                "transport": getattr(self, "transport_mode", None) or "unknown",
            },
            description="MXCP server startup counter",
        )

        logger.info("Telemetry initialization complete.")

    def reload_configuration(self) -> "ReloadRequest":
        """
        Request a full system reload.

        Typically triggered by SIGHUP signal. The reload will:
        1. Drain active requests
        2. Shutdown runtime components
        3. Reload configuration from disk
        4. Restart runtime components
        """
        # Ensure we have raw templates for external reference tracking
        if not self._config_templates_loaded or not self.ref_tracker._template_config:
            logger.info("Loading raw configuration templates for hot reload...")

            # Determine site config path
            site_path = self.site_config_path or Path.cwd()

            # Load raw templates
            site_template = load_site_config(site_path)
            user_template = load_user_config(site_template, resolve_refs=False)

            # Set templates in tracker
            self.ref_tracker.set_template(
                cast(dict[str, Any], site_template), cast(dict[str, Any], user_template)
            )
            self._config_templates_loaded = True
            logger.info("Raw configuration templates loaded.")

        # Define payload to reload config from disk
        def reload_config_files() -> None:
            """Reload configuration files from disk."""
            logger.info("Reloading configuration files...")

            # Reload site config
            site_path = self.site_config_path or Path.cwd()
            new_site_template = load_site_config(site_path)
            new_user_template = load_user_config(new_site_template, resolve_refs=False)

            # Update templates in tracker
            self.ref_tracker.set_template(
                cast(dict[str, Any], new_site_template), cast(dict[str, Any], new_user_template)
            )

            # Resolve and update configs
            new_site_config, new_user_config = self.ref_tracker.resolve_all()
            self.site_config = cast(SiteConfig, new_site_config)
            self.user_config = cast(UserConfig, new_user_config)

            logger.info("Configuration files reloaded")

        # Request a reload with config reload as payload
        return self.reload_manager.request_reload(
            payload_func=reload_config_files, description="Configuration reload (SIGHUP)"
        )

    def _ensure_async_completes(
        self, coro: Any, timeout: float = 10.0, operation_name: str = "operation"
    ) -> Any:
        """Ensure an async operation completes, even when called from sync context with active event loop.

        This method safely runs an async operation from a synchronous context, handling the case
        where there's already an event loop running in the current thread (which would cause
        a deadlock if we tried to use asyncio.run()).

        Args:
            coro: The coroutine to run
            timeout: Timeout in seconds
            operation_name: Name of the operation for logging

        Raises:
            TimeoutError: If the operation times out
            Exception: If the operation fails
        """

        async def with_timeout() -> Any:
            """Wrap the coroutine with a timeout."""
            return await asyncio.wait_for(coro, timeout=timeout)

        # Check if there's an active event loop in the current thread
        try:
            asyncio.get_running_loop()
            # There is an active loop - we must run in a separate thread to avoid deadlock
            logger.info(f"Running {operation_name} with active event loop - using separate thread")

            def run_in_new_loop() -> Any:
                """Run the coroutine in a new event loop in this thread."""
                # asyncio.run() creates a new event loop, runs the coroutine, and cleans up
                return asyncio.run(with_timeout())

            # Execute in a separate thread
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_in_new_loop)
                try:
                    final_type = future.result(
                        timeout=timeout + 1
                    )  # Add buffer for thread overhead
                    logger.info(f"{operation_name} completed successfully")
                    return final_type
                except concurrent.futures.TimeoutError:
                    # The thread itself timed out - this is a fatal error
                    raise TimeoutError(
                        f"{operation_name} thread timed out after {timeout + 1} seconds"
                    ) from None
                except asyncio.TimeoutError:
                    # The asyncio.wait_for timed out (this gets wrapped in the future)
                    raise TimeoutError(
                        f"{operation_name} timed out after {timeout} seconds"
                    ) from None
                except Exception as e:
                    logger.error(f"{operation_name} failed: {e}")
                    raise

        except RuntimeError:
            # No event loop running, we can run directly
            logger.info(f"Running {operation_name} without active event loop - using asyncio.run")
            try:
                result = asyncio.run(with_timeout())
                logger.info(f"{operation_name} completed successfully")
                return result
            except asyncio.TimeoutError:
                raise TimeoutError(f"{operation_name} timed out after {timeout} seconds") from None
            except Exception as e:
                logger.error(f"{operation_name} failed: {e}")
                raise

    def shutdown(self) -> None:
        """Shutdown the server gracefully."""
        # Prevent double shutdown
        if self._shutdown_called:
            return
        self._shutdown_called = True

        logger.info("Shutting down MXCP server...")

        try:
            # Stop the admin API first
            self._ensure_async_completes(
                self.admin_api.stop(),
                timeout=5.0,
                operation_name="Admin API shutdown",
            )

            # Stop the reload manager
            self.reload_manager.stop()

            # Gracefully shut down the reloadable runtime components first
            # This handles python runtimes, plugins, and the db session.
            self.shutdown_runtime_components()

            # Close OAuth server persistence - ensure it completes
            if self.oauth_server:
                try:
                    self._ensure_async_completes(
                        self.oauth_server.close(),
                        timeout=5.0,
                        operation_name="OAuth server shutdown",
                    )
                except Exception as e:
                    logger.error(f"Error closing OAuth server: {e}")
                    # Continue with shutdown even if OAuth server close fails

            # Shutdown audit logger if initialized
            if self.audit_logger:
                try:
                    self.audit_logger.shutdown()
                    logger.info("Closed audit logger")
                except Exception as e:
                    logger.error(f"Error closing audit logger: {e}")

            # Shutdown telemetry
            try:
                shutdown_telemetry()
                logger.info("Shutdown telemetry")
            except Exception as e:
                logger.error(f"Error shutting down telemetry: {e}")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            logger.info("MXCP server shutdown complete")

    def _sanitize_model_name(self, name: str) -> str:
        """Sanitize a name to be a valid Python class name."""
        # Replace non-alphanumeric characters with underscores
        name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        # Ensure it starts with a letter or underscore
        if name and name[0].isdigit():
            name = f"_{name}"
        # Capitalize first letter for class name convention
        return name.title().replace("_", "")

    def _create_pydantic_model_from_schema(
        self,
        schema_def: dict[str, Any],
        model_name: str,
        endpoint_type: EndpointType | None = None,
    ) -> Any:  # Returns types that can be used in type annotations
        """Create a Pydantic model from a JSON Schema definition.

        Args:
            schema_def: JSON Schema definition
            model_name: Name for the generated model
            endpoint_type: Type of endpoint (affects whether parameters are Optional)

        Returns:
            Pydantic model class or type annotation
        """
        # Cache key for this schema (include endpoint_type to avoid conflicts)
        cache_key = f"{model_name}_{hash(json.dumps(schema_def, sort_keys=True))}_{endpoint_type}"
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        json_type = schema_def.get("type", "string")

        # Declare variable with explicit type annotation
        final_type: Any

        # Determine if parameters should be nullable (tools/prompts parameters can be null)
        # or not (resources templates cannot get null arguments)
        make_nullable = endpoint_type in (EndpointType.TOOL, EndpointType.PROMPT)

        # Handle primitive types
        if json_type == "string":
            # Handle enums
            if "enum" in schema_def:
                enum_values = schema_def["enum"]
                if all(isinstance(v, str) for v in enum_values):
                    # For enums, we'll use a simple str type with validation
                    # Since we can't dynamically create Literal unions in a type-safe way
                    if make_nullable:
                        final_type = str | None
                    else:
                        final_type = str
                    self._model_cache[cache_key] = final_type
                    return final_type

            # Create Field with constraints
            field_kwargs = self._extract_field_constraints(schema_def)
            if field_kwargs:
                if make_nullable:
                    final_type = Annotated[str | None, Field(**field_kwargs)]
                else:
                    final_type = Annotated[str, Field(**field_kwargs)]
            else:
                if make_nullable:
                    final_type = str | None
                else:
                    final_type = str
            self._model_cache[cache_key] = final_type
            return final_type

        elif json_type == "integer":
            field_kwargs = self._extract_field_constraints(schema_def)
            if field_kwargs:
                if make_nullable:
                    final_type = Annotated[int | None, Field(**field_kwargs)]
                else:
                    final_type = Annotated[int, Field(**field_kwargs)]
            else:
                if make_nullable:
                    final_type = int | None
                else:
                    final_type = int
            self._model_cache[cache_key] = final_type
            return final_type

        elif json_type == "number":
            field_kwargs = self._extract_field_constraints(schema_def)
            if field_kwargs:
                if make_nullable:
                    final_type = Annotated[float | None, Field(**field_kwargs)]
                else:
                    final_type = Annotated[float, Field(**field_kwargs)]
            else:
                if make_nullable:
                    final_type = float | None
                else:
                    final_type = float
            self._model_cache[cache_key] = final_type
            return final_type

        elif json_type == "boolean":
            field_kwargs = self._extract_field_constraints(schema_def)
            if field_kwargs:
                if make_nullable:
                    final_type = Annotated[bool | None, Field(**field_kwargs)]
                else:
                    final_type = Annotated[bool, Field(**field_kwargs)]
            else:
                if make_nullable:
                    final_type = bool | None
                else:
                    final_type = bool
            self._model_cache[cache_key] = final_type
            return final_type

        elif json_type == "array":
            items_schema = schema_def.get("items")
            if items_schema is not None:
                item_type = self._create_pydantic_model_from_schema(
                    items_schema, f"{model_name}Item", endpoint_type
                )
            else:
                # No items schema specified - use Any for maximum flexibility
                item_type = Any

            field_kwargs = self._extract_field_constraints(schema_def)
            if field_kwargs:
                # Use List with item_type as a generic parameter
                final_type = Annotated[list[item_type], Field(**field_kwargs)]  # type: ignore[valid-type]
            else:
                # Arrays without constraints
                final_type = list[item_type]  # type: ignore[valid-type]
            self._model_cache[cache_key] = final_type
            return final_type

        elif json_type == "object":
            # Handle complex objects with properties
            properties = schema_def.get("properties", {})
            required_fields = set(schema_def.get("required", []))
            # additional_properties = schema_def.get("additionalProperties", True)

            if not properties:
                # Generic object
                field_kwargs = self._extract_field_constraints(schema_def)
                if field_kwargs:
                    final_type = Annotated[dict[str, Any], Field(**field_kwargs)]
                else:
                    final_type = dict[str, Any]
                self._model_cache[cache_key] = final_type
                return final_type

            # Create fields for the model
            model_fields = {}
            for prop_name, prop_schema in properties.items():
                prop_type = self._create_pydantic_model_from_schema(
                    prop_schema,
                    f"{model_name}{self._sanitize_model_name(prop_name)}",
                    endpoint_type,
                )

                # Extract field constraints for this property
                field_kwargs = self._extract_field_constraints(prop_schema)

                # Handle required vs optional fields
                if prop_name in required_fields:
                    if field_kwargs:
                        model_fields[prop_name] = (prop_type, Field(**field_kwargs))
                    else:
                        model_fields[prop_name] = (prop_type, ...)
                else:
                    # Optional field
                    if field_kwargs:
                        model_fields[prop_name] = (prop_type | None, Field(None, **field_kwargs))
                    else:
                        model_fields[prop_name] = (prop_type | None, None)

            # Create the model with proper configuration

            # model_config = ConfigDict(extra="allow" if additional_properties else "forbid")

            # Create model with fields and config
            # Note: In Pydantic v2, __config__ is not supported in create_model
            # Instead, we create the model and then set the config
            final_type = create_model(  # type: ignore[call-overload]
                self._sanitize_model_name(model_name), **model_fields
            )

            self._model_cache[cache_key] = final_type
            return final_type

        # Fallback to Any for unknown types
        final_type = Any
        self._model_cache[cache_key] = final_type
        return final_type

    def _extract_field_constraints(self, schema_def: dict[str, Any]) -> dict[str, Any]:
        """Extract Pydantic Field constraints from JSON Schema definition."""
        field_kwargs = {}

        # Description
        if "description" in schema_def:
            field_kwargs["description"] = schema_def["description"]

        # Default value
        if "default" in schema_def:
            field_kwargs["default"] = schema_def["default"]

        # Examples
        if "examples" in schema_def and schema_def["examples"]:
            field_kwargs["examples"] = schema_def["examples"]

        # String constraints
        if "minLength" in schema_def:
            field_kwargs["min_length"] = schema_def["minLength"]
        if "maxLength" in schema_def:
            field_kwargs["max_length"] = schema_def["maxLength"]
        if "pattern" in schema_def:
            field_kwargs["pattern"] = schema_def["pattern"]

        # Numeric constraints
        if "minimum" in schema_def:
            field_kwargs["ge"] = schema_def["minimum"]
        if "maximum" in schema_def:
            field_kwargs["le"] = schema_def["maximum"]
        if "exclusiveMinimum" in schema_def:
            field_kwargs["gt"] = schema_def["exclusiveMinimum"]
        if "exclusiveMaximum" in schema_def:
            field_kwargs["lt"] = schema_def["exclusiveMaximum"]
        if "multipleOf" in schema_def:
            field_kwargs["multiple_of"] = schema_def["multipleOf"]

        # Array constraints
        if "minItems" in schema_def:
            field_kwargs["min_length"] = schema_def["minItems"]
        if "maxItems" in schema_def:
            field_kwargs["max_length"] = schema_def["maxItems"]

        return field_kwargs

    def _create_pydantic_field_annotation(
        self, param_def: ParamDefinition, endpoint_type: EndpointType | None = None
    ) -> Any:
        """Create a Pydantic type annotation from parameter definition.

        Args:
            param_def: Parameter definition from endpoint YAML
            endpoint_type: Type of endpoint (affects whether parameters are Optional)

        Returns:
            Pydantic type annotation (class or Annotated type)
        """
        param_name = param_def.get("name", "param")
        return self._create_pydantic_model_from_schema(
            cast(dict[str, Any], param_def), param_name, endpoint_type
        )

    def _json_schema_to_python_type(
        self, param_def: ParamDefinition, endpoint_type: EndpointType | None = None
    ) -> Any:
        """Convert JSON Schema type to Python type annotation.

        Args:
            param_def: Parameter definition from endpoint YAML
            endpoint_type: Type of endpoint (affects whether parameters are Optional)

        Returns:
            Python type annotation
        """
        return self._create_pydantic_field_annotation(param_def, endpoint_type)

    def _create_tool_annotations(self, tool_def: ToolDefinition) -> ToolAnnotations | None:
        """Create ToolAnnotations from tool definition.

        Args:
            tool_def: Tool definition from endpoint YAML

        Returns:
            ToolAnnotations object if annotations are present, None otherwise
        """
        annotations_data = tool_def.get("annotations", {})
        if not annotations_data:
            return None

        return ToolAnnotations(
            title=annotations_data.get("title"),
            readOnlyHint=annotations_data.get("readOnlyHint"),
            destructiveHint=annotations_data.get("destructiveHint"),
            idempotentHint=annotations_data.get("idempotentHint"),
            openWorldHint=annotations_data.get("openWorldHint"),
        )

    def _convert_param_type(self, value: Any, param_type: str) -> Any:
        """Convert parameter value to the correct type based on JSON Schema type.

        Args:
            value: The parameter value to convert
            param_type: The JSON Schema type to convert to

        Returns:
            The converted value
        """
        try:
            if value is None:
                return None
            elif param_type == "string":
                return str(value)
            elif param_type == "integer":
                return int(value)
            elif param_type == "number":
                return float(value)
            elif param_type == "boolean":
                if isinstance(value, str):
                    return value.lower() == "true"
                return bool(value)
            elif param_type == "array" or param_type == "object":
                if isinstance(value, str):
                    return json.loads(value)
                return value
            return value
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Error converting parameter value {value} to type {param_type}: {e}")
            raise ValueError(f"Invalid parameter value for type {param_type}: {value}") from e

    def _clean_uri_for_func_name(self, uri: str) -> str:
        """Clean a URI to be used as a function name.

        Args:
            uri: The URI to clean

        Returns:
            A string suitable for use as a function name
        """
        # Replace protocol:// with _
        name = uri.replace("://", "_")
        # Replace / with _
        name = name.replace("/", "_")
        # Replace {param} with _param
        name = name.replace("{", "_").replace("}", "")
        # Replace any remaining non-alphanumeric chars with _
        name = "".join(c if c.isalnum() else "_" for c in name)
        # Remove consecutive underscores
        name = "_".join(filter(None, name.split("_")))
        return name

    def _sanitize_func_name(self, name: str) -> str:
        """Sanitize a name to be used as a Python function name.

        Args:
            name: The name to sanitize

        Returns:
            A string suitable for use as a Python function name
        """
        # Replace any non-alphanumeric chars with _
        name = "".join(c if c.isalnum() else "_" for c in name)
        # Remove consecutive underscores
        name = "_".join(filter(None, name.split("_")))
        # Ensure it starts with a letter or underscore
        if not name[0].isalpha() and name[0] != "_":
            name = "_" + name
        return name

    def mcp_name_to_py(self, name: str) -> str:
        """Convert MCP endpoint name to a valid Python function name.

        Example: 'get-user' → 'mcp_get_user__abc123'

        Args:
            name: The original MCP endpoint name

        Returns:
            A valid Python function name with hash suffix
        """
        base = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        suffix = hashlib.sha1(name.encode()).hexdigest()[:6]
        return f"mcp_{base}__{suffix}"

    # ---------------------------------------------------------------------------
    # helper that every register_* method will call
    # ---------------------------------------------------------------------------
    def _build_and_register(
        self,
        endpoint_type: EndpointType,
        endpoint_key: str,  # "tool" | "resource" | "prompt"
        endpoint_def: ToolDefinition | ResourceDefinition | PromptDefinition,
        decorator: Any,  # self.mcp.tool() | self.mcp.resource(uri) | self.mcp.prompt()
        log_name: str,  # for nice logging
    ) -> None:
        # Get parameter definitions
        parameters = endpoint_def.get("parameters") or []

        # Create function signature with proper Pydantic type annotations
        # Include Context as the first parameter for accessing session_id
        param_annotations = {"ctx": Context}
        param_signatures = ["ctx"]

        # Sort parameters so required (no default) come before optional (with default)
        # This is necessary for valid Python function signatures
        required_params = [p for p in parameters if "default" not in p]
        optional_params = [p for p in parameters if "default" in p]
        sorted_parameters = required_params + optional_params

        for param in sorted_parameters:
            param_name = param["name"]
            param_type = self._json_schema_to_python_type(param, endpoint_type)
            param_annotations[param_name] = param_type

            # Create string representation for makefun with default values
            if "default" in param:
                # Parameter has a default value, make it optional in signature
                default_value = repr(param["default"])
                param_signatures.append(f"{param_name}={default_value}")
            else:
                # Required parameter
                param_signatures.append(f"{param_name}")

        signature = f"({', '.join(param_signatures)})"

        # -------------------------------------------------------------------
        # Body of the handler: receives **kwargs with those exact names
        # -------------------------------------------------------------------
        async def _body(**kwargs: Any) -> Any:
            start_time = time.time()
            status = "success"
            error_msg = None
            result = None  # Initialize result to avoid undefined variable in finally block
            policy_info: dict[str, Any] = {
                "policies_evaluated": [],
                "policy_decision": None,
                "policy_reason": None,
            }

            # Extract the FastMCP Context (first parameter)
            ctx = kwargs.pop("ctx", None)
            mcp_session_id = None
            request_headers = None
            if ctx:
                # session_id might be None in stateless mode
                with contextlib.suppress(Exception):
                    mcp_session_id = getattr(ctx, "session_id", None)
                if hasattr(ctx, "request_context"):
                    request_context = ctx.request_context
                    if (
                        request_context
                        and hasattr(request_context, "request")
                        and request_context.request
                    ):
                        with contextlib.suppress(Exception):
                            request_headers = dict(request_context.request.headers)

            try:
                # Get the user context from the context variable (set by auth middleware)
                user_context = get_user_context()

                logger.info(
                    f"Calling {log_name} {endpoint_def.get('name', endpoint_def.get('uri'))} with: {kwargs}"
                )
                if user_context:
                    logger.info(
                        f"Authenticated user: {user_context.username} (provider: {user_context.provider})"
                    )

                # run through new SDK executor (handles type conversion automatically)
                if self.runtime_environment is None:
                    raise RuntimeError("Execution engine not initialized")
                name: str
                if endpoint_key == "resource":
                    name = cast(str, endpoint_def.get("uri", "unknown"))
                else:
                    name = cast(str, endpoint_def.get("name", "unnamed"))

                # Increment concurrent executions gauge
                increment_gauge(
                    "mxcp.endpoint.concurrent_executions",
                    attributes={"endpoint": name, "type": endpoint_key},
                    description="Currently running endpoint executions",
                )

                # Add session ID to current span if telemetry is enabled
                trace_id = get_current_trace_id()
                if trace_id:
                    # Add both MCP session ID and trace ID to span
                    if mcp_session_id:
                        set_span_attribute("mxcp.session.id", mcp_session_id)
                    set_span_attribute("mxcp.trace.id", trace_id)
                # Use the common execution wrapper with policy info
                result, policy_info = await self._execute(
                    endpoint_type=endpoint_type.value,
                    name=name,
                    params=kwargs,  # No manual conversion needed - SDK handles it
                    user_context=user_context,
                    with_policy_info=True,
                    request_headers=request_headers,  # Pass the FastMCP request headers
                )
                logger.debug(f"Result: {json.dumps(result, indent=2, default=str)}")
                return result

            except Exception as e:
                status = "error"
                error_msg = str(e)
                logger.error(
                    f"Error executing {log_name} {endpoint_def.get('name', endpoint_def.get('uri'))}:\n{traceback.format_exc()}"
                )
                raise
            finally:
                # Calculate duration
                duration_ms = int((time.time() - start_time) * 1000)

                # Determine caller type based on transport
                if self.transport_mode:
                    if self.transport_mode == "stdio":
                        caller = "stdio"
                    else:
                        caller = "http"  # streamable-http or other HTTP transports
                else:
                    # Fallback to http if transport mode not set
                    caller = "http"

                # Record metrics
                # Decrement concurrent executions
                decrement_gauge(
                    "mxcp.endpoint.concurrent_executions",
                    attributes={"endpoint": name, "type": endpoint_key},
                    description="Currently running endpoint executions",
                )

                # Record request counter
                record_counter(
                    "mxcp.endpoint.requests_total",
                    attributes={
                        "endpoint": name,
                        "type": endpoint_key,
                        "status": status,
                        "caller": caller,
                        "policy_decision": policy_info.get("policy_decision", "none"),
                    },
                    description="Total endpoint requests",
                )

                # Record error counter if error occurred
                if status == "error":
                    record_counter(
                        "mxcp.endpoint.errors_total",
                        attributes={
                            "endpoint": name,
                            "type": endpoint_key,
                            "caller": caller,
                            "error_type": type(error_msg).__name__ if error_msg else "unknown",
                        },
                        description="Total endpoint errors",
                    )

                # Log the audit event
                if self.audit_logger:
                    await self.audit_logger.log_event(
                        caller_type=cast(
                            Literal["cli", "http", "stdio", "api", "system", "unknown"], caller
                        ),
                        event_type=cast(
                            Literal["tool", "resource", "prompt"], endpoint_key
                        ),  # "tool", "resource", or "prompt"
                        name=name,
                        input_params=kwargs,
                        duration_ms=duration_ms,
                        schema_name=ENDPOINT_EXECUTION_SCHEMA.schema_name,
                        policy_decision=policy_info["policy_decision"],
                        reason=policy_info["policy_reason"],
                        status=cast(Literal["success", "error"], status),
                        error=error_msg,
                        output_data=result,  # Return the result as output_data
                        policies_evaluated=policy_info["policies_evaluated"],
                        # Add user context if available
                        user_id=user_context.user_id if user_context else None,
                        session_id=mcp_session_id,  # MCP session ID
                        # Add trace ID for correlation with telemetry
                        trace_id=get_current_trace_id(),
                    )

        # -------------------------------------------------------------------
        # Wrap with authentication middleware
        # -------------------------------------------------------------------
        authenticated_body = self.auth_middleware.require_auth(_body)

        # -------------------------------------------------------------------
        # Create function with proper signature and annotations using makefun
        # -------------------------------------------------------------------
        if endpoint_key == "resource":
            original_name = cast(str, endpoint_def.get("uri", "unknown"))
        else:
            original_name = cast(str, endpoint_def.get("name", "unnamed"))
        func_name = self.mcp_name_to_py(original_name)

        # Create the function with proper signature
        handler = create_function(signature, authenticated_body, func_name=func_name)

        # Set the annotations for Pydantic introspection
        handler.__annotations__ = param_annotations

        # Add return type annotation if return schema is defined
        return_schema = endpoint_def.get("return")
        if return_schema:
            return_type = self._create_pydantic_model_from_schema(
                cast(dict[str, Any], return_schema), f"{original_name}Return", endpoint_type
            )
            handler.__annotations__["return"] = return_type

        # Finally register the function with FastMCP -------------------------
        # Use original name for FastMCP registration
        decorator(handler)
        logger.info(f"Registered {log_name}: {original_name} (function: {func_name})")

    def _register_tool(self, tool_def: ToolDefinition) -> None:
        """Register a tool endpoint with MCP.

        Args:
            tool_def: The tool definition from YAML
        """
        # Create tool annotations from the definition
        annotations = self._create_tool_annotations(tool_def)

        self._build_and_register(
            EndpointType.TOOL,
            "tool",
            tool_def,
            decorator=self.mcp.tool(
                name=tool_def.get("name"),
                description=tool_def.get("description"),
                annotations=annotations,
            ),
            log_name="tool",
        )

    def _register_resource(self, resource_def: ResourceDefinition) -> None:
        """Register a resource endpoint with MCP.

        Args:
            resource_def: The resource definition from YAML
        """
        self._build_and_register(
            EndpointType.RESOURCE,
            "resource",
            resource_def,
            decorator=self.mcp.resource(
                resource_def["uri"],
                name=cast(str | None, resource_def.get("name")),
                description=resource_def.get("description"),
                mime_type=resource_def.get("mime_type"),
            ),
            log_name="resource",
        )

    def _register_prompt(self, prompt_def: PromptDefinition) -> None:
        """Register a prompt endpoint with MCP.

        Args:
            prompt_def: The prompt definition from YAML
        """
        self._build_and_register(
            EndpointType.PROMPT,
            "prompt",
            prompt_def,
            decorator=self.mcp.prompt(
                name=prompt_def.get("name"), description=prompt_def.get("description")
            ),
            log_name="prompt",
        )

    def _register_duckdb_features(self) -> None:
        """Register built-in SQL querying and schema exploration tools if enabled."""
        if not self.enable_sql_tools:
            return

        # Register SQL query tool with proper metadata
        @self.mcp.tool(
            name="execute_sql_query",
            description="Execute a SQL query against the DuckDB database and return the results as a list of records",
            annotations=ToolAnnotations(
                title="SQL Query Executor",
                readOnlyHint=False,  # SQL can modify data
                destructiveHint=True,  # SQL can delete/update data
                idempotentHint=False,  # SQL queries may not be idempotent
                openWorldHint=False,  # Operates on closed database
            ),
        )
        @self.auth_middleware.require_auth
        async def execute_sql_query(sql: str) -> list[dict[str, Any]]:
            """Execute a SQL query against the DuckDB database.

            Args:
                sql: The SQL query to execute

            Returns:
                List of records as dictionaries
            """
            start_time = time.time()
            status = "success"
            error_msg = None

            try:
                user_context = get_user_context()
                if user_context:
                    logger.info("Authenticated user executing SQL query")

                result = await self._execute_sql(
                    source_code=sql,
                    params={},
                    user_context=user_context,
                )
                return cast(list[dict[str, Any]], result)
            except Exception as e:
                status = "error"
                error_msg = str(e)
                logger.error(f"Error executing SQL query: {e}")
                raise
            finally:
                # Log audit event
                duration_ms = int((time.time() - start_time) * 1000)
                if self.audit_logger:
                    # Determine caller type
                    caller = "stdio" if getattr(self, "transport_mode", None) == "stdio" else "http"

                    await self.audit_logger.log_event(
                        caller_type=cast(
                            Literal["cli", "http", "stdio", "api", "system", "unknown"], caller
                        ),
                        event_type="tool",
                        name="execute_sql_query",
                        input_params={"sql": sql},
                        duration_ms=duration_ms,
                        schema_name=ENDPOINT_EXECUTION_SCHEMA.schema_name,
                        policy_decision=None,
                        reason=None,
                        status=cast(Literal["success", "error"], status),
                        error=error_msg,
                        trace_id=get_current_trace_id(),
                    )

        # Register table list tool with proper metadata
        @self.mcp.tool(
            name="list_tables",
            description="List all tables in the DuckDB database",
            annotations=ToolAnnotations(
                title="Database Table Lister",
                readOnlyHint=True,  # Only reads metadata
                destructiveHint=False,  # Cannot modify data
                idempotentHint=True,  # Always returns same result
                openWorldHint=False,  # Operates on closed database
            ),
        )
        @self.auth_middleware.require_auth
        async def list_tables() -> list[dict[str, str]]:
            """List all tables in the DuckDB database.

            Returns:
                List of tables with their names and types
            """
            start_time = time.time()
            status = "success"
            error_msg = None

            try:
                user_context = get_user_context()
                if user_context:
                    logger.info(f"User {user_context.username} listing tables")

                result = await self._execute_sql(
                    source_code="""
                        SELECT
                            table_name as name, table_type as type
                        FROM information_schema.tables
                        WHERE table_schema = 'main'
                        ORDER BY table_name""",
                    params={},
                    user_context=user_context,
                )
                return cast(list[dict[str, str]], result)
            except Exception as e:
                status = "error"
                error_msg = str(e)
                logger.error(f"Error listing tables: {e}")
                raise
            finally:
                # Log audit event
                duration_ms = int((time.time() - start_time) * 1000)
                if self.audit_logger:
                    # Determine caller type
                    caller = "stdio" if getattr(self, "transport_mode", None) == "stdio" else "http"

                    await self.audit_logger.log_event(
                        caller_type=cast(
                            Literal["cli", "http", "stdio", "api", "system", "unknown"], caller
                        ),
                        event_type="tool",
                        name="list_tables",
                        input_params={},
                        duration_ms=duration_ms,
                        schema_name=ENDPOINT_EXECUTION_SCHEMA.schema_name,
                        policy_decision=None,
                        reason=None,
                        status=cast(Literal["success", "error"], status),
                        error=error_msg,
                        trace_id=get_current_trace_id(),
                    )

        # Register schema tool with proper metadata
        @self.mcp.tool(
            name="get_table_schema",
            description="Get the schema for a specific table in the DuckDB database",
            annotations=ToolAnnotations(
                title="Table Schema Inspector",
                readOnlyHint=True,  # Only reads metadata
                destructiveHint=False,  # Cannot modify data
                idempotentHint=True,  # Always returns same result for same table
                openWorldHint=False,  # Operates on closed database
            ),
        )
        @self.auth_middleware.require_auth
        async def get_table_schema(table_name: str) -> list[dict[str, Any]]:
            """Get the schema for a specific table.

            Args:
                table_name: Name of the table to get schema for

            Returns:
                List of columns with their names and types
            """
            start_time = time.time()
            status = "success"
            error_msg = None

            try:
                user_context = get_user_context()
                if user_context:
                    logger.info(
                        f"User {user_context.username} getting schema for table {table_name}"
                    )

                result = await self._execute_sql(
                    source_code="""
                        SELECT
                            column_name as name,
                            data_type as type,
                            is_nullable as nullable
                        FROM information_schema.columns
                        WHERE table_name = $table_name
                        ORDER BY ordinal_position
                    """,
                    params={"table_name": table_name},
                    user_context=user_context,
                )
                return cast(list[dict[str, Any]], result)
            except Exception as e:
                status = "error"
                error_msg = str(e)
                logger.error(f"Error getting table schema: {e}")
                raise
            finally:
                # Log audit event
                duration_ms = int((time.time() - start_time) * 1000)
                if self.audit_logger:
                    # Determine caller type
                    caller = "stdio" if getattr(self, "transport_mode", None) == "stdio" else "http"

                    await self.audit_logger.log_event(
                        caller_type=cast(
                            Literal["cli", "http", "stdio", "api", "system", "unknown"], caller
                        ),
                        event_type="tool",
                        name="get_table_schema",
                        input_params={"table_name": table_name},
                        duration_ms=duration_ms,
                        schema_name=ENDPOINT_EXECUTION_SCHEMA.schema_name,
                        policy_decision=None,
                        reason=None,
                        status=cast(Literal["success", "error"], status),
                        error=error_msg,
                        trace_id=get_current_trace_id(),
                    )

        logger.info("Registered built-in DuckDB features")

    @with_draining_and_request_tracking
    async def _execute(
        self,
        endpoint_type: str,
        name: str,
        params: dict[str, Any],
        user_context: Any = None,
        with_policy_info: bool = False,
        request_headers: dict[str, str] | None = None,
    ) -> Any:
        """Execute endpoint with execution lock.

        This method handles the actual endpoint execution with the execution lock.
        The draining wait and request tracking is handled by the decorator.

        Args:
            endpoint_type: Type of endpoint to execute
            name: Name of endpoint
            params: Parameters to pass
            user_context: User context
            with_policy_info: If True, returns (result, policy_info) tuple
            request_headers: Request headers from FastMCP

        Returns:
            Result of execution, or (result, policy_info) if with_policy_info=True
        """
        if self.runtime_environment is None:
            raise RuntimeError("Execution engine not initialized")

        if with_policy_info:
            return await execute_endpoint_with_engine_and_policy(
                endpoint_type=endpoint_type,
                name=name,
                params=params,
                user_config=self.user_config,
                site_config=self.site_config,
                execution_engine=self.runtime_environment.execution_engine,
                user_context=user_context,
                request_headers=request_headers,
                server_ref=self,
            )
        else:
            return await execute_endpoint_with_engine(
                endpoint_type=endpoint_type,
                name=name,
                params=params,
                user_config=self.user_config,
                site_config=self.site_config,
                execution_engine=self.runtime_environment.execution_engine,
                user_context=user_context,
                request_headers=request_headers,
                server_ref=self,
            )

    @with_draining_and_request_tracking
    async def _execute_sql(
        self,
        source_code: str,
        params: dict[str, Any] | None = None,
        user_context: Any = None,
    ) -> Any:
        """Execute SQL query with execution lock.

        This method handles SQL execution through the execution engine with the execution lock.
        The draining wait and request tracking is handled by the decorator.

        Args:
            source_code: SQL source code to execute
            params: Parameters to pass to the SQL query
            user_context: Optional user context for authentication/authorization

        Returns:
            Result of SQL execution
        """
        if self.runtime_environment is None:
            raise RuntimeError("Execution engine not initialized")

        execution_context = ExecutionContext(user_context=user_context)
        execution_context.set("user_config", self.user_config)
        execution_context.set("site_config", self.site_config)

        return await self.runtime_environment.execution_engine.execute(
            language="sql",
            source_code=source_code,
            params=params or {},
            context=execution_context,
        )

    def register_endpoints(self) -> None:
        """Register all discovered endpoints with MCP."""
        for path, endpoint_def in self.endpoints:
            try:
                # Validate endpoint before registration using shared session
                if self.runtime_environment is None:
                    raise RuntimeError("Execution engine not initialized")
                validation_result = validate_endpoint(
                    str(path), self.site_config, self.runtime_environment.execution_engine
                )

                if validation_result["status"] != "ok":
                    logger.warning(
                        f"Skipping invalid endpoint {path}: {validation_result.get('message', 'Unknown error')}"
                    )
                    self.skipped_endpoints.append(
                        {
                            "path": str(path),
                            "error": validation_result.get("message", "Unknown error"),
                        }
                    )
                    continue

                if endpoint_def is None:
                    logger.warning(f"Endpoint definition is None for {path}")
                    continue

                if "tool" in endpoint_def:
                    tool_def = endpoint_def.get("tool")
                    if tool_def:
                        self._register_tool(tool_def)
                        logger.info(
                            f"Registered tool endpoint from {path}: {tool_def.get('name', 'unnamed')}"
                        )
                elif "resource" in endpoint_def:
                    resource_def = endpoint_def.get("resource")
                    if resource_def:
                        self._register_resource(resource_def)
                        logger.info(
                            f"Registered resource endpoint from {path}: {resource_def.get('uri', 'unknown')}"
                        )
                elif "prompt" in endpoint_def:
                    prompt_def = endpoint_def.get("prompt")
                    if prompt_def:
                        self._register_prompt(prompt_def)
                        logger.info(
                            f"Registered prompt endpoint from {path}: {prompt_def.get('name', 'unnamed')}"
                        )
                else:
                    logger.warning(f"Unknown endpoint type in {path}: {endpoint_def}")
            except Exception as e:
                logger.error(f"Error registering endpoint {path}: {e}")
                self.skipped_endpoints.append({"path": str(path), "error": str(e)})
                continue

        # Register DuckDB features if enabled
        if self.enable_sql_tools:
            self._register_duckdb_features()

        # Report skipped endpoints
        if self.skipped_endpoints:
            logger.warning(f"Skipped {len(self.skipped_endpoints)} invalid endpoints:")
            for skipped in self.skipped_endpoints:
                logger.warning(f"  - {skipped['path']}: {skipped['error']}")

    async def _initialize_oauth_server(self) -> None:
        """Initialize OAuth server persistence if enabled."""
        if self.oauth_server:
            try:
                await self.oauth_server.initialize()
                logger.info("OAuth server initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OAuth server: {e}")
                raise

    def run(self, transport: str = "streamable-http") -> None:
        """Run the MCP server.

        Args:
            transport: The transport to use ("streamable-http" or "stdio")
        """
        try:
            logger.info("Starting MCP server...")
            # Store transport mode for use in handlers
            self.transport_mode = transport

            # Start the reload manager
            self.reload_manager.start()

            # Start admin API (async operation from sync context)
            self._ensure_async_completes(
                self.admin_api.start(),
                timeout=10.0,
                operation_name="Admin API startup",
            )

            # Register all endpoints
            self.register_endpoints()
            logger.info("Endpoints registered successfully.")

            # Add debug logging for uvicorn config if using streamable-http
            if transport == "streamable-http":
                logger.info(
                    f"About to start uvicorn with host={self.mcp.settings.host}, port={self.mcp.settings.port}"
                )

            # Initialize OAuth server before starting FastMCP - ensure it completes
            if self.oauth_server:
                try:
                    self._ensure_async_completes(
                        self._initialize_oauth_server(),
                        timeout=10.0,
                        operation_name="OAuth server initialization",
                    )
                except TimeoutError:
                    raise RuntimeError("OAuth server initialization timed out") from None
                except Exception as e:
                    # Don't continue if OAuth is enabled but initialization failed
                    raise RuntimeError(f"OAuth server initialization failed: {e}") from e

            # Start server using MCP's built-in run method
            self.mcp.run(transport=cast(Literal["stdio", "sse", "streamable-http"], transport))
            logger.info("MCP server started successfully.")
        except Exception as e:
            logger.error(f"Error running MCP server: {e}")
            raise

    def _register_oauth_routes(self) -> None:
        """Register OAuth callback routes."""
        if self.oauth_handler is None:
            logger.warning("OAuth handler not configured, skipping OAuth routes")
            return

        callback_path = self.oauth_handler.callback_path
        logger.info(f"Registering OAuth callback route: {callback_path}")

        # Use custom_route to register the callback
        @self.mcp.custom_route(callback_path, methods=["GET"])  # type: ignore[misc]
        async def oauth_callback(request: Any) -> Any:
            if self.oauth_handler is None or self.oauth_server is None:
                raise RuntimeError("OAuth not configured")
            return await self.oauth_handler.on_callback(request, self.oauth_server)

        # Register OAuth Protected Resource metadata endpoint
        @self.mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])  # type: ignore[misc]
        async def oauth_protected_resource_metadata(request: Any) -> Any:
            """Handle OAuth Protected Resource metadata requests (RFC 8693)"""

            # Use URL builder with request context for proper scheme detection
            url_builder = create_url_builder(self.user_config)
            base_url = url_builder.get_base_url(request)

            # Get supported scopes from configuration
            auth_config = self.active_profile.get("auth", {})
            auth_authorization = auth_config.get("authorization", {})
            supported_scopes = auth_authorization.get("required_scopes", [])

            metadata = {
                "resource": base_url,
                "authorization_servers": [base_url],
                "scopes_supported": supported_scopes,
                "bearer_methods_supported": ["header"],
                "resource_documentation": f"{base_url}/docs",
            }

            return JSONResponse(content=metadata, headers={"Content-Type": "application/json"})
