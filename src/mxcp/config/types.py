from typing import TypedDict, List, Dict, Optional, Literal, Any, Union

# Site Config Types
class ExtensionDefinition(TypedDict, total=False):
    name: str
    repo: Optional[str]  # Optional repo name for community/nightly extensions

class DbtConfig(TypedDict):
    enabled: Optional[bool]
    models: Optional[str]
    manifest_path: Optional[str]

class PythonConfig(TypedDict):
    path: Optional[str]

class DuckDBConfig(TypedDict):
    path: Optional[str]
    readonly: Optional[bool]

class DriftConfig(TypedDict):
    path: Optional[str]

class GitHubCloudConfig(TypedDict):
    prefix_with_branch_name: Optional[bool]
    skip_prefix_for_branches: Optional[List[str]]

class ProfileConfig(TypedDict):
    duckdb: Optional[DuckDBConfig]
    drift: Optional[DriftConfig]

class CloudConfig(TypedDict):
    github: Optional[Dict[str, Any]]

class SiteConfig(TypedDict):
    mxcp: str
    project: str
    profile: str
    base_url: Optional[str]
    enabled: Optional[bool]
    secrets: Optional[List[str]]
    extensions: Optional[List[Union[str, ExtensionDefinition]]]
    dbt: Optional[DbtConfig]
    python: Optional[PythonConfig]
    profiles: Dict[str, ProfileConfig]
    cloud: Optional[CloudConfig]

# User Config Types
class VaultConfig(TypedDict):
    enabled: bool
    address: Optional[str]
    token_env: Optional[str]

class SecretDefinition(TypedDict):
    name: str
    type: str
    parameters: Dict[str, str]

class ProjectConfig(TypedDict):
    default: Optional[str]
    profiles: Dict[str, ProfileConfig]

class UserConfig(TypedDict):
    mxcp: str
    vault: Optional[VaultConfig]
    projects: Dict[str, ProjectConfig] 