"""Testing service for MXCP server.

This package provides endpoint testing functionality.
The main entry point is the service module.
"""

# Import main functions from service module
from .service import (
    run_all_tests,
    run_tests,
)

__all__ = [
    "run_tests",
    "run_all_tests",
]
