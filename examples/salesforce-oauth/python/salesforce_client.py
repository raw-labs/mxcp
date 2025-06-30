"""
Salesforce MCP tools using simple_salesforce with MXCP OAuth authentication.
"""
from typing import Dict, Any
from mxcp.auth.context import get_user_context
from simple_salesforce import Salesforce


def _get_salesforce_client():
    """
    Create and return an authenticated Salesforce client using OAuth tokens from user_context.
    
    Uses the MXCP authentication system to get OAuth tokens for the authenticated user.
    The tokens are automatically managed by MXCP's Salesforce OAuth provider.
    """
    try:
        # Get the authenticated user's context
        context = get_user_context()
        
        if not context:
            raise ValueError("No user context available. User must be authenticated.")
        
        # Extract Salesforce OAuth tokens from user context
        access_token = context.external_token
        
        # Extract instance URL from user context (this is user/org-specific)
        instance_url = None
        if context.raw_profile and 'urls' in context.raw_profile:
            urls = context.raw_profile['urls']
            # Try custom_domain first (this is the full instance URL)
            instance_url = urls.get('custom_domain')
            if not instance_url:
                # Fallback: extract base URL from any service endpoint
                for url_key in ['rest', 'enterprise', 'partner']:
                    if url_key in urls:
                        service_url = urls[url_key]
                        instance_url = service_url.split('/services/')[0]
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
        sf = Salesforce(
            session_id=access_token,
            instance_url=instance_url
        )
        
        return sf
        
    except Exception as e:
        raise ValueError(f"Failed to authenticate with Salesforce: {str(e)}")


def list_sobjects(filter: str | None = None) -> list[str]:
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
        
        # Extract just the object names
        object_names = [obj['name'] for obj in describe_result['sobjects']]
        
        # Apply fuzzy filter if provided
        if filter is not None and filter.strip():
            filter_lower = filter.lower()
            object_names = [
                name for name in object_names 
                if filter_lower in name.lower()
            ]
        
        # Sort alphabetically for consistent output
        object_names.sort()
        
        return object_names
        
    except Exception as e:
        # Return error in a format that can be handled by the caller
        raise Exception(f"Error listing Salesforce objects: {str(e)}")


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
    
    # Process fields into the required format
    fields_info = {}
    for field in describe_result['fields']:
        field_name = field['name']
        field_info = {
            'type': field['type'],
            'label': field['label']
        }
        
        # Add referenceTo information for reference fields
        if field['type'] == 'reference' and field.get('referenceTo'):
            field_info['referenceTo'] = field['referenceTo']
        
        fields_info[field_name] = field_info
    
    return fields_info


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
    
    return record


def soql(query: str) -> list[Dict[str, Any]]:
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
    
    # Remove 'attributes' field from each record for cleaner output
    records = []
    for record in result['records']:
        clean_record = {k: v for k, v in record.items() if k != 'attributes'}
        records.append(clean_record)
    
    return records


def search(search_term: str) -> list[Dict[str, Any]]:
    """
    Search for records across all searchable Salesforce objects using a simple search term.
    Uses Salesforce's native search to automatically find matches across all objects.
    
    Args:
        search_term: The term to search for across Salesforce objects
    
    Returns:
        list: Array of matching records from various Salesforce objects
    """
    sf = _get_salesforce_client()
    
    # Use simple SOSL syntax - Salesforce searches all searchable objects automatically
    sosl_query = f"FIND {{{search_term}}}"
    
    # Execute the SOSL search
    search_results = sf.search(sosl_query)
    
    # Flatten results from all objects into a single array
    all_records = []
    for record in search_results['searchRecords']:
        # Remove 'attributes' field and add object type for context
        clean_record = {k: v for k, v in record.items() if k != 'attributes'}
        clean_record['_ObjectType'] = record['attributes']['type']
        all_records.append(clean_record)
    
    return all_records


def sosl(query: str) -> list[Dict[str, Any]]:
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
    
    # Flatten results from all objects into a single array
    all_records = []
    for record in search_results['searchRecords']:
        # Remove 'attributes' field and add object type for context
        clean_record = {k: v for k, v in record.items() if k != 'attributes'}
        clean_record['_ObjectType'] = record['attributes']['type']
        all_records.append(clean_record)
    
    return all_records


def whoami() -> Dict[str, Any]:
    """
    Get basic information about the currently authenticated Salesforce user from the user context.
    
    Returns basic user information from the MXCP authentication context without making API calls.
    
    Returns:
        dict: Dictionary containing basic current user information from authentication context
    """
    context = get_user_context()
    
    if not context:
        raise ValueError("No user context available. User must be authenticated.")
    
    # Extract instance URL from context
    instance_url = None
    if context.raw_profile and 'urls' in context.raw_profile:
        urls = context.raw_profile['urls']
        instance_url = urls.get('custom_domain')
        if not instance_url:
            # Fallback: extract base URL from any service endpoint
            for url_key in ['rest', 'enterprise', 'partner']:
                if url_key in urls:
                    service_url = urls[url_key]
                    instance_url = service_url.split('/services/')[0]
                    break
    
    # Build the response object with available context information
    user_info = {
        'instanceUrl': instance_url,
        'hasAccessToken': bool(context.external_token),
        'rawProfile': context.raw_profile
    }
    
    return user_info
