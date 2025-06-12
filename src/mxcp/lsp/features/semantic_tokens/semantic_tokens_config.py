"""Configuration for semantic tokens functionality."""

from typing import Dict, List


class SemanticTokensConfig:
    """Configuration class for semantic token types and mappings."""
    
    # LSP standard token types
    TOKEN_TYPES: List[str] = [
        "keyword",
        "string", 
        "number",
        "function",
        "comment",
        "operator",
        "type",
        "variable",
    ]
    
    # Token type indices mapping
    TOKEN_TYPE_INDICES: Dict[str, int] = {
        "keyword": 0,
        "string_const": 1,
        "operator": 5,
        "identifier": 7,
        "numeric_const": 2,
        "function": 3,
    }
    
    # SQL data types that should be highlighted as types
    SQL_DATA_TYPES: List[str] = [
        "boolean", "tinyint", "smallint", "integer", "bigint",
        "utinyint", "usmallint", "uinteger", "ubigint",
        "float", "double", "timestamp", "date", "time", "interval",
        "hugeint", "uhugeint", "varchar", "blob", "decimal",
        "timestamp_s", "timestamp_ms", "timestamp_ns",
        "enum", "list", "struct", "map", "array", "uuid", "union",
        "bit", "time_tz", "timestamp_tz",
    ]
    
    # Default token type indices
    TYPE_TOKEN_INDEX = 6
    DEFAULT_TOKEN_INDEX = 1 