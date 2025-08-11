# -*- coding: utf-8 -*-
"""Base audit writer implementation with redaction support.

This module provides the base implementation for audit writers,
including field redaction and business context extraction.
"""
import copy
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .types import AuditRecord, AuditSchema, FieldRedaction, AuditBackend, RedactionStrategy
from .redaction import apply_redaction


class AuditRedactor:
    """Handles field redaction based on strategies."""
    
    def __init__(self, default_strategy: RedactionStrategy = RedactionStrategy.FULL):
        """Initialize the redactor.
        
        Args:
            default_strategy: Default redaction strategy to use when none specified
        """
        self.default_strategy = default_strategy
    
    def redact_record(
        self, 
        record: AuditRecord, 
        redactions: List[FieldRedaction]
    ) -> AuditRecord:
        """Apply redactions to a record.
        
        Args:
            record: The audit record to redact
            redactions: List of field redactions to apply
            
        Returns:
            New AuditRecord with redactions applied
        """
        # Deep copy to avoid modifying original
        redacted = copy.deepcopy(record)
        
        # Apply redactions to input_data
        for redaction in redactions:
            self._apply_redaction(
                redacted.input_data,
                redaction.field_path,
                redaction.strategy,
                redaction.options
            )
            
            # Also apply to output_data if it's a dict
            if isinstance(redacted.output_data, dict):
                self._apply_redaction(
                    redacted.output_data,
                    redaction.field_path,
                    redaction.strategy,
                    redaction.options
                )
        
        return redacted
    
    def _apply_redaction(
        self,
        data: Dict[str, Any],
        field_path: str,
        strategy: RedactionStrategy,
        options: Optional[Dict[str, Any]]
    ) -> None:
        """Apply redaction to a specific field path.
        
        Args:
            data: Dictionary to redact (modified in place)
            field_path: Dot-notation path to field
            strategy: Redaction strategy to apply
            options: Options to pass to redaction strategy
        """
        parts = field_path.split('.')
        current = data
        
        # Navigate to the parent of the field
        for part in parts[:-1]:
            if isinstance(current, dict) and part in current:
                if not isinstance(current[part], dict):
                    # Can't navigate further
                    return
                current = current[part]
            else:
                # Path doesn't exist
                return
        
        # Apply redaction to the final field
        final_key = parts[-1]
        if isinstance(current, dict) and final_key in current:
            current[final_key] = apply_redaction(current[final_key], strategy, options)


class BaseAuditWriter(ABC):
    """Base implementation for audit writers with common functionality."""
    
    def __init__(self, redactor: Optional[AuditRedactor] = None):
        """Initialize the base writer.
        
        Args:
            redactor: Redactor to use for field redaction
        """
        self.redactor = redactor or AuditRedactor()
    
    async def apply_schema_policies(
        self,
        record: AuditRecord,
        schema: AuditSchema
    ) -> AuditRecord:
        """Apply schema-based policies to a record.
        
        Args:
            record: The audit record to process
            schema: The schema containing policies
            
        Returns:
            Processed audit record
        """
        # Make a copy to avoid modifying the original
        processed_record = copy.deepcopy(record)
        
        # Extract business context fields
        if schema.extract_fields:
            processed_record.business_context = self._extract_fields(
                processed_record.input_data,
                schema.extract_fields
            )
        
        # Apply redactions
        if schema.field_redactions:
            processed_record = self.redactor.redact_record(
                processed_record, 
                schema.field_redactions
            )
        
        return processed_record
    
    def _extract_fields(
        self, 
        data: Dict[str, Any], 
        field_paths: List[str]
    ) -> Dict[str, Any]:
        """Extract specified fields from data.
        
        Args:
            data: Source data dictionary
            field_paths: List of dot-notation paths to extract
            
        Returns:
            Dictionary with extracted fields
        """
        extracted = {}
        
        for path in field_paths:
            value = self._get_nested_value(data, path)
            if value is not None:
                # Use the last part of the path as the key
                key = path.split('.')[-1]
                # If there's a conflict, use the full path
                if key in extracted:
                    key = path.replace('.', '_')
                extracted[key] = value
        
        return extracted
    
    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get a value from nested dictionary using dot notation.
        
        Args:
            data: Source dictionary
            path: Dot-notation path
            
        Returns:
            Value at path or None if not found
        """
        parts = path.split('.')
        current = data
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        
        return current
    
