from typing import Any, Literal, TypedDict


# Site Config Types (mxcp-site.yml)
class SiteExtensionDefinition(TypedDict, total=False):
    name: str
    repo: str | None  # Optional repo name for community/nightly extensions


class SitePluginDefinition(TypedDict):
    name: str
    module: str
    config: str | None


class SiteDbtConfig(TypedDict, total=False):
    enabled: bool | None
    # dbt project configuration paths
    model_paths: list[str] | None
    analysis_paths: list[str] | None
    test_paths: list[str] | None
    seed_paths: list[str] | None
    macro_paths: list[str] | None
    snapshot_paths: list[str] | None
    target_path: str | None
    clean_targets: list[str] | None


class SiteSqlToolsConfig(TypedDict, total=False):
    enabled: bool | None


class SiteDuckDBConfig(TypedDict, total=False):
    path: str | None
    readonly: bool | None


class SiteDriftConfig(TypedDict, total=False):
    path: str | None


class SiteAuditConfig(TypedDict, total=False):
    enabled: bool | None
    path: str | None


class SiteProfileConfig(TypedDict, total=False):
    duckdb: SiteDuckDBConfig | None
    drift: SiteDriftConfig | None
    audit: SiteAuditConfig | None


class SitePathsConfig(TypedDict, total=False):
    tools: str | None
    resources: str | None
    prompts: str | None
    evals: str | None
    python: str | None
    plugins: str | None
    sql: str | None
    drift: str | None
    audit: str | None
    data: str | None


class SiteConfig(TypedDict):
    mxcp: str
    project: str
    profile: str
    secrets: list[str] | None  # List of secret names (not definitions)
    plugin: list[SitePluginDefinition] | None
    extensions: list[str | SiteExtensionDefinition] | None
    dbt: SiteDbtConfig | None
    sql_tools: SiteSqlToolsConfig | None
    paths: SitePathsConfig | None
    profiles: dict[str, SiteProfileConfig]


# User Config Types (~/.mxcp/config.yml)
class UserSecretDefinition(TypedDict):
    name: str
    type: str
    parameters: dict[str, Any]  # Can contain strings or nested objects


class UserPluginConfig(TypedDict, total=False):
    config: dict[str, dict[str, str]]


class UserVaultConfig(TypedDict):
    enabled: bool
    address: str | None
    token_env: str | None


class UserOnePasswordConfig(TypedDict):
    enabled: bool
    token_env: str | None


class UserHttpTransportConfig(TypedDict, total=False):
    port: int | None
    host: str | None
    scheme: Literal["http", "https"] | None
    base_url: str | None
    trust_proxy: bool | None
    stateless: bool | None


class UserTransportConfig(TypedDict, total=False):
    provider: Literal["streamable-http", "sse", "stdio"] | None
    http: UserHttpTransportConfig | None


class UserOAuthClientConfig(TypedDict):
    client_id: str
    name: str
    client_secret: str | None
    redirect_uris: list[str] | None
    grant_types: list[Literal["authorization_code", "refresh_token"]] | None
    scopes: list[str] | None


class UserGitHubAuthConfig(TypedDict):
    client_id: str
    client_secret: str
    scope: str | None
    callback_path: str
    auth_url: str
    token_url: str


class UserAtlassianAuthConfig(TypedDict):
    client_id: str
    client_secret: str
    scope: str | None
    callback_path: str
    auth_url: str
    token_url: str


class UserSalesforceAuthConfig(TypedDict):
    client_id: str
    client_secret: str
    scope: str | None
    callback_path: str
    auth_url: str
    token_url: str


class UserKeycloakAuthConfig(TypedDict):
    client_id: str
    client_secret: str
    realm: str
    server_url: str
    scope: str | None
    callback_path: str


class UserGoogleAuthConfig(TypedDict):
    client_id: str
    client_secret: str
    scope: str | None
    callback_path: str
    auth_url: str
    token_url: str


class UserAuthPersistenceConfig(TypedDict, total=False):
    type: Literal["sqlite"] | None
    path: str | None


class UserAuthorizationConfig(TypedDict, total=False):
    required_scopes: list[str] | None


class UserAuthConfig(TypedDict, total=False):
    provider: Literal["none", "github", "atlassian", "salesforce", "keycloak", "google"] | None
    cache_ttl: int | None  # Cache TTL in seconds for user context caching (default: 300)
    cleanup_interval: int | None  # Cleanup interval in seconds for OAuth mappings (default: 300)
    clients: list[UserOAuthClientConfig] | None
    github: UserGitHubAuthConfig | None
    atlassian: UserAtlassianAuthConfig | None
    salesforce: UserSalesforceAuthConfig | None
    keycloak: UserKeycloakAuthConfig | None
    google: UserGoogleAuthConfig | None
    authorization: UserAuthorizationConfig | None
    persistence: UserAuthPersistenceConfig | None


class UserModelConfig(TypedDict):
    type: Literal["claude", "openai"]
    api_key: str | None
    base_url: str | None  # For custom endpoints
    timeout: int | None  # Request timeout in seconds
    max_retries: int | None


class UserModelsConfig(TypedDict, total=False):
    default: str | None  # Default model to use
    models: dict[str, UserModelConfig] | None  # Model configurations


class UserTracingConfig(TypedDict, total=False):
    """Tracing-specific configuration."""

    enabled: bool | None
    console_export: bool | None  # For debugging - print spans to console


class UserLoggingConfig(TypedDict, total=False):
    """Application logging configuration."""

    enabled: bool | None  # Enable file logging
    path: str | None  # Path to log file
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None  # Log level
    max_bytes: int | None  # Max file size before rotation
    backup_count: int | None  # Number of backup files to keep


class UserMetricsConfig(TypedDict, total=False):
    """Metrics-specific configuration."""

    enabled: bool | None
    export_interval: int | None  # Export interval in seconds
    prometheus_port: int | None  # Optional Prometheus scrape endpoint


class UserTelemetryConfig(TypedDict, total=False):
    """Unified telemetry configuration treating all signals as equals."""

    enabled: bool  # Global enable/disable
    endpoint: str | None  # OTLP endpoint (e.g., http://localhost:4318)
    headers: dict[str, str] | None  # Additional headers for OTLP exporter
    service_name: str | None  # Override default service name
    service_version: str | None  # Service version
    environment: str | None  # Deployment environment
    resource_attributes: dict[str, Any] | None  # Additional resource attributes

    # Signal-specific configurations
    tracing: UserTracingConfig | None  # Tracing configuration
    metrics: UserMetricsConfig | None  # Metrics configuration


class UserProfileConfig(TypedDict, total=False):
    secrets: list[UserSecretDefinition] | None
    plugin: UserPluginConfig | None
    auth: UserAuthConfig | None
    telemetry: UserTelemetryConfig | None


class UserProjectConfig(TypedDict):
    profiles: dict[str, UserProfileConfig]


class UserConfig(TypedDict):
    mxcp: str
    projects: dict[str, UserProjectConfig]
    vault: UserVaultConfig | None
    onepassword: UserOnePasswordConfig | None
    transport: UserTransportConfig | None
    models: UserModelsConfig | None
    logging: UserLoggingConfig | None
