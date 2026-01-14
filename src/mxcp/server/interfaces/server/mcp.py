import asyncio
import contextlib
import functools
import hashlib
import json
import logging
import os
import re
import signal
import time
import traceback
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, TypeVar, cast

import uvicorn
from makefun import create_function
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import Context as FastMCPContextRuntime
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl, ConfigDict, Field, create_model
from starlette.responses import JSONResponse

from mxcp.sdk.audit import AuditLogger
from mxcp.sdk.auth import GeneralOAuthAuthorizationServer
from mxcp.sdk.auth.context import get_user_context
from mxcp.sdk.auth.middleware import AuthenticationMiddleware
from mxcp.sdk.core import PACKAGE_VERSION
from mxcp.sdk.core.analytics import track_endpoint_execution
from mxcp.sdk.mcp import FastMCPLogProxy
from mxcp.sdk.telemetry import (
    decrement_gauge,
    get_current_trace_id,
    increment_gauge,
    record_counter,
    traced_operation,
)
from mxcp.server.admin import AdminAPIRunner
from mxcp.server.core.auth.helpers import (
    create_oauth_handler,
    create_url_builder,
    translate_auth_config,
)
from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel
from mxcp.server.core.config.site_config import get_active_profile, load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.core.refs.external import ExternalRefTracker
from mxcp.server.core.reload import AsyncServerLock, ReloadManager, ReloadRequest
from mxcp.server.core.telemetry import configure_telemetry_from_config, shutdown_telemetry
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.definitions.endpoints.models import (
    ParamDefinitionModel,
    PromptDefinitionModel,
    ResourceDefinitionModel,
    ToolDefinitionModel,
    TypeDefinitionModel,
)
from mxcp.server.definitions.endpoints.utils import EndpointType
from mxcp.server.executor.context_utils import build_execution_context
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
from mxcp.server.services.endpoints.models import EndpointErrorModel
from mxcp.server.services.endpoints.validator import validate_endpoint

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context as FastMCPContextGeneric

    FastMCPContext = FastMCPContextGeneric[Any, Any, Any]
else:  # pragma: no cover
    FastMCPContext = FastMCPContextRuntime


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
            # Check if draining is in progress and if not, increment the active requests counter.
            async with self.requests_lock:
                if not self.draining:
                    self.active_requests += 1
                    break

            # Draining is in progress, wait and retry.
            if time.time() - wait_start > wait_timeout:
                raise RuntimeError(
                    "Service is reloading and taking longer than expected. Please retry in a few seconds."
                )
            await asyncio.sleep(0.1)

        try:
            return await func(self, *args, **kwargs)
        finally:
            async with self.requests_lock:
                self.active_requests -= 1

    return cast(T, wrapper)


class RAWMCP:
    """MXCP MCP Server implementation that bridges MXCP endpoints with MCP protocol."""

    # Type annotations for instance attributes
    site_config: SiteConfigModel
    user_config: UserConfigModel
    _site_config_template: SiteConfigModel
    _user_config_template: UserConfigModel
    host: str
    port: int
    profile_name: str
    transport: str
    readonly: bool
    _model_cache: dict[str, Any]
    transport_mode: str | None

    _signal_loop: asyncio.AbstractEventLoop | None = None

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

        # Track transport mode and other state
        self.transport_mode = None
        self._shutdown_called = False

        # Request tracking for safe reloading
        self.active_requests = 0
        self.requests_lock = AsyncServerLock()
        self.draining = False

        # Event loop used for signal callbacks (set when main loop starts)
        self._signal_loop: asyncio.AbstractEventLoop | None = None

        # Initialize admin API (but don't start yet - will be started in run())
        self.admin_api = AdminAPIRunner(
            server=self,
            socket_path=get_env_admin_socket_path(),
            enabled=get_env_admin_socket_enabled(),
        )

        # Note: Signal handlers are registered in run() when the system is ready
        # to handle them, not here in __init__.

        self._initialize_audit_config()

    def _initialize_audit_config(self) -> None:
        """Resolve static audit logging settings from configuration."""
        profile_config = self.site_config.profiles.get(self.profile_name)
        audit_config = profile_config.audit if profile_config else None
        self._audit_logging_enabled = bool(audit_config and audit_config.enabled)
        audit_path_str = audit_config.path if audit_config and audit_config.path else ""
        self._audit_log_path = Path(audit_path_str) if audit_path_str else Path("audit.log")

    def _resolve_and_apply_configs(self) -> None:
        """Resolve external references with selective interpolation and apply CLI overrides.

        External references (${ENV_VAR}, vault://, file://) are resolved using selective
        interpolation, which only resolves references for the active profile and top-level
        config. This prevents errors from undefined environment variables in inactive profiles.
        """
        site_template_dict = self._site_config_template.model_dump(mode="python")
        user_template_dict = self._user_config_template.model_dump(mode="python")

        # Check if configs contain unresolved references
        config_str = json.dumps(site_template_dict) + json.dumps(user_template_dict)
        needs_resolution = any(pattern in config_str for pattern in ["${", "vault://", "file://"])

        # Determine active profile (CLI override > site config)
        active_profile = str(self._cli_overrides["profile"] or self._site_config_template.profile)
        project_name = self._site_config_template.project

        if needs_resolution:
            # Set templates and resolve with selective interpolation
            logger.info(
                f"Resolving external configuration references for project={project_name}, profile={active_profile}..."
            )
            self.ref_tracker.set_template(
                site_template_dict,
                user_template_dict,
            )
            self._config_templates_loaded = True

            # Use selective interpolation - only resolve active profile + top-level config
            resolved_site, resolved_user = self.ref_tracker.resolve_all(
                project_name=project_name,
                profile_name=active_profile,
            )
            self.site_config = SiteConfigModel.model_validate(
                resolved_site, context={"repo_root": self.site_config_path}
            )
            self.user_config = UserConfigModel.model_validate(resolved_user)
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
        transport_model = self.user_config.transport
        http_config = transport_model.http

        self.transport = str(
            self._cli_overrides["transport"] or transport_model.provider or "streamable-http"
        )

        self.host = str(self._cli_overrides["host"] or http_config.host or "localhost")
        port_value = self._cli_overrides["port"] or http_config.port or 8000
        self.port = int(port_value)

        config_stateless = http_config.stateless or False
        self.stateless_http = (
            self._cli_overrides["stateless_http"]
            if self._cli_overrides["stateless_http"] is not None
            else config_stateless
        )

        self.json_response = self._cli_overrides["json_response"]
        self.readonly = bool(self._cli_overrides["readonly"])

        # SQL tools setting
        sql_tools_config = self.site_config.sql_tools
        site_sql_tools = bool(sql_tools_config.enabled)
        self.enable_sql_tools = (
            self._cli_overrides["enable_sql_tools"]
            if self._cli_overrides["enable_sql_tools"] is not None
            else site_sql_tools
        )

    def get_endpoint_counts(self) -> dict[str, int]:
        """Get counts of valid endpoints by type.

        Uses self.endpoints which may be filtered to exclude endpoints with
        validation errors.
        """
        tool_count = sum(
            1
            for _, endpoint in self.endpoints
            if endpoint is not None and endpoint.tool is not None
        )
        resource_count = sum(
            1
            for _, endpoint in self.endpoints
            if endpoint is not None and endpoint.resource is not None
        )
        prompt_count = sum(
            1
            for _, endpoint in self.endpoints
            if endpoint is not None and endpoint.prompt is not None
        )

        return {
            "tools": tool_count,
            "resources": resource_count,
            "prompts": prompt_count,
            "total": tool_count + resource_count + prompt_count,
        }

    def validate_all_endpoints(self) -> list[EndpointErrorModel]:
        """Validate all endpoints and return any validation errors.

        This method validates endpoints using the execution engine to check SQL syntax,
        etc. Call this before run() to check for validation errors.

        Returns:
            List of EndpointErrorModel instances for endpoints with validation errors.
            Empty list if all endpoints are valid.
        """
        validation_errors: list[EndpointErrorModel] = []

        if self.runtime_environment is None:
            raise RuntimeError("Execution engine not initialized")

        for path, _endpoint_def in self.endpoints:
            try:
                validation_result = validate_endpoint(
                    str(path), self.site_config, self.runtime_environment.execution_engine
                )

                if validation_result.status != "ok":
                    validation_errors.append(
                        EndpointErrorModel(
                            path=str(path),
                            error=validation_result.message or "Unknown validation error",
                        )
                    )
            except Exception as e:
                validation_errors.append(EndpointErrorModel(path=str(path), error=str(e)))

        return validation_errors

    def _load_endpoints(self) -> None:
        """Load and categorize endpoints."""

        self.loader = EndpointLoader(self.site_config)

        # Store all endpoints for reference
        self._all_endpoints = self.loader.discover_endpoints()

        # Split into valid and failed
        self.endpoints = [
            (path, endpoint) for path, endpoint, error in self._all_endpoints if error is None
        ]
        self.skipped_endpoints: list[EndpointErrorModel] = [
            EndpointErrorModel(path=str(path), error=error)
            for path, _, error in self._all_endpoints
            if error is not None
        ]

        # Log results
        logger.info(
            f"Discovered {len(self.endpoints)} valid endpoints, {len(self.skipped_endpoints)} failed endpoints"
        )
        if self.skipped_endpoints:
            for skipped in self.skipped_endpoints:
                logger.warning(f"Failed to load endpoint {skipped.path}: {skipped.error}")

    def _initialize_oauth(self) -> None:
        """Initialize OAuth authentication using profile-specific auth config."""
        auth_config = self.active_profile.auth
        self.oauth_handler = create_oauth_handler(
            auth_config,
            host=self.host,
            port=self.port,
            user_config=self.user_config,
        )
        self.oauth_server = None
        self.auth_settings = None

        if self.oauth_handler:
            auth_config_dict = translate_auth_config(auth_config)
            user_config_dict = self.user_config.model_dump(mode="python")
            self.oauth_server = GeneralOAuthAuthorizationServer(
                self.oauth_handler, auth_config_dict, user_config_dict
            )

            # Use URL builder for OAuth endpoints
            url_builder = create_url_builder(self.user_config)
            base_url = url_builder.get_base_url(host=self.host, port=self.port)

            # Get authorization configuration
            auth_authorization = auth_config.authorization
            required_scopes = auth_authorization.required_scopes if auth_authorization else []

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
            logger.info(f"OAuth authentication enabled with provider: {auth_config.provider}")
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

    async def _run_admin_api_and_transport(self, transport: str) -> None:
        """Start the admin API (if enabled) and run the main MCP server."""
        # Start admin API in this event loop (if enabled)
        await self.admin_api.start()

        try:
            # Now start the main MCP server based on transport
            if transport == "stdio":
                await self.mcp.run_stdio_async()
            elif transport == "sse":
                await self.mcp.run_sse_async(None)
            elif transport == "streamable-http":
                # Get the Starlette app and run with uvicorn
                starlette_app = self.mcp.streamable_http_app()
                config = uvicorn.Config(
                    starlette_app,
                    host=self.mcp.settings.host,
                    port=self.mcp.settings.port,
                    log_level=self.mcp.settings.log_level.lower(),
                )
                server = uvicorn.Server(config)
                await server.serve()
        finally:
            # Cleanup: stop admin API
            logger.info("Stopping admin API")
            await self.admin_api.stop()
            logger.info("Admin API stopped")

    async def _initialize_audit_logger(self) -> None:
        """Initialize audit logger once the event loop is running."""
        if self.audit_logger is not None:
            return

        if not self._audit_logging_enabled:
            self.audit_logger = await AuditLogger.disabled()
            return

        log_path = self._audit_log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_logger = await AuditLogger.jsonl(log_path=log_path)
        await self._register_audit_schema()

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
        """Register signal handlers for reload only.

        SIGTERM/SIGINT handling is delegated to uvicorn for graceful HTTP server shutdown.
        RAWMCP cleanup (shutdown()) is called via serve.py's KeyboardInterrupt handler.

        Signal flow:
        - SIGTERM/SIGINT: Handled by uvicorn → raises KeyboardInterrupt → serve.py cleanup
        - SIGHUP: Custom reload logic
        """
        if hasattr(signal, "SIGHUP"):
            # SIGHUP triggers a full system reload
            signal.signal(signal.SIGHUP, self._handle_reload_signal)
            logger.info("Registered SIGHUP handler for system reload.")

    def _handle_reload_signal(self, signum: int, frame: Any) -> None:
        """Handle SIGHUP signal to reload the configuration.

        Signal handlers run in the main thread but outside the event loop context.
        We use call_soon_threadsafe to schedule the async reload task on the loop.
        """
        logger.info("Received SIGHUP signal, scheduling configuration reload...")

        loop = self._signal_loop
        if loop is None:
            logger.error("SIGHUP received but event loop not initialized - ignoring")
            return

        loop.call_soon_threadsafe(lambda: asyncio.create_task(self._handle_reload_signal_async()))

    async def _handle_reload_signal_async(self) -> None:
        """Async handler that waits for reload completion."""
        request = self.reload_configuration()

        try:
            completed = await request.wait_for_completion(timeout=60.0)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"SIGHUP reload wait failed: {exc}")
            return

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
        project_name = self.site_config.project

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
                site_template.model_dump(mode="python"),
                user_template.model_dump(mode="python"),
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
                new_site_template.model_dump(mode="python"),
                new_user_template.model_dump(mode="python"),
            )

            # Resolve and update configs
            new_site_config, new_user_config = self.ref_tracker.resolve_all()
            self.site_config = SiteConfigModel.model_validate(
                new_site_config, context={"repo_root": self.site_config_path}
            )
            self.user_config = UserConfigModel.model_validate(new_user_config)

            logger.info("Configuration files reloaded")

        # Request a reload with config reload as payload
        return self.reload_manager.request_reload(
            payload_func=reload_config_files, description="Configuration reload (SIGHUP)"
        )

    async def shutdown(self) -> None:
        """Shutdown the server gracefully."""
        # Prevent double shutdown
        if self._shutdown_called:
            return
        self._shutdown_called = True

        logger.info("Shutting down MXCP server...")

        # Clear signal loop first to prevent SIGHUP signals from triggering
        # reload requests during shutdown (they'll be safely ignored).
        self._signal_loop = None

        # Stop the reload manager while the loop is still running
        try:
            await self.reload_manager.stop()
        except Exception as exc:
            logger.error(f"Error stopping reload manager: {exc}")

        # Gracefully shut down the reloadable runtime components first
        # This handles python runtimes, plugins, and the db session.
        try:
            self.shutdown_runtime_components()
        except Exception as exc:
            logger.error(f"Error shutting down runtime components: {exc}")

        # Close OAuth server persistence
        if self.oauth_server:
            try:
                await asyncio.wait_for(self.oauth_server.close(), timeout=5.0)
                logger.info("Closed OAuth server")
            except asyncio.TimeoutError:
                logger.error("OAuth server shutdown timed out after 5 seconds")
            except Exception as exc:
                logger.error(f"Error closing OAuth server: {exc}")

        # Shutdown audit logger if initialized
        if self.audit_logger:
            try:
                await asyncio.wait_for(self.audit_logger.close(), timeout=5.0)
                logger.info("Closed audit logger")
            except asyncio.TimeoutError:
                logger.error("Audit logger shutdown timed out after 5 seconds")
            except Exception as exc:
                logger.error(f"Error closing audit logger: {exc}")

        # Shutdown telemetry (synchronous)
        try:
            shutdown_telemetry()
            logger.info("Shutdown telemetry")
        except Exception as exc:
            logger.error(f"Error shutting down telemetry: {exc}")

        # Note: We intentionally do NOT flush analytics here.
        # Analytics is non-critical, and flush() can block indefinitely on network issues.
        # PostHog's auto-flush (every 0.5s) handles the common case.

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

    def _schema_dict(self, schema: TypeDefinitionModel) -> dict[str, Any]:
        """Convert a schema model to a plain dictionary representation."""
        return schema.model_dump(mode="python", exclude_unset=True, by_alias=True)

    def _create_pydantic_model_from_schema(
        self,
        schema_def: TypeDefinitionModel,
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
        schema_dict = self._schema_dict(schema_def)

        cache_key = f"{model_name}_{hash(json.dumps(schema_dict, sort_keys=True))}_{endpoint_type}"
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        json_type = schema_def.type

        # Declare variable with explicit type annotation
        final_type: Any

        # Determine if parameters should be nullable (tools/prompts parameters can be null)
        # or not (resources templates cannot get null arguments)
        make_nullable = endpoint_type in (EndpointType.TOOL, EndpointType.PROMPT)

        # Handle primitive types
        if json_type == "string":
            if schema_def.enum and all(isinstance(v, str) for v in schema_def.enum):
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
            items_schema = schema_def.items
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
            properties = schema_def.properties or {}
            required_fields = set(schema_def.required or [])

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
                        default = field_kwargs.pop("default", None)
                        model_fields[prop_name] = (prop_type | None, Field(default, **field_kwargs))
                    else:
                        model_fields[prop_name] = (prop_type | None, None)

            # Create the model with proper configuration

            # Create model with fields and config
            # Note: In Pydantic v2, __config__ is not supported in create_model
            # Instead, we create the model and then set the config
            extra_mode: str | None = None
            if schema_def.additionalProperties is True:
                extra_mode = "allow"
            elif schema_def.additionalProperties is False:
                extra_mode = "forbid"

            if extra_mode is not None:
                final_type = create_model(  # type: ignore[call-overload]
                    self._sanitize_model_name(model_name),
                    __config__=ConfigDict(extra=extra_mode),
                    **model_fields,
                )
            else:
                final_type = create_model(  # type: ignore[call-overload]
                    self._sanitize_model_name(model_name), **model_fields
                )

            self._model_cache[cache_key] = final_type
            return final_type

        # Fallback to Any for unknown types
        final_type = Any
        self._model_cache[cache_key] = final_type
        return final_type

    def _extract_field_constraints(self, schema_def: TypeDefinitionModel) -> dict[str, Any]:
        """Extract Pydantic Field constraints from a type definition."""
        field_kwargs: dict[str, Any] = {}

        if schema_def.description:
            field_kwargs["description"] = schema_def.description

        if "default" in schema_def.model_fields_set:
            field_kwargs["default"] = schema_def.default

        if schema_def.examples:
            field_kwargs["examples"] = schema_def.examples

        if schema_def.minLength is not None:
            field_kwargs["min_length"] = schema_def.minLength
        if schema_def.maxLength is not None:
            field_kwargs["max_length"] = schema_def.maxLength
        if schema_def.pattern is not None:
            field_kwargs["pattern"] = schema_def.pattern

        if schema_def.minimum is not None:
            field_kwargs["ge"] = schema_def.minimum
        if schema_def.maximum is not None:
            field_kwargs["le"] = schema_def.maximum
        if schema_def.exclusiveMinimum is not None:
            field_kwargs["gt"] = schema_def.exclusiveMinimum
        if schema_def.exclusiveMaximum is not None:
            field_kwargs["lt"] = schema_def.exclusiveMaximum
        if schema_def.multipleOf is not None:
            field_kwargs["multiple_of"] = schema_def.multipleOf

        if schema_def.minItems is not None:
            field_kwargs["min_length"] = schema_def.minItems
        if schema_def.maxItems is not None:
            field_kwargs["max_length"] = schema_def.maxItems

        return field_kwargs

    def _create_pydantic_field_annotation(
        self, param_def: TypeDefinitionModel, endpoint_type: EndpointType | None = None
    ) -> Any:
        """Create a Pydantic type annotation from parameter definition.

        Args:
            param_def: Parameter definition from endpoint YAML
            endpoint_type: Type of endpoint (affects whether parameters are Optional)

        Returns:
            Pydantic type annotation (class or Annotated type)
        """
        param_name = getattr(param_def, "name", None) or "param"
        return self._create_pydantic_model_from_schema(param_def, param_name, endpoint_type)

    def _json_schema_to_python_type(
        self, param_def: TypeDefinitionModel, endpoint_type: EndpointType | None = None
    ) -> Any:
        """Convert JSON Schema type to Python type annotation.

        Args:
            param_def: Parameter definition from endpoint YAML
            endpoint_type: Type of endpoint (affects whether parameters are Optional)

        Returns:
            Python type annotation
        """
        return self._create_pydantic_field_annotation(param_def, endpoint_type)

    def _create_tool_annotations(self, tool_def: ToolDefinitionModel) -> ToolAnnotations | None:
        """Create ToolAnnotations from tool definition.

        Args:
            tool_def: Tool definition from endpoint YAML

        Returns:
            ToolAnnotations object if annotations are present, None otherwise
        """
        annotations_model = tool_def.annotations
        if not annotations_model:
            return None

        annotations_data = annotations_model.model_dump(mode="python", exclude_unset=True)
        return ToolAnnotations(**annotations_data)

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
        endpoint_def: ToolDefinitionModel | ResourceDefinitionModel | PromptDefinitionModel,
        decorator: Any,  # self.mcp.tool() | self.mcp.resource(uri) | self.mcp.prompt()
        log_name: str,  # for nice logging
    ) -> None:
        # Get parameter definitions
        parameters = endpoint_def.parameters or []

        # Create function signature with proper Pydantic type annotations
        # Include Context as the first parameter for accessing session_id
        param_annotations = {"ctx": FastMCPContext}
        param_signatures = ["ctx"]

        # Sort parameters so required (no default) come before optional (with default)
        # This is necessary for valid Python function signatures
        def has_default(param_model: ParamDefinitionModel) -> bool:
            param_dump = param_model.model_dump(mode="python", exclude_unset=True, by_alias=True)
            return "default" in param_dump

        sorted_parameters = [p for p in parameters if not has_default(p)] + [
            p for p in parameters if has_default(p)
        ]

        for param in sorted_parameters:
            param_schema = param.model_dump(mode="python", exclude_unset=True, by_alias=True)
            param_name = param.name
            param_type = self._json_schema_to_python_type(param, endpoint_type)
            param_annotations[param_name] = param_type

            # Create string representation for makefun with default values
            if "default" in param_schema:
                # Parameter has a default value, make it optional in signature
                default_value = repr(param_schema["default"])
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

            # Get the user context from the context variable (set by auth middleware)
            user_context = get_user_context()

            # Determine endpoint name early for use in span and metrics
            name: str
            if endpoint_key == "resource":
                name = cast(str, getattr(endpoint_def, "uri", "unknown"))
            else:
                name = cast(str, getattr(endpoint_def, "name", "unnamed"))

            # Create root span for endpoint execution with all MXCP-specific attributes
            with traced_operation(
                "mxcp.endpoint.execute",
                attributes={
                    "mxcp.endpoint.name": name,
                    "mxcp.endpoint.type": endpoint_key,
                },
            ) as span:
                try:
                    logger.info(f"Calling {log_name} {name} with: {kwargs}")
                    if user_context:
                        logger.info(
                            f"Authenticated user: {user_context.username} (provider: {user_context.provider})"
                        )
                        # Add auth attributes to span
                        if span:
                            span.set_attribute("mxcp.auth.authenticated", True)
                            span.set_attribute("mxcp.auth.provider", user_context.provider)
                    else:
                        if span:
                            span.set_attribute("mxcp.auth.authenticated", False)

                    # Add session ID to span if available
                    if span and mcp_session_id:
                        span.set_attribute("mxcp.session.id", mcp_session_id)

                    # run through new SDK executor (handles type conversion automatically)
                    if self.runtime_environment is None:
                        raise RuntimeError("Execution engine not initialized")

                    # Increment concurrent executions gauge
                    increment_gauge(
                        "mxcp.endpoint.concurrent_executions",
                        attributes={"endpoint": name, "type": endpoint_key},
                        description="Currently running endpoint executions",
                    )

                    # Use the common execution wrapper with policy info
                    result, policy_info = await self._execute(
                        endpoint_type=endpoint_type.value,
                        name=name,
                        params=kwargs,  # No manual conversion needed - SDK handles it
                        user_context=user_context,
                        with_policy_info=True,
                        request_headers=request_headers,  # Pass the FastMCP request headers
                        mcp_ctx=ctx,
                    )

                    # Add policy decision to span after execution
                    if span and policy_info.get("policy_decision"):
                        span.set_attribute("mxcp.policy.decision", policy_info["policy_decision"])
                        if policy_info.get("policies_evaluated"):
                            span.set_attribute(
                                "mxcp.policy.rules_evaluated",
                                len(policy_info["policies_evaluated"]),
                            )

                    logger.debug(f"Result: {json.dumps(result, indent=2, default=str)}")
                    return result

                except Exception as e:
                    status = "error"
                    error_msg = str(e)
                    logger.error(f"Error executing {log_name} {name}:\n{traceback.format_exc()}")
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

                    # Track endpoint execution for anonymous analytics
                    # Note: endpoint name is hashed for privacy
                    track_endpoint_execution(
                        endpoint_type=endpoint_key,
                        endpoint_name=name,
                        success=(status == "success"),
                        duration_ms=duration_ms,
                        transport=caller,
                    )

                    # Log the audit event
                    if self.audit_logger:
                        try:
                            await self.audit_logger.log_event(
                                caller_type=cast(
                                    Literal["cli", "http", "stdio", "api", "system", "unknown"],
                                    caller,
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
                        except Exception as audit_error:
                            # Log audit failure prominently - this should never be silent
                            logger.error(
                                f"CRITICAL: Audit logging failed for endpoint '{name}': {audit_error}",
                                exc_info=True,
                            )

        # -------------------------------------------------------------------
        # Wrap with authentication middleware
        # -------------------------------------------------------------------
        authenticated_body = self.auth_middleware.require_auth(_body)

        # -------------------------------------------------------------------
        # Create function with proper signature and annotations using makefun
        # -------------------------------------------------------------------
        if endpoint_key == "resource":
            original_name = cast(str, getattr(endpoint_def, "uri", "unknown"))
        else:
            original_name = cast(str, getattr(endpoint_def, "name", "unnamed"))
        func_name = self.mcp_name_to_py(original_name)

        # Create the function with proper signature
        handler = create_function(signature, authenticated_body, func_name=func_name)

        # Set the annotations for Pydantic introspection
        handler.__annotations__ = param_annotations

        # Add return type annotation if return schema is defined
        return_schema = (
            endpoint_def.return_
            if isinstance(endpoint_def, ToolDefinitionModel | ResourceDefinitionModel)
            else None
        )
        if return_schema:
            return_type = self._create_pydantic_model_from_schema(
                return_schema, f"{original_name}Return", endpoint_type
            )
            handler.__annotations__["return"] = return_type

        # Finally register the function with FastMCP -------------------------
        # Use original name for FastMCP registration
        decorator(handler)
        logger.info(f"Registered {log_name}: {original_name} (function: {func_name})")

    def _register_tool(self, tool_def: ToolDefinitionModel) -> None:
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
                name=tool_def.name,
                description=tool_def.description,
                annotations=annotations,
            ),
            log_name="tool",
        )

    def _register_resource(self, resource_def: ResourceDefinitionModel) -> None:
        """Register a resource endpoint with MCP.

        Args:
            resource_def: The resource definition from YAML
        """
        self._build_and_register(
            EndpointType.RESOURCE,
            "resource",
            resource_def,
            decorator=self.mcp.resource(
                resource_def.uri,
                name=resource_def.name,
                description=resource_def.description,
                mime_type=resource_def.mime_type,
            ),
            log_name="resource",
        )

    def _register_prompt(self, prompt_def: PromptDefinitionModel) -> None:
        """Register a prompt endpoint with MCP.

        Args:
            prompt_def: The prompt definition from YAML
        """
        self._build_and_register(
            EndpointType.PROMPT,
            "prompt",
            prompt_def,
            decorator=self.mcp.prompt(name=prompt_def.name, description=prompt_def.description),
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
        mcp_ctx: FastMCPContext | None = None,
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

        transport = self.transport_mode or "server"
        mcp_interface = FastMCPLogProxy(mcp_ctx) if mcp_ctx else None
        execution_context = build_execution_context(
            user_context=user_context,
            user_config=self.user_config,
            site_config=self.site_config,
            server_ref=self,
            request_headers=request_headers,
            transport=transport,
            mcp_interface=mcp_interface,
        )

        if with_policy_info:
            return await execute_endpoint_with_engine_and_policy(
                endpoint_type=endpoint_type,
                name=name,
                params=params,
                user_config=self.user_config,
                site_config=self.site_config,
                execution_engine=self.runtime_environment.execution_engine,
                execution_context=execution_context,
                skip_output_validation=False,
                user_context=user_context,
                server_ref=self,
            )
        else:
            return await execute_endpoint_with_engine(
                endpoint_type,
                name,
                params,
                self.user_config,
                self.site_config,
                self.runtime_environment.execution_engine,
                execution_context=execution_context,
                skip_output_validation=False,
                user_context=user_context,
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

        execution_context = build_execution_context(
            user_context=user_context,
            user_config=self.user_config,
            site_config=self.site_config,
            server_ref=self,
            transport=self.transport_mode or "server",
        )

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

                if validation_result.status != "ok":
                    logger.warning(
                        f"Skipping invalid endpoint {path}: {validation_result.message or 'Unknown error'}"
                    )
                    self.skipped_endpoints.append(
                        EndpointErrorModel(
                            path=str(path),
                            error=validation_result.message or "Unknown error",
                        )
                    )
                    continue

                if endpoint_def is None:
                    logger.warning(f"Endpoint definition is None for {path}")
                    continue

                if endpoint_def.tool is not None:
                    self._register_tool(endpoint_def.tool)
                    logger.info(f"Registered tool endpoint from {path}: {endpoint_def.tool.name}")
                elif endpoint_def.resource is not None:
                    self._register_resource(endpoint_def.resource)
                    logger.info(
                        f"Registered resource endpoint from {path}: {endpoint_def.resource.uri}"
                    )
                elif endpoint_def.prompt is not None:
                    self._register_prompt(endpoint_def.prompt)
                    logger.info(
                        f"Registered prompt endpoint from {path}: {endpoint_def.prompt.name}"
                    )
                else:
                    logger.warning(f"Unknown endpoint type in {path}: {endpoint_def}")
            except Exception as e:
                logger.error(f"Error registering endpoint {path}: {e}", exc_info=True)
                self.skipped_endpoints.append(EndpointErrorModel(path=str(path), error=str(e)))
                continue

        # Register DuckDB features if enabled
        if self.enable_sql_tools:
            self._register_duckdb_features()

        # Report skipped endpoints
        if self.skipped_endpoints:
            logger.warning(f"Skipped {len(self.skipped_endpoints)} invalid endpoints:")
            for skipped in self.skipped_endpoints:
                logger.warning(f"  - {skipped.path}: {skipped.error}")

    async def _initialize_oauth_server(self) -> None:
        """Initialize OAuth server persistence if enabled."""
        if self.oauth_server:
            try:
                await self.oauth_server.initialize()
                logger.info("OAuth server initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OAuth server: {e}")
                raise

    async def run(self, transport: str = "streamable-http") -> None:
        """Run the MCP server.

        Args:
            transport: The transport to use ("streamable-http", "sse", or "stdio")

        Raises:
            ValueError: If transport is not one of the supported values
        """
        # Validate transport early
        valid_transports = ["stdio", "sse", "streamable-http"]
        if transport not in valid_transports:
            raise ValueError(
                f"Unknown transport: {transport}. Must be one of: {', '.join(valid_transports)}"
            )

        reload_started = False
        try:
            logger.info("Starting MCP server...")
            # Store transport mode for use in handlers
            self.transport_mode = transport

            # Note: Admin API will be started in the FastMCP lifespan event
            # when the uvicorn event loop is running. This ensures the admin
            # API's uvicorn server runs in the same event loop as the main server.

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
                    await asyncio.wait_for(self._initialize_oauth_server(), timeout=10.0)
                except asyncio.TimeoutError:
                    raise RuntimeError("OAuth server initialization timed out") from None
                except Exception as exc:
                    # Don't continue if OAuth is enabled but initialization failed
                    raise RuntimeError(f"OAuth server initialization failed: {exc}") from exc

            loop = asyncio.get_running_loop()
            self._signal_loop = loop

            # Start reload manager, then register signal handlers.
            # Order matters: reload_manager must be started before signals can trigger reloads.
            self.reload_manager.start()
            reload_started = True
            self._register_signal_handlers()

            await self._initialize_audit_logger()

            # Start server
            await self._run_admin_api_and_transport(transport)
            logger.info("MCP server started successfully.")
        except Exception as e:
            logger.error(f"Error running MCP server: {e}")
            raise
        finally:
            if reload_started:
                logger.info("Stopping reload manager")
                await self.reload_manager.stop()
                logger.info("Reload manager stopped")

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
            auth_config = self.active_profile.auth
            auth_authorization = auth_config.authorization
            supported_scopes = auth_authorization.required_scopes if auth_authorization else []

            metadata = {
                "resource": base_url,
                "authorization_servers": [base_url],
                "scopes_supported": supported_scopes,
                "bearer_methods_supported": ["header"],
                "resource_documentation": f"{base_url}/docs",
            }

            return JSONResponse(content=metadata, headers={"Content-Type": "application/json"})
