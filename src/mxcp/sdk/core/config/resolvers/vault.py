"""
Vault resolver.

This module provides the VaultResolver class for resolving HashiCorp Vault
references like vault://secret/path#key.
"""

import os
import re
import logging
from typing import Any, Dict, List, Optional

from .base import ResolverPlugin

logger = logging.getLogger(__name__)


class VaultResolver(ResolverPlugin):
    """Resolver for HashiCorp Vault references like vault://secret/path#key."""
    
    VAULT_URL_PATTERN = re.compile(r'vault://([^#]+)(?:#(.+))?')
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._vault_client = None
    
    @property
    def name(self) -> str:
        return "vault"
    
    @property
    def url_patterns(self) -> List[str]:
        return [r'vault://([^#]+)(?:#(.+))?']
    
    def can_resolve(self, reference: str) -> bool:
        return reference.startswith('vault://')
    
    def validate_config(self) -> bool:
        if not self.config.get('enabled', False):
            return False
        
        address = self.config.get('address')
        if not address:
            logger.error("Vault address is required")
            return False
        
        token_env = self.config.get('token_env', 'VAULT_TOKEN')
        if not os.environ.get(token_env):
            logger.error(f"Vault token environment variable not found: {token_env}")
            return False
        
        return True
    
    def resolve(self, reference: str) -> str:
        match = self.VAULT_URL_PATTERN.match(reference)
        if not match:
            raise ValueError(f"Invalid vault reference: {reference}")
        
        secret_path = match.group(1)
        key = match.group(2) or 'value'
        
        # Initialize vault client if needed
        if not self._vault_client:
            self._init_vault_client()
        
        try:
            # Read secret from vault
            if not self._vault_client:
                raise ValueError("Vault client not initialized")
            
            response = self._vault_client.secrets.kv.v2.read_secret_version(
                path=secret_path
            )
            
            secret_data = response['data']['data']
            if key not in secret_data:
                raise ValueError(f"Key '{key}' not found in vault secret: {secret_path}")
            
            return str(secret_data[key])
        
        except Exception as e:
            raise ValueError(f"Failed to read from vault: {e}")
    
    def cleanup(self) -> None:
        """Clean up the vault client."""
        if self._vault_client:
            # hvac Client doesn't have an explicit close method, but we can clean up our reference
            self._vault_client = None
    
    def _init_vault_client(self):
        """Initialize the Vault client."""
        try:
            import hvac
        except ImportError:
            raise ImportError("hvac package is required for Vault support. Install with: pip install hvac")
        
        address = self.config.get('address')
        token_env = self.config.get('token_env', 'VAULT_TOKEN')
        token = os.environ.get(token_env)
        
        self._vault_client = hvac.Client(url=address, token=token)
        
        if not self._vault_client.is_authenticated():
            raise ValueError("Failed to authenticate with Vault") 