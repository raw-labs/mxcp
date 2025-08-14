"""
Salesforce MCP tools using simple_salesforce with MXCP OAuth authentication.
"""

import threading
from functools import wraps
from typing import Dict, Any, List, Optional
from mxcp.sdk.auth.context import get_user_context
from simple_salesforce import Salesforce  # type: ignore[attr-defined]
from simple_salesforce.exceptions import SalesforceExpiredSession
from mxcp.runtime import on_init, on_shutdown
import logging

# Thread-safe cache for Salesforce clients
_client_cache: Optional[Dict[str, Salesforce]] = None
_cache_lock: Optional[threading.Lock] = None


@on_init
def init_client_cache() -> None:
    """
    Initialize the Salesforce client cache.
    """
    global _client_cache, _cache_lock
    _client_cache = {}
    _cache_lock = threading.Lock()


@on_shutdown
def clear_client_cache() -> None:
    """
    Clear the Salesforce client cache.
    """
    global _client_cache, _cache_lock
    _client_cache = None
    _cache_lock = None


def _get_cache_key(context: Any) -> Optional[str]:
    """Generate a cache key based on user context."""
    if not context:
        return None

    # Use user ID and instance URL as cache key
    user_id = getattr(context, "user_id", None) or getattr(context, "id", None)

    # Extract instance URL
    instance_url = None
    if context.raw_profile and "urls" in context.raw_profile:
        urls = context.raw_profile["urls"]
        instance_url = urls.get("custom_domain")
        if not instance_url:
            for url_key in ["rest", "enterprise", "partner"]:
                if url_key in urls:
                    service_url = urls[url_key]
                    instance_url = service_url.split("/services/")[0]
                    break

    if user_id and instance_url:
        return f"{user_id}:{instance_url}"

    return None


def with_session_retry(func: Any) -> Any:
    """
    Decorator that automatically retries API calls with cache invalidation when sessions expire.

    This handles the race condition where a session might expire between cache validation
    and the actual API call.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except SalesforceExpiredSession:
            logging.error("Salesforce session expired")
            # Session expired during the call - invalidate cache and retry once
            context = get_user_context()
            cache_key = _get_cache_key(context)
            if cache_key and _cache_lock and _client_cache:
                with _cache_lock:
                    # Remove the expired client from cache
                    _client_cache.pop(cache_key, None)

            # Retry the function call - this will get a fresh client
            return func(*args, **kwargs)

    return wrapper


def _escape_sosl_search_term(search_term: str) -> str:
    """
    Escape special characters in SOSL search terms to prevent injection attacks.

    SOSL special characters that need escaping: & | ! { } [ ] ( ) ^ ~ * ? : " ' + -
    """
    # Escape backslashes first to avoid double-escaping
    escaped = search_term.replace("\\", "\\\\")

    # Escape SOSL special characters
    special_chars = [
        "&",
        "|",
        "!",
        "{",
        "}",
        "[",
        "]",
        "(",
        ")",
        "^",
        "~",
        "*",
        "?",
        ":",
        '"',
        "'",
        "+",
        "-",
    ]
    for char in special_chars:
        escaped = escaped.replace(char, f"\\{char}")

    return escaped


def _get_salesforce_client() -> Salesforce:
    """
    Create and return an authenticated Salesforce client using OAuth tokens from user_context.

    Uses caching to avoid recreating clients unnecessarily. Clients are cached per user
    and instance URL combination in a thread-safe manner.
    """
    try:
        # Get the authenticated user's context
        context = get_user_context()

        if not context:
            raise ValueError("No user context available. User must be authenticated.")

        # Generate cache key
        cache_key = _get_cache_key(context)

        # Try to get cached client first
        if cache_key and _cache_lock and _client_cache:
            with _cache_lock:
                if cache_key in _client_cache:
                    logging.info("Using cached Salesforce client")
                    # Return cached client - retry decorator will handle any session expiry
                    return _client_cache[cache_key]

        logging.info("No cached Salesforce client found, creating new one")
        # Extract Salesforce OAuth tokens from user context
        access_token = context.external_token

        # Extract instance URL from user context (this is user/org-specific)
        instance_url = None
        if context.raw_profile and "urls" in context.raw_profile:
            urls = context.raw_profile["urls"]
            # Try custom_domain first (this is the full instance URL)
            instance_url = urls.get("custom_domain")
            if not instance_url:
                # Fallback: extract base URL from any service endpoint
                for url_key in ["rest", "enterprise", "partner"]:
                    if url_key in urls:
                        service_url = urls[url_key]
                        instance_url = service_url.split("/services/")[0]
                        break

        if not access_token:
            raise ValueError(
                "No Salesforce access token found in user context. "
                "User must authenticate with Salesforce through MXCP."
            )

        if not instance_url:
            raise ValueError(
                "No Salesforce instance URL found in user context. "
                "Authentication may be incomplete or profile missing URL information."
            )

        # Initialize Salesforce client with OAuth token
        sf = Salesforce(session_id=access_token, instance_url=instance_url)

        # Cache the client if we have a valid cache key
        if cache_key and _cache_lock and _client_cache:
            with _cache_lock:
                _client_cache[cache_key] = sf

        return sf

    except Exception as e:
        raise ValueError(f"Failed to authenticate with Salesforce: {str(e)}")


@with_session_retry
def list_sobjects(filter: Optional[str] = None) -> List[str]:
    """
    List all available Salesforce objects (sObjects) in the org.

    Args:
        filter: Optional fuzzy filter to match object names (case-insensitive substring search).
                Examples: "account", "__c" for custom objects, "contact", etc.

    Returns:
        list: List of Salesforce object names as strings
    """
    try:
        sf = _get_salesforce_client()

        # Get all sObjects metadata
        describe_result = sf.describe()

        if not describe_result or "sobjects" not in describe_result:
            raise ValueError("Invalid describe response from Salesforce API")

        # Extract just the object names
        sobjects = describe_result["sobjects"]
        object_names = []
        for obj in sobjects:
            if not isinstance(obj, dict) or "name" not in obj:
                raise ValueError(f"Invalid sobject format: {obj}")
            object_names.append(obj["name"])

        # Apply fuzzy filter if provided
        if filter is not None and filter.strip():
            filter_lower = filter.lower()
            object_names = [name for name in object_names if filter_lower in name.lower()]

        # Sort alphabetically for consistent output
        object_names.sort()

        return object_names

    except Exception as e:
        # Return error in a format that can be handled by the caller
        raise Exception(f"Error listing Salesforce objects: {str(e)}")


@with_session_retry
def describe_sobject(object_name: str) -> Dict[str, Any]:
    """
    Get detailed field information for a specific Salesforce object (sObject).

    Args:
        object_name: The API name of the Salesforce object to describe

    Returns:
        dict: Dictionary where each key is a field name and each value contains field metadata
    """
    sf = _get_salesforce_client()

    # Try to get the object - catch this specifically for "object doesn't exist"
    try:
        sobject = getattr(sf, object_name)
    except AttributeError:
        raise Exception(f"Salesforce object '{object_name}' does not exist")

    # Let API errors from describe() propagate naturally with their original messages
    describe_result = sobject.describe()

    if not describe_result or "fields" not in describe_result:
        raise ValueError(f"Invalid describe response for object '{object_name}'")

    # Process fields into the required format
    fields_info = {}
    for field in describe_result["fields"]:
        if not isinstance(field, dict):
            raise ValueError(f"Invalid field format in '{object_name}': {field}")

        required_fields = ["name", "type", "label"]
        for required_field in required_fields:
            if required_field not in field:
                raise ValueError(f"Field missing '{required_field}' in '{object_name}': {field}")
        field_name = field["name"]
        field_info = {"type": field["type"], "label": field["label"]}

        # Add referenceTo information for reference fields
        if field["type"] == "reference" and field.get("referenceTo"):
            field_info["referenceTo"] = field["referenceTo"]

        fields_info[field_name] = field_info

    return fields_info


@with_session_retry
def get_sobject(object_name: str, record_id: str) -> Dict[str, Any]:
    """
    Retrieve a specific Salesforce record by its object type and ID.

    Args:
        object_name: The API name of the Salesforce object type
        record_id: The unique Salesforce ID of the record to retrieve

    Returns:
        dict: Dictionary containing all fields and values for the specified record
    """
    sf = _get_salesforce_client()

    # Try to get the object - catch this specifically for "object doesn't exist"
    try:
        sobject = getattr(sf, object_name)
    except AttributeError:
        raise Exception(f"Salesforce object '{object_name}' does not exist")

    # Let API errors from get() propagate naturally with their original messages
    record = sobject.get(record_id)

    if not isinstance(record, dict):
        raise ValueError(f"Invalid record format returned for {object_name}:{record_id}")

    # Remove 'attributes' field for consistency with other functions
    clean_record: Dict[str, Any] = {k: v for k, v in record.items() if k != "attributes"}
    return clean_record


@with_session_retry
def soql(query: str) -> List[Dict[str, Any]]:
    """
    Execute an arbitrary SOQL (Salesforce Object Query Language) query.

    Args:
        query: The SOQL query to execute

    Returns:
        list: Array of records returned by the SOQL query
    """
    sf = _get_salesforce_client()

    # Execute the SOQL query
    result = sf.query(query)

    if not result or "records" not in result:
        raise ValueError("Invalid SOQL query response from Salesforce API")

    # Remove 'attributes' field from each record for cleaner output
    records = []
    for record in result["records"]:
        if not isinstance(record, dict):
            raise ValueError(f"Invalid record format in SOQL result: {record}")
        clean_record = {k: v for k, v in record.items() if k != "attributes"}
        records.append(clean_record)

    return records


@with_session_retry
def search(search_term: str) -> List[Dict[str, Any]]:
    """
    Search for records across all searchable Salesforce objects using a simple search term.
    Uses Salesforce's native search to automatically find matches across all objects.

    Args:
        search_term: The term to search for across Salesforce objects

    Returns:
        list: Array of matching records from various Salesforce objects
    """
    sf = _get_salesforce_client()

    # Escape the search term to prevent SOSL injection attacks
    escaped_search_term = _escape_sosl_search_term(search_term)

    # Use simple SOSL syntax - Salesforce searches all searchable objects automatically
    sosl_query = f"FIND {{{escaped_search_term}}}"

    # Execute the SOSL search
    search_results = sf.search(sosl_query)

    if not search_results or "searchRecords" not in search_results:
        raise ValueError("Invalid SOSL search response from Salesforce API")

    # Flatten results from all objects into a single array
    all_records = []
    for record in search_results["searchRecords"]:
        if not isinstance(record, dict):
            raise ValueError(f"Invalid record format in SOSL result: {record}")
        if "attributes" not in record or not isinstance(record["attributes"], dict):
            raise ValueError(f"Invalid record attributes in SOSL result: {record}")

        # Remove 'attributes' field and add object type for context
        clean_record = {k: v for k, v in record.items() if k != "attributes"}
        clean_record["_ObjectType"] = record["attributes"]["type"]
        all_records.append(clean_record)

    return all_records


@with_session_retry
def sosl(query: str) -> List[Dict[str, Any]]:
    """
    Execute an arbitrary SOSL (Salesforce Object Search Language) query.

    Args:
        query: The SOSL query to execute

    Returns:
        list: Array of records returned by the SOSL search query
    """
    sf = _get_salesforce_client()

    # Execute the SOSL search
    search_results = sf.search(query)

    if not search_results or "searchRecords" not in search_results:
        raise ValueError("Invalid SOSL query response from Salesforce API")

    # Flatten results from all objects into a single array
    all_records = []
    for record in search_results["searchRecords"]:
        if not isinstance(record, dict):
            raise ValueError(f"Invalid record format in SOSL result: {record}")
        if "attributes" not in record or not isinstance(record["attributes"], dict):
            raise ValueError(f"Invalid record attributes in SOSL result: {record}")

        # Remove 'attributes' field and add object type for context
        clean_record = {k: v for k, v in record.items() if k != "attributes"}
        clean_record["_ObjectType"] = record["attributes"]["type"]
        all_records.append(clean_record)

    return all_records


def whoami() -> Dict[str, Any]:
    """
    Get basic information about the currently authenticated Salesforce user from the user context.

    Returns essential user information from the MXCP authentication context without making API calls.

    Returns:
        dict: Dictionary containing essential current user information
    """
    context = get_user_context()

    if not context:
        raise ValueError("No user context available. User must be authenticated.")

    # Extract instance URL from context
    instance_url = None
    if context.raw_profile and "urls" in context.raw_profile:
        urls = context.raw_profile["urls"]
        instance_url = urls.get("custom_domain")
        if not instance_url:
            # Fallback: extract base URL from any service endpoint
            for url_key in ["rest", "enterprise", "partner"]:
                if url_key in urls:
                    service_url = urls[url_key]
                    instance_url = service_url.split("/services/")[0]
                    break

    # Extract essential user information from raw profile
    raw_profile = context.raw_profile or {}

    user_info = {
        "user_id": raw_profile.get("user_id"),
        "email": raw_profile.get("email"),
        "name": raw_profile.get("name"),
        "preferred_username": raw_profile.get("preferred_username"),
        "organization_id": raw_profile.get("organization_id"),
        "instanceUrl": instance_url,
    }

    return user_info
