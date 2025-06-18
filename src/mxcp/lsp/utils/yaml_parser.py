"""
YAML parsing utilities for MXCP LSP.

This module provides safe YAML parsing capabilities for MXCP tool definitions,
extracting SQL code blocks and parameter definitions while maintaining security.

Security Note:
This module uses safe_load to prevent arbitrary code execution from malicious YAML files.
"""

from yaml import safe_load, compose
import yaml
from typing import Optional, Tuple
from pathlib import Path
import logging
from .models import Parameter
from lsprotocol import types

logger = logging.getLogger(__name__)


class YamlParsingError(Exception):
    """Raised when YAML parsing fails in a way that affects LSP functionality."""
    pass


class YamlParser:
    """
    Safe YAML parser for MXCP tool definitions.
    
    This parser extracts SQL code blocks and parameters from MXCP YAML files
    while maintaining security by using safe_load and validating inputs.
    
    Security Features:
    - Uses yaml.safe_load to prevent code execution
    - Validates file paths and URIs
    - Handles malformed YAML gracefully
    - Limits resource consumption
    """
    
    def __init__(self, yaml_string: str, document_uri: Optional[str] = None):
        """
        Initialize the YAML parser with safe loading.
        
        Args:
            yaml_string: The YAML content to parse
            document_uri: Optional URI of the document for error reporting
            
        Raises:
            YamlParsingError: If YAML parsing fails critically
        """
        self.yaml_string = yaml_string
        self.document_uri = document_uri or "unknown"
        self.yaml_object = None
        self.code = None
        self.code_span = None
        
        # Validate input
        self._validate_input()
        
        # Parse YAML safely
        self._parse_yaml()
        
        # Extract code and span information
        self.code = self._get_code()
        self.code_span = self._get_code_span()

    def _validate_input(self) -> None:
        """
        Validate the input YAML string and document URI.
        
        Raises:
            YamlParsingError: If input validation fails
        """
        if not isinstance(self.yaml_string, str):
            raise YamlParsingError(f"YAML input must be a string, got {type(self.yaml_string)}")
        
        if len(self.yaml_string) > 10 * 1024 * 1024:  # 10MB limit
            raise YamlParsingError("YAML file too large (>10MB)")
        
        # Validate document URI if provided
        if self.document_uri != "unknown":
            try:
                # Basic URI validation - ensure it's a valid file path or URI
                if self.document_uri.startswith('file://'):
                    # Validate file URI path
                    path_part = self.document_uri[7:]  # Remove 'file://' prefix
                    Path(path_part).resolve()  # This will raise if path is invalid
                elif not self.document_uri.startswith(('http://', 'https://')):
                    # Assume it's a file path
                    Path(self.document_uri).resolve()
            except Exception as e:
                logger.warning(f"Invalid document URI '{self.document_uri}': {e}")

    def _parse_yaml(self) -> None:
        """
        Safely parse the YAML content.
        
        Uses yaml.safe_load to prevent arbitrary code execution.
        """
        try:
            # Use safe_load to prevent code execution vulnerabilities
            self.yaml_object = safe_load(self.yaml_string)
            logger.debug(f"Successfully parsed YAML from {self.document_uri}")
            
        except yaml.YAMLError as e:
            logger.warning(f"YAML parsing error in {self.document_uri}: {e}")
            self.yaml_object = None
            
        except Exception as e:
            logger.error(f"Unexpected error parsing YAML in {self.document_uri}: {e}")
            self.yaml_object = None

    def get_parameters(self) -> Optional[list[Parameter]]:
        """
        Get the parameters from the YAML object.
        
        Returns:
            List of Parameter objects or None if no parameters found
            
        Raises:
            YamlParsingError: If parameter structure is malformed
        """
        if not self._is_valid_mxcp_structure():
            return None
            
        try:
            parameters_data = self.yaml_object["tool"]["parameters"]
            if not isinstance(parameters_data, list):
                logger.warning(f"Parameters must be a list in {self.document_uri}")
                return None
                
            parameters = []
            for i, param_data in enumerate(parameters_data):
                try:
                    if not isinstance(param_data, dict):
                        logger.warning(f"Parameter {i} must be a dict in {self.document_uri}")
                        continue
                        
                    # Validate required fields
                    if "name" not in param_data or "type" not in param_data:
                        logger.warning(f"Parameter {i} missing required fields in {self.document_uri}")
                        continue
                    
                    parameter = Parameter(
                        name=str(param_data["name"]),
                        type=str(param_data["type"]),
                        description=param_data.get("description"),
                        default=param_data.get("default")
                    )
                    parameters.append(parameter)
                    
                except Exception as e:
                    logger.warning(f"Error processing parameter {i} in {self.document_uri}: {e}")
                    continue
                    
            return parameters if parameters else None
            
        except KeyError:
            return None
        except Exception as e:
            logger.error(f"Error extracting parameters from {self.document_uri}: {e}")
            return None

    def should_provide_lsp(
        self, cursor_position: Optional[types.Position] = None
    ) -> bool:
        """
        Check if LSP should be provided for this YAML document.
        
        Args:
            cursor_position: Optional cursor position to check
            
        Returns:
            True if LSP features should be provided
        """
        return (
            self._is_valid_mxcp_structure()
            and self._has_inline_sql_code()
            and self._cursor_in_code_range(cursor_position)
        )

    def _is_valid_mxcp_structure(self) -> bool:
        """
        Check if the YAML has the basic MXCP tool structure.
        
        Returns:
            True if structure is valid for MXCP processing
        """
        try:
            return (
                self.yaml_object is not None
                and isinstance(self.yaml_object, dict)
                and "mxcp" in self.yaml_object
                and "tool" in self.yaml_object
                and isinstance(self.yaml_object["tool"], dict)
                and "source" in self.yaml_object["tool"]
                and isinstance(self.yaml_object["tool"]["source"], dict)
                and "code" in self.yaml_object["tool"]["source"]
            )
        except (TypeError, AttributeError):
            return False

    def _has_inline_sql_code(self) -> bool:
        """
        Check if the code is inline SQL (not a .sql file reference).
        
        Returns:
            True if code is inline SQL that can be processed
        """
        if not self._is_valid_mxcp_structure():
            return False
        
        try:
            code = self.yaml_object["tool"]["source"]["code"]
            return (
                isinstance(code, str)
                and code.strip()  # Not empty
                and not code.strip().lower().endswith(".sql")  # Not a file reference
            )
        except (TypeError, KeyError):
            return False

    def _cursor_in_code_range(self, cursor_position: Optional[types.Position]) -> bool:
        """
        Check if the cursor position is within the code block range.
        
        Args:
            cursor_position: Position to check
            
        Returns:
            True if position is within code range or position is None
        """
        if cursor_position is None:
            return True
        
        if self.code_span is None:
            return False
        
        try:
            return (
                self.code_span[0].line - 1 <= cursor_position.line <= self.code_span[1].line + 1
            )
        except (AttributeError, TypeError):
            return False

    def _get_code(self) -> Optional[str]:
        """
        Get the SQL code from the YAML object.
        
        Returns:
            SQL code string or None if not available
        """
        if not self._has_inline_sql_code():
            return None
            
        try:
            return self.yaml_object["tool"]["source"]["code"]
        except (KeyError, TypeError):
            return None

    def _get_code_span(self) -> Optional[Tuple[types.Position, types.Position]]:
        """
        Get the position span of the SQL code block in the document.
        
        Returns:
            Tuple of (start_position, end_position) or None if not found
            
        Note:
            This method uses yaml.compose which is safe for position tracking
            but should only be used on already validated YAML content.
        """
        if not self.yaml_string:
            return None
            
        try:
            # Use compose to get position information
            # This is safe because we're only using it for position tracking
            root = compose(self.yaml_string)
            if root is None:
                return None

            # Find the ScalarNode that is the value of the key `code`
            def find_code_node(node):
                if isinstance(node, yaml.MappingNode):
                    for k, v in node.value:
                        if isinstance(k, yaml.ScalarNode) and k.value == "code":
                            return v
                        hit = find_code_node(v)
                        if hit:
                            return hit
                elif isinstance(node, yaml.SequenceNode):
                    for child in node.value:
                        hit = find_code_node(child)
                        if hit:
                            return hit
                return None

            node = find_code_node(root)
            if node is None:
                return None

            # Calculate byte offsets for the content
            txt = self.yaml_string
            
            # Start position - first content character
            p_start = node.start_mark.pointer
            if node.style in ("|", ">"):  # block scalar
                newline_pos = txt.find("\n", p_start)
                if newline_pos != -1:
                    p_start = newline_pos + 1
                    # Skip indentation
                    while p_start < len(txt) and txt[p_start] in " \t":
                        p_start += 1
            elif node.style in ("'", '"'):  # quoted inline
                p_start += 1  # skip opening quote

            # End position - last content character
            if node.style in ("|", ">"):  # block scalar
                p_end = node.end_mark.pointer - 1
            elif node.style in ("'", '"'):  # quoted inline
                p_end = node.end_mark.pointer - 2
            else:  # plain inline
                p_end = node.end_mark.pointer - 1

            # Convert byte offsets to line/column positions
            def byte_offset_to_position(ptr: int) -> types.Position:
                if ptr < 0:
                    ptr = 0
                elif ptr > len(txt):
                    ptr = len(txt)
                    
                line = txt.count("\n", 0, ptr)
                last_newline = txt.rfind("\n", 0, ptr)
                column = ptr - (last_newline + 1) if last_newline != -1 else ptr
                return types.Position(line=line, character=column)

            start_pos = byte_offset_to_position(p_start)
            end_pos = byte_offset_to_position(p_end)

            return (start_pos, end_pos)
            
        except Exception as e:
            logger.warning(f"Error extracting code span from {self.document_uri}: {e}")
            return None 