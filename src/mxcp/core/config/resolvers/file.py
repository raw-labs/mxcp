"""
File resolver.

This module provides the FileResolver class for resolving file references
like file:///path/to/file.
"""

import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ResolverPlugin

logger = logging.getLogger(__name__)


class FileResolver(ResolverPlugin):
    """Resolver for file references like file:///path/to/file."""
    
    FILE_URL_PATTERN = re.compile(r'file://(.+)')
    
    @property
    def name(self) -> str:
        return "file"
    
    @property
    def url_patterns(self) -> List[str]:
        return [r'file://(.+)']
    
    def can_resolve(self, reference: str) -> bool:
        return reference.startswith('file://')
    
    def resolve(self, reference: str) -> str:
        match = self.FILE_URL_PATTERN.match(reference)
        if not match:
            raise ValueError(f"Invalid file reference: {reference}")
        
        file_path = Path(match.group(1))
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            return file_path.read_text(encoding='utf-8').strip()
        except Exception as e:
            raise ValueError(f"Failed to read file {file_path}: {e}") 