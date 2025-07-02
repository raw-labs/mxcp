"""
JIRA Python Endpoints

This module provides direct Python MCP endpoints for querying Atlassian JIRA.
This is a simpler alternative to the plugin-based approach.
"""

from typing import Dict, Any, List, Optional
import logging
from atlassian import Jira
from mxcp.runtime import config, db

logger = logging.getLogger(__name__)


def _get_jira_client() -> Jira:
    """Get configured JIRA client from secrets."""
    jira_config = config.get_secret("jira")
    if not jira_config:
        raise ValueError("JIRA configuration not found. Please configure JIRA secrets in your user config.")
    
    required_keys = ["url", "username", "password"]
    missing_keys = [key for key in required_keys if not jira_config.get(key)]
    if missing_keys:
        raise ValueError(f"Missing JIRA configuration keys: {', '.join(missing_keys)}")
    
    return Jira(
        url=jira_config["url"],
        username=jira_config["username"],
        password=jira_config["password"],
        cloud=True
    )


def jql_query(query: str, start: Optional[int] = 0, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Execute a JQL query against Jira.

    Args:
        query: The JQL query string
        start: Starting index for pagination (default: 0)
        limit: Maximum number of results to return (default: None, meaning no limit)

    Returns:
        List of Jira issues matching the query
    """
    logger.info("Executing JQL query: %s with start=%s, limit=%s", query, start, limit)

    jira = _get_jira_client()
    
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
    jira_url = jira.url
    
    for issue in raw.get("issues", []):
        f = issue["fields"]

        cleaned.append({
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
            "url": f"{jira_url}/browse/{issue['key']}",  # web UI URL
        })

    return cleaned


def get_issue(issue_key: str) -> Dict[str, Any]:
    """Get detailed information for a specific JIRA issue by its key.

    Args:
        issue_key: The issue key (e.g., 'RD-123', 'TEST-456')

    Returns:
        Dictionary containing comprehensive issue information
        
    Raises:
        ValueError: If issue is not found or access is denied
    """
    logger.info("Getting issue details for key: %s", issue_key)
    jira = _get_jira_client()
    
    # Get issue by key - this method handles the REST API call
    issue = jira.issue(issue_key)
    
    # Extract and clean up the most important fields for easier consumption
    fields = issue.get('fields', {})
    jira_url = jira.url
    
    def _safe_get(obj, key, default=None):
        """Safely get a value from a dict/object that might be None."""
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)
    
    cleaned_issue = {
        "key": issue.get('key'),
        "id": issue.get('id'),
        "summary": fields.get('summary'),
        "description": fields.get('description'),
        "status": _safe_get(fields.get('status'), 'name'),
        "assignee": _safe_get(fields.get('assignee'), 'displayName'),
        "assignee_account_id": _safe_get(fields.get('assignee'), 'accountId'),
        "reporter": _safe_get(fields.get('reporter'), 'displayName'),
        "reporter_account_id": _safe_get(fields.get('reporter'), 'accountId'),
        "issue_type": _safe_get(fields.get('issuetype'), 'name'),
        "priority": _safe_get(fields.get('priority'), 'name'),
        "resolution": _safe_get(fields.get('resolution'), 'name'),
        "resolution_date": fields.get('resolutiondate'),
        "created": fields.get('created'),
        "updated": fields.get('updated'),
        "due_date": fields.get('duedate'),
        "labels": fields.get('labels', []) or [],
        "components": [comp.get('name') for comp in fields.get('components', []) if comp and comp.get('name')] if fields.get('components') else [],
        "fix_versions": [ver.get('name') for ver in fields.get('fixVersions', []) if ver and ver.get('name')] if fields.get('fixVersions') else [],
        "project": {
            "key": _safe_get(fields.get('project'), 'key'),
            "name": _safe_get(fields.get('project'), 'name')
        },
        "parent": _safe_get(fields.get('parent'), 'key'),
        "url": f"{jira_url}/browse/{issue.get('key')}"
    }
    
    return cleaned_issue


def get_user(account_id: str) -> Dict[str, Any]:
    """Get a specific user by their unique account ID.

    Args:
        account_id: The unique Atlassian account ID for the user.
                   Example: "557058:ab168c94-8485-405c-88e6-6458375eb30b"

    Returns:
        Dictionary containing filtered user details
        
    Raises:
        ValueError: If user is not found or account ID is invalid
    """
    logger.info("Getting user details for account ID: %s", account_id)
    jira = _get_jira_client()
    
    # Get user by account ID - pass as account_id parameter for Jira Cloud
    user = jira.user(account_id=account_id)
    
    # Return only the requested fields
    return {
        "accountId": user.get("accountId"),
        "displayName": user.get("displayName"),
        "emailAddress": user.get("emailAddress"),
        "active": user.get("active"),
        "timeZone": user.get("timeZone")
    }


def search_user(query: str) -> List[Dict[str, Any]]:
    """Search for users by query string (username, email, or display name).

    Args:
        query: Search term - can be username, email, display name, or partial matches.
               Examples: "ben@raw-labs.com", "Benjamin Gaidioz", "ben", "benjamin", "gaidioz"

    Returns:
        List of matching users with filtered fields. Empty list if no matches found.
    """
    logger.info("Searching for users with query: %s", query)
    jira = _get_jira_client()
    
    # user_find_by_user_string returns a list of users matching the query
    users = jira.user_find_by_user_string(query=query)
    
    if not users:
        return []
    
    # Filter users to only include relevant fields
    filtered_users = []
    for user in users:
        filtered_users.append({
            "accountId": user.get("accountId"),
            "displayName": user.get("displayName"),
            "emailAddress": user.get("emailAddress"),
            "active": user.get("active"),
            "timeZone": user.get("timeZone")
        })
    
    return filtered_users


def list_projects() -> List[Dict[str, Any]]:
    """Return a concise list of Jira projects.
    
    Returns:
        List of dictionaries containing project information
    """
    logger.info("Listing all projects")

    jira = _get_jira_client()
    raw_projects: List[Dict[str, Any]] = jira.projects(expand="lead")

    def safe_name(obj: Optional[Dict[str, Any]]) -> Optional[str]:
        return obj.get("displayName") or obj.get("name") if obj else None

    concise: List[Dict[str, Any]] = []
    jira_url = jira.url
    
    for p in raw_projects:
        concise.append({
            "key": p.get("key"),
            "name": p.get("name"),
            "type": p.get("projectTypeKey"),  # e.g. software, business
            "lead": safe_name(p.get("lead")),
            "url": f"{jira_url}/projects/{p.get('key')}",  # web UI URL
        })

    return concise


def get_project(project_key: str) -> Dict[str, Any]:
    """Get details for a specific project by its key.

    Args:
        project_key: The project key (e.g., 'TEST' for project TEST)

    Returns:
        Dictionary containing the project details
        
    Raises:
        ValueError: If project is not found or access is denied
    """
    logger.info("Getting project details for key: %s", project_key)
    jira = _get_jira_client()
    
    try:
        info = jira.project(project_key)
    except Exception as e:
        # Handle various possible errors from the JIRA API
        error_msg = str(e).lower()
        if "404" in error_msg or "not found" in error_msg:
            raise ValueError(f"Project '{project_key}' not found in JIRA")
        elif "403" in error_msg or "forbidden" in error_msg:
            raise ValueError(f"Access denied to project '{project_key}' in JIRA")
        else:
            # Re-raise other errors with context
            raise ValueError(f"Error retrieving project '{project_key}': {e}") from e
    
    # Filter to essential fields only to avoid response size issues
    cleaned_info = {
        "key": info.get("key"),
        "name": info.get("name"),
        "description": info.get("description"),
        "projectTypeKey": info.get("projectTypeKey"),
        "simplified": info.get("simplified"),
        "style": info.get("style"),
        "isPrivate": info.get("isPrivate"),
        "archived": info.get("archived")
    }
    
    # Add lead info if present
    if "lead" in info and info["lead"]:
        cleaned_info["lead"] = {
            "displayName": info["lead"].get("displayName"),
            "emailAddress": info["lead"].get("emailAddress"),
            "accountId": info["lead"].get("accountId"),
            "active": info["lead"].get("active")
        }
    
    cleaned_info["url"] = f"{jira.url}/projects/{project_key}"
    
    return cleaned_info


def get_project_roles(project_key: str) -> List[Dict[str, Any]]:
    """Get all roles available in a project.

    Args:
        project_key: The project key (e.g., 'TEST' for project TEST)

    Returns:
        List of roles available in the project
        
    Raises:
        ValueError: If project is not found or access is denied
    """
    logger.info("Getting project roles for key: %s", project_key)
    jira = _get_jira_client()
    
    try:
        # Get all project roles using the correct method
        project_roles = jira.get_project_roles(project_key)
        
        result = []
        for role_name, role_url in project_roles.items():
            # Extract role ID from URL (e.g., "https://domain.atlassian.net/rest/api/3/project/10000/role/10002")
            role_id = role_url.split("/")[-1]
            
            result.append({
                "name": role_name,
                "id": role_id
            })
        
        return result
        
    except Exception as e:
        # Handle various possible errors from the JIRA API
        error_msg = str(e).lower()
        if "404" in error_msg or "not found" in error_msg:
            raise ValueError(f"Project '{project_key}' not found in JIRA")
        elif "403" in error_msg or "forbidden" in error_msg:
            raise ValueError(f"Access denied to project '{project_key}' in JIRA")
        else:
            # Re-raise other errors with context
            raise ValueError(f"Error retrieving project roles for '{project_key}': {e}") from e


def get_project_role_users(project_key: str, role_name: str) -> Dict[str, Any]:
    """Get users and groups for a specific role in a project.

    Args:
        project_key: The project key (e.g., 'TEST' for project TEST)
        role_name: The name of the role to get users for

    Returns:
        Dictionary containing users and groups for the specified role
        
    Raises:
        ValueError: If project or role is not found, or access is denied
    """
    logger.info("Getting users for role '%s' in project '%s'", role_name, project_key)
    jira = _get_jira_client()
    
    try:
        # First get all project roles to find the role ID
        project_roles = jira.get_project_roles(project_key)
        
        if role_name not in project_roles:
            available_roles = list(project_roles.keys())
            raise ValueError(f"Role '{role_name}' not found in project '{project_key}'. Available roles: {available_roles}")
        
        # Extract role ID from URL
        role_url = project_roles[role_name]
        role_id = role_url.split("/")[-1]
        
        # Get role details including actors (users and groups)
        role_details = jira.get_project_actors_for_role_project(project_key, role_id)
        
        result = {
            "project_key": project_key,
            "role_name": role_name,
            "role_id": role_id,
            "users": [],
            "groups": []
        }
        
        # Process actors (role_details is a list of actors)
        if isinstance(role_details, list):
            for actor in role_details:
                if isinstance(actor, dict):
                    actor_type = actor.get("type", "")
                    if actor_type == "atlassian-user-role-actor":
                        # Individual user
                        user_info = {
                            "accountId": actor.get("actorUser", {}).get("accountId"),
                            "displayName": actor.get("displayName")
                        }
                        result["users"].append(user_info)
                    elif actor_type == "atlassian-group-role-actor":
                        # Group
                        group_info = {
                            "name": actor.get("displayName"),
                            "groupId": actor.get("actorGroup", {}).get("groupId")
                        }
                        result["groups"].append(group_info)
                    else:
                        # Handle other actor types or simple user entries
                        display_name = actor.get("displayName") or actor.get("name")
                        if display_name:
                            user_info = {
                                "accountId": actor.get("accountId"),
                                "displayName": display_name,
                            }
                            result["users"].append(user_info)
        
        return result
        
    except ValueError:
        # Re-raise ValueError as-is (these are our custom error messages)
        raise
    except Exception as e:
        # Handle various possible errors from the JIRA API
        error_msg = str(e).lower()
        if "404" in error_msg or "not found" in error_msg:
            raise ValueError(f"Project '{project_key}' not found in JIRA")
        elif "403" in error_msg or "forbidden" in error_msg:
            raise ValueError(f"Access denied to project '{project_key}' in JIRA")
        else:
            # Re-raise other errors with context
            raise ValueError(f"Error retrieving users for role '{role_name}' in project '{project_key}': {e}") from e


