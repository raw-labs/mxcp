"""
MXCP Jira OAuth Plugin

This plugin provides UDFs for querying Atlassian Jira using OAuth authentication.
Unlike the API token version, this plugin uses OAuth tokens from authenticated users.
"""

from .plugin import MXCPPlugin

__all__ = ["MXCPPlugin"]
