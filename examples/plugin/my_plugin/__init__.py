"""
Example MXCP Plugin

This plugin demonstrates how to create a simple MXCP plugin with Caesar cipher encryption capabilities
and optional user context integration for authentication-aware features.

Example usage:
    >>> plugin = MXCPPlugin({"rotation": 13})
    >>> plugin.encrypt("Hello, World!")  # Returns "Uryyb, Jbeyq!"
    >>> plugin.decrypt("Uryyb, Jbeyq!")  # Returns "Hello, World!"
    
With user context (when authentication is enabled):
    >>> plugin.get_user_info()  # Returns user information
"""

from typing import Dict, Any, Optional
from mxcp.plugins import MXCPBasePlugin, udf

class MXCPPlugin(MXCPBasePlugin):
    """Plugin that provides Caesar cipher encryption and decryption functions.
    
    This plugin implements the Caesar cipher, a type of substitution cipher where
    each letter in the plaintext is shifted a certain number of places down or up
    the alphabet. It also demonstrates how to use user context for authentication-aware features.
    
    Example:
        >>> plugin = MXCPPlugin({"rotation": 13})
        >>> plugin.encrypt("Hello, World!")  # Returns "Uryyb, Jbeyq!"
        >>> plugin.decrypt("Uryyb, Jbeyq!")  # Returns "Hello, World!"
    """
    
    def __init__(self, config: Dict[str, Any], user_context=None):
        """Initialize the plugin with configuration and optional user context.
        
        Args:
            config: Configuration dictionary containing:
                - rotation: Number of positions to shift (1-25), can be string or int
            user_context: Optional authenticated user context (for new plugins)
        """
        super().__init__(config, user_context)
        rotation = config.get("rotation", 13)
        
        # Convert string to int if needed
        if isinstance(rotation, str):
            try:
                rotation = int(rotation)
            except ValueError:
                raise ValueError("Rotation must be a valid integer")
                
        if not isinstance(rotation, int) or rotation < 1 or rotation > 25:
            raise ValueError("Rotation must be an integer between 1 and 25")
            
        self.rotation = rotation
        
    def __rotate_char(self, char: str, forward: bool = True) -> str:
        """Rotate a single character by the configured number of positions.
        
        Args:
            char: Character to rotate
            forward: True for encryption, False for decryption
            
        Returns:
            Rotated character
        """
        if not char.isalpha():
            return char
            
        # Determine the base ASCII value (a=97, A=65)
        base = ord('a') if char.islower() else ord('A')
        # Calculate the position in the alphabet (0-25)
        pos = ord(char) - base
        # Apply rotation (forward or backward)
        shift = self.rotation if forward else -self.rotation
        # Wrap around the alphabet and convert back to character
        return chr(base + ((pos + shift) % 26))
        
    @udf
    def encrypt(self, text: str) -> str:
        """Encrypt text using the Caesar cipher.
        
        Args:
            text: Text to encrypt
            
        Returns:
            Encrypted text
            
        Example:
            >>> plugin.encrypt("Hello, World!")  # Returns "Uryyb, Jbeyq!"
        """
        return ''.join(self.__rotate_char(c, True) for c in text)
        
    @udf
    def decrypt(self, text: str) -> str:
        """Decrypt text using the Caesar cipher.
        
        Args:
            text: Text to decrypt
            
        Returns:
            Decrypted text
            
        Example:
            >>> plugin.decrypt("Uryyb, Jbeyq!")  # Returns "Hello, World!"
        """
        return ''.join(self.__rotate_char(c, False) for c in text)
    
    @udf
    def encrypt_with_user_key(self, text: str) -> str:
        """Encrypt text using a user-specific rotation based on their username.
        
        This demonstrates how plugins can use user context to provide 
        personalized functionality.
        
        Args:
            text: Text to encrypt
            
        Returns:
            Text encrypted with user-specific key, or standard encryption if not authenticated
        """
        if self.is_authenticated():
            # Use username length as additional rotation factor
            username = self.get_username() or ""
            user_rotation = (self.rotation + len(username)) % 26
            # Temporarily modify rotation for this operation
            original_rotation = self.rotation
            self.rotation = user_rotation if user_rotation > 0 else 1
            result = self.encrypt(text)
            self.rotation = original_rotation  # Restore original rotation
            return result
        else:
            # Fall back to standard encryption
            return self.encrypt(text)
