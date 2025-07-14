"""DuckDB executor plugin package."""

from .session import DuckDBSession, execute_query_to_dict

__all__ = ["DuckDBSession", "execute_query_to_dict"] 