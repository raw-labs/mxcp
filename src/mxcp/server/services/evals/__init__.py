"""Evaluation service for MXCP server.

This package provides LLM-based evaluation functionality for testing endpoints.
The main entry point is the service module.
"""

# Import main functions from service module
from .service import run_all_evals, run_eval_suite

__all__ = [
    "run_eval_suite",
    "run_all_evals",
]
