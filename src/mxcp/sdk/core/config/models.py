"""Pydantic models for resolver configuration.

This module defines Pydantic model classes for the resolver configuration structure
that supports vault, 1password, file, and environment variable resolution.
"""

from pydantic import ConfigDict

from mxcp.sdk.models import SdkBaseModel


class VaultConfigModel(SdkBaseModel):
    """Configuration for Vault integration.

    HashiCorp Vault integration allows resolving secrets from a Vault server.
    The token is read from an environment variable for security.

    Attributes:
        enabled: Whether Vault integration is enabled
        address: The Vault server address (e.g., https://vault.example.com)
        token_env: Environment variable name containing the Vault token

    Example:
        >>> config = VaultConfigModel(
        ...     enabled=True,
        ...     address="https://vault.example.com",
        ...     token_env="VAULT_TOKEN"
        ... )
    """

    # Allow mutability for config merging
    model_config = ConfigDict(extra="forbid", frozen=False)

    enabled: bool = False
    address: str | None = None
    token_env: str | None = None


class OnePasswordConfigModel(SdkBaseModel):
    """Configuration for 1Password integration.

    1Password integration allows resolving secrets using a service account.
    The token is read from an environment variable for security.

    Attributes:
        enabled: Whether 1Password integration is enabled
        token_env: Environment variable name containing the 1Password service account token

    Example:
        >>> config = OnePasswordConfigModel(
        ...     enabled=True,
        ...     token_env="OP_SERVICE_ACCOUNT_TOKEN"
        ... )
    """

    # Allow mutability for config merging
    model_config = ConfigDict(extra="forbid", frozen=False)

    enabled: bool = False
    token_env: str | None = None


class ResolverConfigModel(SdkBaseModel):
    """Root configuration for all resolvers.

    This is the structure of the resolver configuration that can be loaded
    from a config.yaml file:

    ```yaml
    config:
      vault:
        enabled: true
        address: "https://vault.example.com"
        token_env: "VAULT_TOKEN"
      onepassword:
        enabled: true
        token_env: "OP_SERVICE_ACCOUNT_TOKEN"
    ```

    Attributes:
        vault: Configuration for HashiCorp Vault integration
        onepassword: Configuration for 1Password integration

    Example:
        >>> config = ResolverConfigModel(
        ...     vault=VaultConfigModel(enabled=True, address="https://vault.example.com"),
        ...     onepassword=OnePasswordConfigModel(enabled=True)
        ... )
    """

    # Allow mutability for config merging
    model_config = ConfigDict(extra="forbid", frozen=False)

    vault: VaultConfigModel | None = None
    onepassword: OnePasswordConfigModel | None = None
