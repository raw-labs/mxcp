"""
Secret injection for DuckDB session in executor plugin.

This module handles secret injection into DuckDB sessions.
This is a cloned version of the secret injection for the executor plugin system.
"""

import logging
from typing import Any, Dict, List

import duckdb

from ._types import SecretDefinition

logger = logging.getLogger(__name__)


def inject_secrets(con: duckdb.DuckDBPyConnection, secrets: List[SecretDefinition]) -> None:
    """Inject secrets into DuckDB session"""
    logger.debug(f"Injecting {len(secrets)} secrets")
    logger.debug(f"Found secrets: {[s.name for s in secrets]}")

    # Create secrets in DuckDB
    for secret in secrets:
        # Build CREATE TEMPORARY SECRET statement
        params = []
        for key, value in secret.parameters.items():
            # Handle special case for nested dictionaries (e.g., HTTP headers)
            if isinstance(value, dict):
                # Convert dict to DuckDB MAP syntax
                map_items = [f"'{k}': '{v}'" for k, v in value.items()]
                params.append(f"{key} MAP {{{', '.join(map_items)}}}")
            else:
                params.append(f"{key} '{value}'")

        create_secret_sql = f"""
        CREATE TEMPORARY SECRET {secret.name} (
            TYPE {secret.type},
            {', '.join(params)}
        )
        """

        try:
            logger.debug(f"Creating secret with SQL: {create_secret_sql}")
            con.execute(create_secret_sql)
        except Exception as e:
            # Log the error but continue - this allows MXCP to support any secret type
            # while DuckDB only creates the ones it understands
            logger.debug(f"Could not create secret '{secret.name}' in DuckDB: {e}")
            logger.debug(
                "This secret will still be accessible via config.get_secret() in Python endpoints"
            )
