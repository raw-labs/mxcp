"""
Extension loader for DuckDB.

This module handles DuckDB extension loading.
"""

import logging

import duckdb

from .types import ExtensionDefinition


def load_extensions(
    con: duckdb.DuckDBPyConnection, extensions: list[ExtensionDefinition] | None = None
) -> None:
    """Load DuckDB extensions based on configuration.

    Args:
        con: DuckDB connection
        extensions: List of extensions to load. Can be strings for core extensions
                   or dicts with name/repo for community/nightly extensions.
    """
    if not extensions:
        return

    for ext in extensions:
        # All extensions are now ExtensionDefinition objects
        if not ext.name:
            continue  # Skip extensions without a name
        if ext.repo:
            _load_extension(con, ext.name, ext.repo)
        else:
            _load_extension(con, ext.name)


def _load_extension(con: duckdb.DuckDBPyConnection, name: str, repo: str | None = None) -> None:
    """Load a single DuckDB extension.

    Args:
        con: DuckDB connection
        name: Extension name
        repo: Optional repository name (e.g. community, core_nightly)
    """
    try:
        if repo:
            con.sql(f"INSTALL {name} FROM {repo}; LOAD {name};")
            logging.info(f"DuckDB extension '{name}' from '{repo}' loaded.")
        else:
            con.sql(f"INSTALL {name}; LOAD {name};")
            logging.info(f"DuckDB extension '{name}' loaded.")
    except Exception as e:
        logging.error(f"Failed to load DuckDB extension '{name}': {e}")
        raise
