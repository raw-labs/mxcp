"""
Unified module for external configuration reference handling.

This module provides a single source of truth for:
- Reference patterns (${ENV_VAR}, vault://, file://)
- Resolution functions
- Reference detection and interpolation
"""
import os
import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Regular expression patterns for external references
ENV_VAR_PATTERN = re.compile(r'\${([A-Za-z0-9_]+)}')
VAULT_URL_PATTERN = re.compile(r'vault://([^#]+)(?:#(.+))?')
FILE_URL_PATTERN = re.compile(r'file://(.+)')
ONEPASSWORD_URL_PATTERN = re.compile(r'op://([^/]+)/([^/]+)/([^/?]+)(?:\?attribute=(otp))?$')


def is_external_reference(value: Any) -> bool:
    """Check if a value contains any external reference."""
    if not isinstance(value, str):
        return False
    
    return (
        value.startswith('vault://') or
        value.startswith('file://') or
        value.startswith('op://') or
        ENV_VAR_PATTERN.search(value) is not None
    )


def detect_reference_type(value: str) -> Optional[str]:
    """Detect the type of external reference in a string value."""
    if value.startswith('vault://'):
        return 'vault'
    elif value.startswith('file://'):
        return 'file'
    elif value.startswith('op://'):
        return 'onepassword'
    elif ENV_VAR_PATTERN.search(value):
        return 'env'
    return None


def resolve_env_var(value: str) -> str:
    """Resolve environment variable references in a string.
    
    Args:
        value: String potentially containing ${ENV_VAR} references
        
    Returns:
        String with all environment variables resolved
        
    Raises:
        ValueError: If an environment variable is not set
    """
    matches = ENV_VAR_PATTERN.findall(value)
    if not matches:
        return value
    
    result = value
    for env_var in matches:
        if env_var not in os.environ:
            raise ValueError(f"Environment variable {env_var} is not set")
        result = result.replace(f"${{{env_var}}}", os.environ[env_var])
    
    return result


def resolve_vault_url(vault_url: str, vault_config: Optional[Dict[str, Any]]) -> str:
    """Resolve a vault:// URL to retrieve the secret value.
    
    Args:
        vault_url: The vault:// URL to resolve (e.g., vault://secret/myapp#password)
        vault_config: The vault configuration from user config
        
    Returns:
        The resolved secret value
        
    Raises:
        ValueError: If vault is not configured or URL is invalid
        ImportError: If hvac library is not available
    """
    if not vault_config or not vault_config.get('enabled', False):
        raise ValueError(f"Vault URL '{vault_url}' found but Vault is not enabled in configuration")
    
    # Parse the vault URL
    match = VAULT_URL_PATTERN.match(vault_url)
    if not match:
        raise ValueError(f"Invalid vault URL format: '{vault_url}'. Expected format: vault://path/to/secret#key")
    
    secret_path = match.group(1)
    secret_key = match.group(2)
    
    if not secret_key:
        raise ValueError(f"Vault URL '{vault_url}' must specify a key after '#'. Expected format: vault://path/to/secret#key")
    
    try:
        import hvac
    except ImportError:
        raise ImportError("hvac library is required for Vault integration. Install with: pip install hvac")
    
    # Get Vault configuration
    vault_address = vault_config.get('address')
    if not vault_address:
        raise ValueError("Vault address must be configured when using vault:// URLs")
    
    token_env = vault_config.get('token_env', 'VAULT_TOKEN')
    vault_token = os.environ.get(token_env)
    if not vault_token:
        raise ValueError(f"Vault token not found in environment variable '{token_env}'")
    
    # Initialize Vault client
    try:
        client = hvac.Client(url=vault_address, token=vault_token)
        
        if not client.is_authenticated():
            raise ValueError("Failed to authenticate with Vault")
        
        # Read the secret - try KV v2 first, then fall back to KV v1
        try:
            response = client.secrets.kv.v2.read_secret_version(path=secret_path)
            secret_data = response['data']['data']
        except Exception:
            try:
                response = client.secrets.kv.v1.read_secret(path=secret_path)
                secret_data = response['data']
            except Exception as e:
                raise ValueError(f"Failed to read secret from Vault path '{secret_path}': {e}")
        
        if secret_key not in secret_data:
            raise ValueError(f"Key '{secret_key}' not found in Vault secret at path '{secret_path}'")
        
        return secret_data[secret_key]
        
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Error connecting to Vault: {e}")


def resolve_file_url(file_url: str) -> str:
    """Resolve a file:// URL to read the content from a local file.
    
    Args:
        file_url: The file:// URL to resolve
        
    Returns:
        The content of the file with whitespace stripped
        
    Raises:
        ValueError: If file path is invalid or file cannot be read
        FileNotFoundError: If the file does not exist
    """
    # Parse the file URL
    match = FILE_URL_PATTERN.match(file_url)
    if not match:
        raise ValueError(f"Invalid file URL format: '{file_url}'. Expected format: file://path/to/file")
    
    file_path_str = match.group(1)
    
    # Handle absolute paths (file:///path) vs relative paths (file://path)
    if file_path_str.startswith('/'):
        file_path = Path(file_path_str)
    else:
        file_path = Path.cwd() / file_path_str
    
    try:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
        
        content = file_path.read_text(encoding='utf-8').strip()
        
        if not content:
            logger.warning(f"File '{file_path}' is empty")
        
        return content
        
    except FileNotFoundError:
        raise
    except PermissionError as e:
        raise ValueError(f"Permission denied reading file '{file_path}': {e}")
    except Exception as e:
        raise ValueError(f"Error reading file '{file_path}': {e}")


def resolve_onepassword_url(op_url: str, op_config: Optional[Dict[str, Any]]) -> str:
    """Resolve a 1Password op:// URL to retrieve the secret value.
    
    Args:
        op_url: The op:// URL to resolve (e.g., op://vault/item/field or op://vault/item/field?attribute=otp)
        op_config: The 1Password configuration from user config
        
    Returns:
        The resolved secret value
        
    Raises:
        ValueError: If 1Password is not configured or URL is invalid
        ImportError: If onepassword-sdk library is not available
    """
    if not op_config or not op_config.get('enabled', False):
        raise ValueError(f"1Password URL '{op_url}' found but 1Password is not enabled in configuration")
    
    # Parse the 1Password URL
    match = ONEPASSWORD_URL_PATTERN.match(op_url)
    if not match:
        raise ValueError(f"Invalid 1Password URL format: '{op_url}'. Expected format: op://vault/item/field or op://vault/item/field?attribute=otp")
    
    vault_name = match.group(1)
    item_name = match.group(2)
    field_name = match.group(3)
    attribute = match.group(4)  # Optional attribute like 'otp'
    
    try:
        import onepassword  # type: ignore
    except ImportError:
        raise ImportError("onepassword-sdk library is required for 1Password integration. Install with: pip install 'mxcp[onepassword]'")
    
    # Build the secret reference - new SDK format
    if attribute == 'otp':
        secret_ref = f"op://{vault_name}/{item_name}/{field_name}?attribute=totp"
    else:
        secret_ref = f"op://{vault_name}/{item_name}/{field_name}"
    
    # Get the configured token
    token_env = op_config.get('token_env', 'OP_SERVICE_ACCOUNT_TOKEN')
    op_token = os.environ.get(token_env)
    if not op_token:
        raise ValueError(f"1Password service account token not found in environment variable '{token_env}'")
    
    # Temporarily set OP_SERVICE_ACCOUNT_TOKEN if needed
    # The 1Password SDK specifically requires this environment variable name
    original_token = os.environ.get('OP_SERVICE_ACCOUNT_TOKEN')
    token_was_set = original_token is not None
    
    try:
        # Only set the token if it's not already set to the correct value
        if original_token != op_token:
            os.environ['OP_SERVICE_ACCOUNT_TOKEN'] = op_token
        
        # Initialize 1Password client and resolve the secret
        client = onepassword.Client()
        secret_value = client.secrets.resolve(secret_ref)
        
        return secret_value
        
    except Exception as e:
        raise ValueError(f"Failed to resolve 1Password URL '{op_url}': {e}") from e
    finally:
        # Restore the original state to avoid global side effects
        if original_token != op_token:
            if token_was_set:
                os.environ['OP_SERVICE_ACCOUNT_TOKEN'] = original_token
            else:
                # Remove the variable if it wasn't originally set
                os.environ.pop('OP_SERVICE_ACCOUNT_TOKEN', None)


def resolve_value(value: str, vault_config: Optional[Dict[str, Any]] = None, op_config: Optional[Dict[str, Any]] = None) -> str:
    """Resolve a single string value that may contain external references.
    
    Args:
        value: String value to resolve
        vault_config: Optional vault configuration
        op_config: Optional 1Password configuration
        
    Returns:
        Resolved value
        
    Raises:
        ValueError: If resolution fails
    """
    if value.startswith('vault://'):
        return resolve_vault_url(value, vault_config)
    elif value.startswith('file://'):
        return resolve_file_url(value)
    elif value.startswith('op://'):
        return resolve_onepassword_url(value, op_config)
    else:
        return resolve_env_var(value)


def interpolate_all(config: Any, vault_config: Optional[Dict[str, Any]] = None, op_config: Optional[Dict[str, Any]] = None) -> Any:
    """Recursively interpolate all external references in a configuration.
    
    Args:
        config: Configuration structure (dict, list, or scalar)
        vault_config: Optional vault configuration
        op_config: Optional 1Password configuration
        
    Returns:
        Configuration with all references resolved
    """
    if isinstance(config, str) and is_external_reference(config):
        return resolve_value(config, vault_config, op_config)
    elif isinstance(config, dict):
        return {k: interpolate_all(v, vault_config, op_config) for k, v in config.items()}
    elif isinstance(config, list):
        return [interpolate_all(item, vault_config, op_config) for item in config]
    else:
        return config


def find_references(config: Any, path: Optional[List[Union[str, int]]] = None) -> List[Tuple[List[Union[str, int]], str, str]]:
    """Find all external references in a configuration structure.
    
    Args:
        config: Configuration to scan
        path: Current path in the configuration (for internal use)
        
    Returns:
        List of tuples: (path, value, ref_type)
        where path is the location, value is the reference string,
        and ref_type is 'vault', 'file', or 'env'
    """
    refs = []
    path = path or []
    
    if isinstance(config, str) and is_external_reference(config):
        ref_type = detect_reference_type(config)
        if ref_type:
            refs.append((path, config, ref_type))
    elif isinstance(config, dict):
        for key, value in config.items():
            refs.extend(find_references(value, path + [key]))
    elif isinstance(config, list):
        for i, item in enumerate(config):
            refs.extend(find_references(item, path + [i]))
    
    return refs 