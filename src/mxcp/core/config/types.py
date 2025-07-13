"""
Type definitions for resolver configuration.

This module defines TypedDict classes for the resolver configuration structure
that supports vault, 1password, file, and environment variable resolution.
"""

from typing import TypedDict, Optional


class VaultConfigOptional(TypedDict, total=False):
    """Optional fields for VaultConfig."""
    address: Optional[str]
    token_env: Optional[str]


class VaultConfig(VaultConfigOptional):
    """Configuration for Vault integration."""
    enabled: bool  # Required


class OnePasswordConfigOptional(TypedDict, total=False):
    """Optional fields for OnePasswordConfig."""
    token_env: Optional[str]


class OnePasswordConfig(OnePasswordConfigOptional):
    """Configuration for 1Password integration."""
    enabled: bool  # Required


class ResolverConfig(TypedDict, total=False):
    """
    Root configuration for all resolvers.
    
    This is the structure of the new config.yaml file:
    
    config:
      vault:
        enabled: true
        address: "https://vault.example.com"
        token_env: "VAULT_TOKEN"
      onepassword:
        enabled: true
        token_env: "OP_SERVICE_ACCOUNT_TOKEN"
    """
    vault: Optional[VaultConfig]
    onepassword: Optional[OnePasswordConfig] 