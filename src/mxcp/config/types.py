from typing import TypedDict, List, Dict, Optional, Literal, Any, Union

# Site Config Types (mxcp-site.yml)
class SiteExtensionDefinition(TypedDict, total=False):
    name: str
    repo: Optional[str]  # Optional repo name for community/nightly extensions

class SitePluginDefinition(TypedDict):
    name: str
    module: str
    config: Optional[str]

class SiteDbtConfig(TypedDict, total=False):
    enabled: Optional[bool]
    # dbt project configuration paths
    model_paths: Optional[List[str]]
    analysis_paths: Optional[List[str]]
    test_paths: Optional[List[str]]
    seed_paths: Optional[List[str]]
    macro_paths: Optional[List[str]]
    snapshot_paths: Optional[List[str]]
    target_path: Optional[str]
    clean_targets: Optional[List[str]]

class SiteSqlToolsConfig(TypedDict, total=False):
    enabled: Optional[bool]

class SiteDuckDBConfig(TypedDict, total=False):
    path: Optional[str]
    readonly: Optional[bool]

class SiteDriftConfig(TypedDict, total=False):
    path: Optional[str]

class SiteAuditConfig(TypedDict, total=False):
    enabled: Optional[bool]
    path: Optional[str]

class SiteProfileConfig(TypedDict, total=False):
    duckdb: Optional[SiteDuckDBConfig]
    drift: Optional[SiteDriftConfig]
    audit: Optional[SiteAuditConfig]

class SitePathsConfig(TypedDict, total=False):
    tools: Optional[str]
    resources: Optional[str]
    prompts: Optional[str]
    evals: Optional[str]
    python: Optional[str]
    plugins: Optional[str]
    sql: Optional[str]
    drift: Optional[str]
    audit: Optional[str]
    data: Optional[str]

class SiteConfig(TypedDict):
    mxcp: str
    project: str
    profile: str
    secrets: Optional[List[str]]  # List of secret names (not definitions)
    plugin: Optional[List[SitePluginDefinition]]
    extensions: Optional[List[Union[str, SiteExtensionDefinition]]]
    dbt: Optional[SiteDbtConfig]
    sql_tools: Optional[SiteSqlToolsConfig]
    paths: Optional[SitePathsConfig]
    profiles: Dict[str, SiteProfileConfig]

# User Config Types (~/.mxcp/config.yml)
class UserSecretDefinition(TypedDict):
    name: str
    type: str
    parameters: Dict[str, Any]  # Can contain strings or nested objects

class UserPluginConfig(TypedDict, total=False):
    config: Dict[str, Dict[str, str]]

class UserVaultConfig(TypedDict):
    enabled: bool
    address: Optional[str]
    token_env: Optional[str]

class UserOnePasswordConfig(TypedDict):
    enabled: bool
    token_env: Optional[str]

class UserHttpTransportConfig(TypedDict, total=False):
    port: Optional[int]
    host: Optional[str]
    scheme: Optional[Literal["http", "https"]]
    base_url: Optional[str]
    trust_proxy: Optional[bool]
    stateless: Optional[bool]

class UserTransportConfig(TypedDict, total=False):
    provider: Optional[Literal["streamable-http", "sse", "stdio"]]
    http: Optional[UserHttpTransportConfig]

class UserOAuthClientConfig(TypedDict):
    client_id: str
    name: str
    client_secret: Optional[str]
    redirect_uris: Optional[List[str]]
    grant_types: Optional[List[Literal["authorization_code", "refresh_token"]]]
    scopes: Optional[List[str]]

class UserGitHubAuthConfig(TypedDict):
    client_id: str
    client_secret: str
    scope: Optional[str]
    callback_path: str
    auth_url: str
    token_url: str

class UserAtlassianAuthConfig(TypedDict):
    client_id: str
    client_secret: str
    scope: Optional[str]
    callback_path: str
    auth_url: str
    token_url: str

class UserSalesforceAuthConfig(TypedDict):
    client_id: str
    client_secret: str
    scope: Optional[str]
    callback_path: str
    auth_url: str
    token_url: str

class UserAuthPersistenceConfig(TypedDict, total=False):
    type: Optional[Literal["sqlite"]]
    path: Optional[str]

class UserAuthorizationConfig(TypedDict, total=False):
    required_scopes: Optional[List[str]]

class UserAuthConfig(TypedDict, total=False):
    provider: Optional[Literal["none", "github", "atlassian", "salesforce"]]
    clients: Optional[List[UserOAuthClientConfig]]
    github: Optional[UserGitHubAuthConfig]
    atlassian: Optional[UserAtlassianAuthConfig]
    salesforce: Optional[UserSalesforceAuthConfig]
    authorization: Optional[UserAuthorizationConfig]
    persistence: Optional[UserAuthPersistenceConfig]

class UserModelConfig(TypedDict):
    type: Literal["claude", "openai"]
    api_key: Optional[str]
    base_url: Optional[str]  # For custom endpoints
    timeout: Optional[int]  # Request timeout in seconds
    max_retries: Optional[int]
    
class UserModelsConfig(TypedDict, total=False):
    default: Optional[str]  # Default model to use
    models: Optional[Dict[str, UserModelConfig]]  # Model configurations

class UserProfileConfig(TypedDict, total=False):
    secrets: Optional[List[UserSecretDefinition]]
    plugin: Optional[UserPluginConfig]
    auth: Optional[UserAuthConfig]

class UserProjectConfig(TypedDict):
    profiles: Dict[str, UserProfileConfig]

class UserConfig(TypedDict):
    mxcp: str
    projects: Dict[str, UserProjectConfig]
    vault: Optional[UserVaultConfig]
    onepassword: Optional[UserOnePasswordConfig]
    transport: Optional[UserTransportConfig]
    models: Optional[UserModelsConfig]