from typing import TypedDict, List, Dict, Optional, Literal, Any

# Site Config Types
class AdapterDefinition(TypedDict):
    name: str
    package: str
    config: str

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
    raw: str
    project: str
    profile: str
    base_url: Optional[str]
    enabled: Optional[bool]
    secrets: Optional[List[str]]
    adapters: Optional[List[AdapterDefinition]]
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
    raw: str
    vault: Optional[VaultConfig]
    projects: Dict[str, ProjectConfig] 