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

class SiteProfileConfig(TypedDict, total=False):
    duckdb: Optional[SiteDuckDBConfig]
    drift: Optional[SiteDriftConfig]

class SiteConfig(TypedDict):
    mxcp: str
    project: str
    profile: str
    secrets: Optional[List[str]]  # List of secret names (not definitions)
    plugin: Optional[List[SitePluginDefinition]]
    extensions: Optional[List[Union[str, SiteExtensionDefinition]]]
    dbt: Optional[SiteDbtConfig]
    sql_tools: Optional[SiteSqlToolsConfig]
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


class UserAuthorizationConfig(TypedDict, total=False):
    required_scopes: Optional[List[str]]

class UserAuthConfig(TypedDict, total=False):
    provider: Optional[Literal["none", "github", "atlassian", "salesforce"]]
    clients: Optional[List[UserOAuthClientConfig]]
    github: Optional[UserGitHubAuthConfig]
    atlassian: Optional[UserAtlassianAuthConfig]
    salesforce: Optional[UserSalesforceAuthConfig]
    authorization: Optional[UserAuthorizationConfig]

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
    transport: Optional[UserTransportConfig]