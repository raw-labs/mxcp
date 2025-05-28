from typing import TypedDict, List, Dict, Optional, Literal, Any, Union

# Site Config Types
class ExtensionDefinition(TypedDict, total=False):
    name: str
    repo: Optional[str]  # Optional repo name for community/nightly extensions

class PluginDefinition(TypedDict):
    name: str
    module: str
    config: Optional[str]

class DbtConfig(TypedDict):
    enabled: Optional[bool]
    models: Optional[str]
    manifest_path: Optional[str]

class SqlToolsConfig(TypedDict):
    enabled: Optional[bool]

class PythonConfig(TypedDict):
    path: Optional[str]

class DuckDBConfig(TypedDict):
    path: Optional[str]
    readonly: Optional[bool]

class DriftConfig(TypedDict):
    path: Optional[str]

class SecretDefinition(TypedDict):
    name: str
    type: str
    parameters: Dict[str, str]

class PluginConfig(TypedDict):
    config: Dict[str, Dict[str, str]]

class ProfileConfig(TypedDict):
    duckdb: Optional[DuckDBConfig]
    drift: Optional[DriftConfig]
    secrets: Optional[List[SecretDefinition]]
    plugin: Optional[PluginConfig]

class SiteConfig(TypedDict):
    mxcp: str
    project: str
    profile: str
    secrets: Optional[List[str]]
    plugin: Optional[List[PluginDefinition]]
    extensions: Optional[List[Union[str, ExtensionDefinition]]]
    dbt: Optional[DbtConfig]
    python: Optional[PythonConfig]
    sql_tools: Optional[SqlToolsConfig]
    profiles: Dict[str, ProfileConfig]

# User Config Types
class VaultConfig(TypedDict):
    enabled: bool
    address: Optional[str]
    token_env: Optional[str]

class HttpTransportConfig(TypedDict):
    port: Optional[int]
    host: Optional[str]
    scheme: Optional[Literal["http", "https"]]
    base_url: Optional[str]
    trust_proxy: Optional[bool]

class TransportConfig(TypedDict):
    provider: Optional[str]
    http: Optional[HttpTransportConfig]

# Auth Config Types
class OAuthClientConfig(TypedDict):
    client_id: str
    name: str
    client_secret: Optional[str]
    redirect_uris: Optional[List[str]]
    grant_types: Optional[List[Literal["authorization_code", "refresh_token"]]]
    scopes: Optional[List[str]]

class GitHubAuthConfig(TypedDict):
    client_id: str
    client_secret: str
    scope: Optional[str]
    callback_path: str
    auth_url: str
    token_url: str

class AuthConfig(TypedDict):
    provider: Optional[Literal["none", "github"]]
    clients: Optional[List[OAuthClientConfig]]
    github: Optional[GitHubAuthConfig]

class ProjectConfig(TypedDict):
    default: Optional[str]
    profiles: Dict[str, ProfileConfig]

class UserConfig(TypedDict):
    mxcp: str
    auth: Optional[AuthConfig]
    vault: Optional[VaultConfig]
    transport: Optional[TransportConfig]
    projects: Dict[str, ProjectConfig]