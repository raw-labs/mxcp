"""Pydantic models for DuckDB infrastructure.

This module contains data structures for configuring and managing DuckDB
connections, extensions, plugins, and secrets.
"""

from typing import Any, Literal

from pydantic import Field

from mxcp.sdk.models import SdkBaseModel


class ExtensionDefinitionModel(SdkBaseModel):
    """Definition of a DuckDB extension to load.

    DuckDB extensions provide additional functionality like httpfs for HTTP
    file access, parquet for Parquet file support, etc.

    Attributes:
        name: Extension name (e.g., 'httpfs', 'parquet', 'json')
        repo: Optional repository name for community or nightly extensions.
            Use 'community' for community extensions or 'core_nightly' for
            nightly builds of core extensions.

    Example:
        >>> ext = ExtensionDefinitionModel(name="httpfs")
        >>> ext_nightly = ExtensionDefinitionModel(name="parquet", repo="core_nightly")
    """

    name: str
    repo: Literal["community", "core_nightly"] | None = None


class PluginDefinitionModel(SdkBaseModel):
    """Definition of a plugin to load.

    Plugins are Python modules that extend MXCP functionality, providing
    additional functions, types, or integrations.

    Attributes:
        name: Plugin name for identification
        module: Python module path (e.g., 'mxcp_plugin_example')
        config: Optional config key name for plugin-specific configuration

    Example:
        >>> plugin = PluginDefinitionModel(
        ...     name="confluence",
        ...     module="mxcp_plugin_confluence",
        ...     config="confluence"
        ... )
    """

    name: str
    module: str
    config: str | None = None


class PluginConfigModel(SdkBaseModel):
    """Configuration for plugins.

    Contains the path to the plugins directory and a mapping of plugin
    configurations keyed by plugin name.

    Attributes:
        plugins_path: Path to plugins directory relative to repository root
        config: Dictionary mapping plugin names to their configuration dicts

    Example:
        >>> plugin_config = PluginConfigModel(
        ...     plugins_path="plugins",
        ...     config={"confluence": {"base_url": "https://wiki.example.com"}}
        ... )
    """

    plugins_path: str
    config: dict[str, dict[str, str]] = Field(default_factory=dict)


class SecretDefinitionModel(SdkBaseModel):
    """Definition of a secret for injection into DuckDB.

    Secrets are used to provide credentials for accessing external resources
    like S3 buckets, HTTP endpoints, or databases.

    Attributes:
        name: Secret name for reference in SQL
        type: Secret type (e.g., 'S3', 'HTTP', 'GCS')
        parameters: Secret parameters (credentials, endpoints, etc.)

    Example:
        >>> secret = SecretDefinitionModel(
        ...     name="my_s3",
        ...     type="S3",
        ...     parameters={
        ...         "KEY_ID": "AKIAIOSFODNN7EXAMPLE",
        ...         "SECRET": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        ...         "REGION": "us-east-1"
        ...     }
        ... )
    """

    name: str
    type: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class DatabaseConfigModel(SdkBaseModel):
    """Configuration for DuckDB database.

    Specifies how to connect to and configure a DuckDB database instance.

    Attributes:
        path: Database file path. Use ':memory:' for in-memory database.
        readonly: Whether database is opened in readonly mode
        extensions: List of extensions to load on connection

    Example:
        >>> db_config = DatabaseConfigModel(
        ...     path="data/db.duckdb",
        ...     readonly=True,
        ...     extensions=[ExtensionDefinitionModel(name="httpfs")]
        ... )
    """

    path: str
    readonly: bool = False
    extensions: list[ExtensionDefinitionModel] = Field(default_factory=list)
