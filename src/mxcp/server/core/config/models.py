from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

logger = logging.getLogger(__name__)


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class SiteExtensionDefinitionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    repo: Literal["community", "core_nightly"] | None = None


class SitePluginDefinitionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    module: str
    config: str | None = None


class SiteDbtConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    model_paths: list[str] = Field(default_factory=lambda: ["models"])
    analysis_paths: list[str] = Field(default_factory=lambda: ["analyses"])
    test_paths: list[str] = Field(default_factory=lambda: ["tests"])
    seed_paths: list[str] = Field(default_factory=lambda: ["seeds"])
    macro_paths: list[str] = Field(default_factory=lambda: ["macros"])
    snapshot_paths: list[str] = Field(default_factory=lambda: ["snapshots"])
    target_path: str = "target"
    clean_targets: list[str] = Field(default_factory=lambda: ["target", "dbt_packages"])

    @field_validator(
        "model_paths",
        "analysis_paths",
        "test_paths",
        "seed_paths",
        "macro_paths",
        "snapshot_paths",
        "clean_targets",
        mode="before",
    )
    @classmethod
    def _ensure_str_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [str(value)]


class SiteSqlToolsConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False


class SiteDuckDBConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str | None = None
    readonly: bool = False


class SiteDriftConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str | None = None


class SiteAuditConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    path: str | None = None


class SiteProfileConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    duckdb: SiteDuckDBConfigModel = Field(default_factory=SiteDuckDBConfigModel)
    drift: SiteDriftConfigModel = Field(default_factory=SiteDriftConfigModel)
    audit: SiteAuditConfigModel = Field(default_factory=SiteAuditConfigModel)


class SitePathsConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tools: str = "tools"
    resources: str = "resources"
    prompts: str = "prompts"
    evals: str = "evals"
    python: str = "python"
    plugins: str = "plugins"
    sql: str = "sql"
    drift: str = "drift"
    audit: str = "audit"
    data: str = "data"


class SiteConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mxcp: Literal[1] = 1
    project: str
    profile: str
    secrets: list[str] = Field(default_factory=list)
    plugin: list[SitePluginDefinitionModel] = Field(default_factory=list)
    extensions: list[SiteExtensionDefinitionModel] = Field(default_factory=list)
    dbt: SiteDbtConfigModel = Field(default_factory=SiteDbtConfigModel)
    sql_tools: SiteSqlToolsConfigModel = Field(default_factory=SiteSqlToolsConfigModel)
    paths: SitePathsConfigModel = Field(default_factory=SitePathsConfigModel)
    profiles: dict[str, SiteProfileConfigModel] = Field(default_factory=dict)

    @field_validator("secrets", mode="before")
    @classmethod
    def _normalize_secrets(cls, value: Any) -> list[str]:
        return _ensure_list(value)

    @field_validator("plugin", mode="before")
    @classmethod
    def _normalize_plugins(cls, value: Any) -> list[Any]:
        return _ensure_list(value)

    @field_validator("extensions", mode="before")
    @classmethod
    def _normalize_extensions(cls, value: Any) -> list[Any]:
        items = _ensure_list(value)
        normalized: list[Any] = []
        for item in items:
            if isinstance(item, str):
                normalized.append({"name": item})
            else:
                normalized.append(item)
        return normalized

    @field_validator("dbt", "sql_tools", "paths", mode="before")
    @classmethod
    def _default_object(cls, value: Any) -> Any:
        if value is None:
            return {}
        return value

    @field_validator("profiles", mode="before")
    @classmethod
    def _normalize_profiles(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return dict(value)
        raise TypeError("profiles must be a mapping")

    @model_validator(mode="after")
    def _apply_active_profile_defaults(self, info: ValidationInfo) -> SiteConfigModel:
        repo_root = Path(info.context.get("repo_root", Path.cwd())) if info.context else Path.cwd()

        profile_name = self.profile
        profiles = dict(self.profiles)
        active_profile = profiles.get(profile_name, SiteProfileConfigModel())

        duckdb = active_profile.duckdb
        if not duckdb.path:
            db_path = repo_root / self.paths.data / f"db-{profile_name}.duckdb"
            duckdb = duckdb.model_copy(update={"path": str(db_path)})

        env_duckdb_path = os.environ.get("MXCP_DUCKDB_PATH")
        if env_duckdb_path:
            logger.info("Overriding DuckDB path with MXCP_DUCKDB_PATH: %s", env_duckdb_path)
            duckdb = duckdb.model_copy(update={"path": env_duckdb_path})

        drift = active_profile.drift
        if not drift.path:
            drift_path = repo_root / self.paths.drift / f"drift-{profile_name}.json"
            drift = drift.model_copy(update={"path": str(drift_path)})

        audit = active_profile.audit
        if not audit.path:
            audit_path = repo_root / self.paths.audit / f"logs-{profile_name}.jsonl"
            audit = audit.model_copy(update={"path": str(audit_path)})

        audit_env = os.environ.get("MXCP_AUDIT_ENABLED", "").strip().lower()
        if audit_env in {"true", "1", "yes"}:
            audit = audit.model_copy(update={"enabled": True})
        elif audit_env in {"false", "0", "no"}:
            audit = audit.model_copy(update={"enabled": False})

        profiles[profile_name] = active_profile.model_copy(
            update={"duckdb": duckdb, "drift": drift, "audit": audit}
        )

        object.__setattr__(self, "profiles", profiles)
        updated_fields = set(getattr(self, "__pydantic_fields_set__", set()))
        updated_fields.add("profiles")
        object.__setattr__(self, "__pydantic_fields_set__", updated_fields)
        return self

    @field_serializer("extensions")
    def _serialize_extensions(
        self, extensions: list[SiteExtensionDefinitionModel]
    ) -> list[str | dict[str, str]]:
        serialized: list[str | dict[str, str]] = []
        for ext in extensions:
            if ext.repo:
                serialized.append({"name": ext.name, "repo": ext.repo})
            else:
                serialized.append(ext.name)
        return serialized


# Ensure forward references are resolved for helper usages.
SiteConfigModel.model_rebuild(_types_namespace={"Literal": Literal})


class UserSecretDefinitionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    type: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class UserPluginConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    config: dict[str, dict[str, str]] = Field(default_factory=dict)


class UserVaultConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    address: str | None = None
    token_env: str | None = None


class UserOnePasswordConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    token_env: str | None = None


class UserHttpTransportConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    port: int = 8000
    host: str = "localhost"
    scheme: Literal["http", "https"] = "http"
    base_url: str | None = None
    trust_proxy: bool = False
    stateless: bool = False


class UserTransportConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["streamable-http", "sse", "stdio"] = "streamable-http"
    http: UserHttpTransportConfigModel = Field(default_factory=UserHttpTransportConfigModel)


class UserOAuthClientModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str
    name: str
    client_secret: str | None = None
    redirect_uris: list[str] = Field(default_factory=list)
    grant_types: list[Literal["authorization_code", "refresh_token"]] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)


class UserAuthPersistenceConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["sqlite"] = "sqlite"
    path: str = Field(default_factory=lambda: str(Path.home() / ".mxcp" / "oauth.db"))
    auth_encryption_key: str | None = None


class UserAuthorizationConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_scopes: list[str] = Field(default_factory=list)


class UserGitHubAuthConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str
    client_secret: str
    scope: str | None = None
    callback_path: str
    auth_url: str
    token_url: str


class UserAtlassianAuthConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str
    client_secret: str
    # Required: provider scopes must be explicit in user config; we avoid SDK-side defaults.
    scope: str
    callback_path: str
    auth_url: str
    token_url: str


class UserSalesforceAuthConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str
    client_secret: str
    scope: str | None = None
    callback_path: str
    auth_url: str
    token_url: str


class UserKeycloakAuthConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str
    client_secret: str
    realm: str
    server_url: str
    scope: str | None = None
    callback_path: str


class UserGoogleAuthConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str
    client_secret: str
    # Required: provider scopes must be explicit in user config; we avoid SDK-side defaults.
    scope: str
    callback_path: str
    auth_url: str
    token_url: str


class UserAuthConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["none", "github", "atlassian", "salesforce", "keycloak", "google"] = "none"
    clients: list[UserOAuthClientModel] = Field(default_factory=list)
    github: UserGitHubAuthConfigModel | None = None
    atlassian: UserAtlassianAuthConfigModel | None = None
    salesforce: UserSalesforceAuthConfigModel | None = None
    keycloak: UserKeycloakAuthConfigModel | None = None
    google: UserGoogleAuthConfigModel | None = None
    authorization: UserAuthorizationConfigModel | None = None
    persistence: UserAuthPersistenceConfigModel | None = None

    @model_validator(mode="after")
    def _apply_defaults(self) -> UserAuthConfigModel:
        provider = self.provider or "none"
        persistence = self.persistence
        if provider != "none" and persistence is None:
            persistence = UserAuthPersistenceConfigModel()
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "persistence", persistence)
        updated_fields = set(getattr(self, "__pydantic_fields_set__", set()))
        updated_fields.update({"provider", "persistence"})
        object.__setattr__(self, "__pydantic_fields_set__", updated_fields)
        return self


class UserModelConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["claude", "openai"]
    api_key: str | None = None
    base_url: str | None = None
    timeout: int | None = None
    max_retries: int | None = None


class UserModelsConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    default: str | None = None
    models: dict[str, UserModelConfigModel] = Field(default_factory=dict)


class UserTracingConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    console_export: bool = False


class UserMetricsConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    export_interval: int = 60


class UserTelemetryConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    endpoint: str | None = None
    headers: dict[str, str] | None = None
    service_name: str | None = None
    service_version: str | None = None
    environment: str | None = None
    resource_attributes: dict[str, Any] | None = None
    tracing: UserTracingConfigModel | None = None
    metrics: UserMetricsConfigModel | None = None


class UserLoggingConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    path: str | None = None
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "WARNING"
    max_bytes: int = 10_485_760
    backup_count: int = 5


class UserProfileConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    secrets: list[UserSecretDefinitionModel] = Field(default_factory=list)
    plugin: UserPluginConfigModel = Field(default_factory=UserPluginConfigModel)
    auth: UserAuthConfigModel = Field(default_factory=UserAuthConfigModel)
    telemetry: UserTelemetryConfigModel | None = None


class UserProjectConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profiles: dict[str, UserProfileConfigModel] = Field(default_factory=dict)


class UserConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mxcp: Literal[1] = 1
    projects: dict[str, UserProjectConfigModel] = Field(default_factory=dict)
    vault: UserVaultConfigModel | None = None
    onepassword: UserOnePasswordConfigModel | None = None
    transport: UserTransportConfigModel = Field(default_factory=UserTransportConfigModel)
    models: UserModelsConfigModel | None = None
    logging: UserLoggingConfigModel = Field(default_factory=UserLoggingConfigModel)
