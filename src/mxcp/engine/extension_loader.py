import logging
from typing import List, Union
from mxcp.config.types import SiteExtensionDefinition

def load_extensions(con, extensions: List[Union[str, SiteExtensionDefinition]] = None):
    """Load DuckDB extensions based on configuration.
    
    Args:
        con: DuckDB connection
        extensions: List of extensions to load. Can be strings for core extensions
                   or dicts with name/repo for community/nightly extensions.
    """
    if not extensions:
        return

    for ext in extensions:
        if isinstance(ext, str):
            # Core extension
            _load_extension(con, ext)
        else:
            # Community/nightly extension
            name = ext["name"]
            repo = ext.get("repo")
            if repo:
                _load_extension(con, name, repo)
            else:
                _load_extension(con, name)

def _load_extension(con, name: str, repo: str = None):
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
        logging.warning(f"Failed to load DuckDB extension '{name}': {e}")