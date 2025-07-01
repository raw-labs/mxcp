"""
Jira OAuth Plugin Implementation

This module provides UDFs for querying Atlassian Jira using JQL with OAuth 2.0 authentication.
"""

from typing import Dict, Any, List, Optional
import logging
import json
import requests
from atlassian import Jira
from mxcp.plugins import MXCPBasePlugin, udf
from mxcp.auth.context import get_user_context

logger = logging.getLogger(__name__)


class MXCPPlugin(MXCPBasePlugin):
    """Jira OAuth plugin that provides JQL query functionality using OAuth 2.0 Bearer tokens."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Jira OAuth plugin.

        Args:
            config: Plugin configuration containing optional settings
                Optional keys:
                - oauth_token: Fallback OAuth Bearer token (if not using user context)
        """
        super().__init__(config)
        self.fallback_oauth_token = config.get("oauth_token", "")

    def _get_oauth_token(self) -> str:
        """Get OAuth token from user context or fallback configuration.
        
        Returns:
            OAuth Bearer token
            
        Raises:
            ValueError: If no OAuth token is available
        """
        # First try to get token from user context (preferred)
        user_context = get_user_context()
        if user_context and user_context.external_token:
            logger.debug("Using OAuth token from user context")
            return user_context.external_token
        
        # Fall back to configured token
        if self.fallback_oauth_token:
            logger.debug("Using fallback OAuth token from configuration")
            return self.fallback_oauth_token
            
        raise ValueError("No OAuth token available from user context or configuration")

    def _get_cloud_id(self, oauth_token: str) -> str:
        """Get the cloud ID for the first accessible Jira instance using the OAuth token.
        
        Args:
            oauth_token: OAuth Bearer token
            
        Returns:
            Cloud ID for the first accessible Jira instance
            
        Raises:
            ValueError: If cloud ID cannot be retrieved
        """
        try:
            response = requests.get(
                "https://api.atlassian.com/oauth/token/accessible-resources",
                headers={
                    "Authorization": f"Bearer {oauth_token}",
                    "Accept": "application/json"
                }
            )
            response.raise_for_status()
            
            resources = response.json()
            logger.debug(f"Found {len(resources)} accessible resources")
            
            # Use the first accessible resource
            if resources:
                cloud_id = resources[0].get("id")
                instance_url = resources[0].get("url")
                logger.info(f"Using cloud ID: {cloud_id} for instance: {instance_url}")
                return cloud_id
                
            raise ValueError(f"No accessible resources found for OAuth token")
            
        except requests.RequestException as e:
            logger.error(f"Failed to get cloud ID: {e}")
            raise ValueError(f"Failed to retrieve cloud ID: {e}")

    def _create_jira_client(self) -> Jira:
        """Create a Jira client with OAuth authentication using the correct API gateway URL.
        
        Returns:
            Configured Jira client instance
        """
        oauth_token = self._get_oauth_token()
        
        # Get the cloud ID for the first accessible Jira instance
        cloud_id = self._get_cloud_id(oauth_token)
        
        # Construct the API gateway URL for OAuth requests
        api_gateway_url = f"https://api.atlassian.com/ex/jira/{cloud_id}"
        logger.info("API Gateway URL: %s", api_gateway_url)
        
        # Create a requests session with OAuth Bearer token
        session = requests.Session()
        session.headers['Authorization'] = f'Bearer {oauth_token}'
        
        # Create and return Jira client with the OAuth session and API gateway URL
        # Explicitly set cloud=True since we're using Jira Cloud with OAuth
        return Jira(url=api_gateway_url, session=session, cloud=True)

    @udf
    def jql_query(self, query: str, start: Optional[int] = 0, limit: Optional[int] = None) -> str:
        """Execute a JQL query against Jira using OAuth authentication.

        Args:
            query: The JQL query string
            start: Starting index for pagination (default: 0)
            limit: Maximum number of results to return (default: None, meaning no limit)

        Returns:
            JSON string containing Jira issues matching the query
        """
        logger.info("Executing JQL query with OAuth: %s with start=%s, limit=%s", query, start, limit)

        # Create Jira client with current user's OAuth token
        jira = self._create_jira_client()

        raw = jira.jql(
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
        """Get details for a specific user by username using OAuth.

        Args:
            username: The username to search for

        Returns:
            JSON string containing the user details
        """
        logger.info("Getting user details with OAuth for username: %s", username)
        
        # Create Jira client with current user's OAuth token
        jira = self._create_jira_client()
        
        return json.dumps(jira.user_find_by_user_string(query=username))

    @udf
    def list_projects(self) -> str:
        """List all accessible Jira projects using OAuth authentication.

        Returns:
            JSON string containing an array of accessible Jira projects
        """
        logger.info("Listing all projects with OAuth")

        # Create Jira client with current user's OAuth token
        jira = self._create_jira_client()

        raw_projects: List[Dict[str, Any]] = jira.projects()

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
        """Get details for a specific project by its key using OAuth.

        Args:
            project_key: The project key (e.g., 'TEST' for project TEST)

        Returns:
            JSON string containing the project details
        """
        logger.info("Getting project details with OAuth for key: %s", project_key)
        
        # Create Jira client with current user's OAuth token
        jira = self._create_jira_client()
        
        info = jira.project(project_key)
        # remove the self key if it exists
        if "self" in info:
            info.pop("self")
        # Add web UI URL
        info["url"] = f"{self.url}/projects/{project_key}"
        return json.dumps(info)