"""
MXCP Plugins Module

This module provides the base Plugin class and utilities for extending MXCP's functionality
with custom data processing capabilities.
"""

from mxcp.plugins.base import MXCPBasePlugin, udf, on_shutdown

__all__ = ['MXCPBasePlugin', 'udf', 'on_shutdown'] 
