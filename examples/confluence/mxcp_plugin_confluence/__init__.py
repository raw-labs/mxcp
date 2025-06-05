"""
Confluence Plugin Implementation

This module provides UDFs for interacting with Atlassian Confluence.
"""

from typing import Dict, Any, List, Optional
import logging
import json
from atlassian import Confluence
from mxcp.plugins import MXCPBasePlugin, udf

logger = logging.getLogger(__name__)


class MXCPPlugin(MXCPBasePlugin):
    """Confluence plugin that provides content query functionality."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Confluence plugin.

        Args:
            config: Plugin configuration containing Confluence API credentials
                Required keys:
                - url: The base URL of your Confluence instance
                - username: Your Atlassian username/email
                - password: Your Atlassian API token
        """
        super().__init__(config)
        self.url = config.get("url", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")

        if not all([self.url, self.username, self.password]):
            raise ValueError(
                "Confluence plugin requires url, username, and password in configuration"
            )

        # Initialize Confluence client
        self.confluence = Confluence(
            url=self.url, username=self.username, password=self.password, cloud=True
        )

    @udf
    def cql_query(
        self, query: str, space_key: Optional[str] = None, max_results: Optional[int] = 50
    ) -> str:
        """Execute a CQL query against Confluence.

        Args:
            query: The CQL query string
            space_key: Optional space key to limit the search
            max_results: Maximum number of results to return (default: 50)

        Returns:
            JSON string containing matching pages
        """
        logger.info(
            "Executing CQL query: %s in space=%s with max_results=%s",
            query, space_key, max_results
        )

        # Build the CQL query
        cql = query
        if space_key:
            cql = f'space = "{space_key}" AND {cql}'

        # Execute the CQL query
        results = self.confluence.cql(cql=cql, limit=max_results, expand="version,metadata.labels")

        # Transform the response to match our schema
        transformed_results = [
            {
                "id": page["content"]["id"],
                "title": page["content"]["title"],
                "space_key": page["content"]["space"]["key"],
                "url": f"{self.url}/wiki/spaces/{page['content']['space']['key']}/pages/{page['content']['id']}",
                "version": {
                    "number": page["content"]["version"]["number"],
                    "when": page["content"]["version"]["when"],
                },
                "last_modified": page["content"]["version"]["when"],
                "author": page["content"]["version"]["by"]["email"],
                "labels": [
                    label["name"] for label in page["content"]["metadata"]["labels"]["results"]
                ],
            }
            for page in results["results"]
        ]

        return json.dumps(transformed_results)

    @udf
    def search_pages(self, query: str, limit: Optional[int] = 10) -> str:
        """Search pages by keyword.

        Args:
            query: Search string, e.g., 'onboarding guide'
            limit: Maximum number of results to return (default: 10)

        Returns:
            JSON string containing matching pages
        """
        logger.info("Searching pages with query: %s, limit: %s", query, limit)

        results = self.confluence.cql(cql=f'text ~ "{query}"', limit=limit, expand="version,space")

        return json.dumps(results)

    @udf
    def get_page(self, page_id: str) -> str:
        """Fetch page content (storage format or rendered HTML).

        Args:
            page_id: Confluence page ID

        Returns:
            JSON string containing page content
        """
        logger.info("Getting page content for ID: %s", page_id)

        page = self.confluence.get_page_by_id(page_id=page_id, expand="body.storage,body.view")

        return json.dumps(page)

    @udf
    def get_children(self, page_id: str) -> str:
        """List direct children of a page.

        Args:
            page_id: Confluence page ID

        Returns:
            JSON string containing child pages
        """
        logger.info("Getting children for page ID: %s", page_id)

        children = self.confluence.get_child_pages(page_id=page_id, expand="version,space")

        return json.dumps(children)

    @udf
    def list_spaces(self) -> str:
        """Return all accessible spaces (by key and name).

        Returns:
            JSON string containing list of spaces
        """
        logger.info("Listing all spaces")

        spaces = self.confluence.get_all_spaces(expand="description,metadata.labels")

        return json.dumps(spaces)

    @udf
    def describe_page(self, page_id: str) -> str:
        """Show metadata about a page (title, author, updated, labels, etc).

        Args:
            page_id: Confluence page ID

        Returns:
            JSON string containing page metadata
        """
        logger.info("Getting metadata for page ID: %s", page_id)

        page = self.confluence.get_page_by_id(
            page_id=page_id, expand="version,space,metadata.labels"
        )

        return json.dumps(page)
