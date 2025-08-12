"""
Jira Plugin Implementation

This module provides UDFs for querying Atlassian Jira using JQL.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from atlassian import Jira

from mxcp.plugins import MXCPBasePlugin, udf

logger = logging.getLogger(__name__)


class MXCPPlugin(MXCPBasePlugin):
    """Jira plugin that provides JQL query functionality."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Jira plugin.

        Args:
            config: Plugin configuration containing Jira API credentials
                Required keys:
                - url: The base URL of your Jira instance
                - username: Your Jira username/email
                - password: Your Jira API token/password
        """
        super().__init__(config)
        self.url = config.get("url", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")

        if not all([self.url, self.username, self.password]):
            raise ValueError("Jira plugin requires url, username, and password in configuration")

        # Initialize Jira client
        self.jira = Jira(url=self.url, username=self.username, password=self.password, cloud=True)

    @udf
    def jql_query(self, query: str, start: Optional[int] = 0, limit: Optional[int] = None) -> str:
        """Execute a JQL query against Jira.

        Args:
            query: The JQL query string
            start: Starting index for pagination (default: 0)
            limit: Maximum number of results to return (default: None, meaning no limit)

        Returns:
            JSON string containing Jira issues matching the query
        """
        logger.info("Executing JQL query: %s with start=%s, limit=%s", query, start, limit)

        raw = self.jira.jql(
            jql=query,
            start=start,
            limit=limit,
            fields=(
                "key,summary,status,resolution,resolutiondate,"
                "assignee,reporter,issuetype,priority,"
                "created,updated,labels,fixVersions,parent"
            ),
        )

        def _name(obj: Optional[Dict[str, Any]]) -> Optional[str]:
            """Return obj['name'] if present, else None."""
            return obj.get("name") if obj else None

        def _key(obj: Optional[Dict[str, Any]]) -> Optional[str]:
            return obj.get("key") if obj else None

        cleaned: List[Dict[str, Any]] = []
        for issue in raw.get("issues", []):
            f = issue["fields"]

            cleaned.append(
                {
                    "key": issue["key"],
                    "summary": f.get("summary"),
                    "status": _name(f.get("status")),
                    "resolution": _name(f.get("resolution")),
                    "resolution_date": f.get("resolutiondate"),
                    "assignee": _name(f.get("assignee")),
                    "reporter": _name(f.get("reporter")),
                    "type": _name(f.get("issuetype")),
                    "priority": _name(f.get("priority")),
                    "created": f.get("created"),
                    "updated": f.get("updated"),
                    "labels": f.get("labels") or [],
                    "fix_versions": [_name(v) for v in f.get("fixVersions", [])],
                    "parent": _key(f.get("parent")),
                    "url": f"{self.url}/browse/{issue['key']}",  # web UI URL
                }
            )

        return json.dumps(cleaned)

    @udf
    def get_user(self, username: str) -> str:
        """Get details for a specific user by username.

        Args:
            username: The username to search for

        Returns:
            JSON string containing the user details
        """
        logger.info("Getting user details for username: %s", username)
        return json.dumps(self.jira.user_find_by_user_string(query=username))

    @udf
    def list_projects(self) -> str:
        """
        Return a concise list of Jira projects.
        """
        logger.info("Listing all projects")

        raw_projects: List[Dict[str, Any]] = self.jira.projects()

        def safe_name(obj: Optional[Dict[str, Any]]) -> Optional[str]:
            return obj.get("displayName") or obj.get("name") if obj else None

        concise: List[Dict[str, Any]] = []
        for p in raw_projects:
            concise.append(
                {
                    "key": p.get("key"),
                    "name": p.get("name"),
                    "type": p.get("projectTypeKey"),  # e.g. software, business
                    "lead": safe_name(p.get("lead")),
                    "url": f"{self.url}/projects/{p.get('key')}",  # web UI URL
                }
            )

        return json.dumps(concise)

    @udf
    def get_project(self, project_key: str) -> str:
        """Get details for a specific project by its key.

        Args:
            project_key: The project key (e.g., 'TEST' for project TEST)

        Returns:
            JSON string containing the project details
        """
        logger.info("Getting project details for key: %s", project_key)
        info = self.jira.project(project_key)
        # remove the self key if it exists
        if "self" in info:
            info.pop("self")
        # Add web UI URL
        info["url"] = f"{self.url}/projects/{project_key}"
        return json.dumps(info)
