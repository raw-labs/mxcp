"""
Salesforce Python Endpoints

This module provides direct Python MCP endpoints for querying Salesforce.
This is a simpler alternative to the plugin-based approach.
"""

from typing import Dict, Any, List, Optional
import logging
import json
import simple_salesforce
from mxcp.runtime import config, on_init, on_shutdown

logger = logging.getLogger(__name__)

# Global Salesforce client for reuse across all function calls
sf_client: Optional[simple_salesforce.Salesforce] = None


@on_init
def setup_salesforce_client():
    """Initialize Salesforce client when server starts."""
    global sf_client
    logger.info("Initializing Salesforce client...")
    
    sf_config = config.get_secret("salesforce")
    if not sf_config:
        raise ValueError("Salesforce configuration not found. Please configure Salesforce secrets in your user config.")
    
    required_keys = ["username", "password", "security_token", "instance_url", "client_id"]
    missing_keys = [key for key in required_keys if not sf_config.get(key)]
    if missing_keys:
        raise ValueError(f"Missing Salesforce configuration keys: {', '.join(missing_keys)}")
    
    sf_client = simple_salesforce.Salesforce(
        username=sf_config["username"],
        password=sf_config["password"],
        security_token=sf_config["security_token"],
        instance_url=sf_config["instance_url"],
        client_id=sf_config["client_id"]
    )
    
    logger.info("Salesforce client initialized successfully")


@on_shutdown
def cleanup_salesforce_client():
    """Clean up Salesforce client when server stops."""
    global sf_client
    if sf_client:
        # Salesforce client doesn't need explicit cleanup, but we'll clear the reference
        sf_client = None
        logger.info("Salesforce client cleaned up")


def _get_salesforce_client() -> simple_salesforce.Salesforce:
    """Get the global Salesforce client."""
    if sf_client is None:
        raise RuntimeError("Salesforce client not initialized. Make sure the server is started properly.")
    return sf_client


def soql(query: str) -> List[Dict[str, Any]]:
    """Execute an SOQL query against Salesforce.
    
    Args:
        query: The SOQL query to execute
        
    Returns:
        List of records returned by the query, with 'attributes' field removed
        
    Example:
        >>> soql("SELECT Id, Name FROM Account")
    """
    logger.info("Executing SOQL query: %s", query)
    
    sf = _get_salesforce_client()
    result = sf.query(query)
    
    # Remove 'attributes' field from each record for cleaner output
    return [
        {k: v for k, v in record.items() if k != 'attributes'} 
        for record in result['records']
    ]


def sosl(query: str) -> List[Dict[str, Any]]:
    """Execute a SOSL query against Salesforce.
    
    Args:
        query: The SOSL query to execute
        
    Returns:
        List of search results from searchRecords
        
    Example:
        >>> sosl("FIND {Acme} IN ALL FIELDS RETURNING Account(Name), Contact(FirstName,LastName)")
    """
    logger.info("Executing SOSL query: %s", query)
    
    sf = _get_salesforce_client()
    result = sf.search(query)
    
    # Return the searchRecords directly as a list
    return result.get('searchRecords', [])


def search(search_term: str) -> List[Dict[str, Any]]:
    """Search across all Salesforce objects using a simple search term.
    
    Args:
        search_term: The term to search for
        
    Returns:
        List of search results
        
    Example:
        >>> search("Acme")  # Searches for "Acme" across all objects
    """
    logger.info("Searching for term: %s", search_term)
    
    # Build a SOSL query that searches across common objects
    sosl_query = f"FIND {{{search_term}}} IN ALL FIELDS RETURNING Account(Name, Phone, BillingCity), Contact(FirstName, LastName, Email), Lead(FirstName, LastName, Company), Opportunity(Name, Amount, StageName)"
    
    return sosl(sosl_query)


def list_sobjects(filter: Optional[str] = None) -> List[str]:
    """List all available Salesforce objects (sObjects) in the org.
    
    Args:
        filter: Optional fuzzy filter to match object names (case-insensitive substring search).
                Examples: "account", "__c" for custom objects, "contact", etc.
    
    Returns:
        list: List of Salesforce object names as strings
    """
    sf = _get_salesforce_client()
        
    describe_result = sf.describe()
        
    object_names = [obj['name'] for obj in describe_result['sobjects']]
        
    if filter is not None and filter.strip():
        filter_lower = filter.lower()
        object_names = [
            name for name in object_names 
            if filter_lower in name.lower()
        ]
        
    object_names.sort()
        
    return object_names


def describe_sobject(sobject_name: str) -> Dict[str, Any]:
    """Get the description of a Salesforce object type.
    
    Args:
        sobject_name: The name of the Salesforce object type
        
    Returns:
        Dictionary containing the object's field descriptions
        
    Example:
        >>> describe_sobject("Account")
    """
    logger.info("Describing Salesforce object: %s", sobject_name)
    
    sf = _get_salesforce_client()
    
    # Try to get the object - catch this specifically for "object doesn't exist"
    try:
        sobject = getattr(sf, sobject_name)
    except AttributeError:
        raise Exception(f"Salesforce object '{sobject_name}' does not exist")
    
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

def get_sobject(sobject_name: str, record_id: str) -> Dict[str, Any]:
    """Get a specific Salesforce object by its ID.
    
    Args:
        sobject_name: The name of the Salesforce object type
        record_id: The Salesforce ID of the object
        
    Returns:
        Dictionary containing the object's field values
        
    Example:
        >>> get_sobject("Account", "001xx000003DIloAAG")
    """
    logger.info("Getting Salesforce object: %s with ID: %s", sobject_name, record_id)
    
    sf = _get_salesforce_client()
    
    # Try to get the object - catch this specifically for "object doesn't exist"
    try:
        sobject = getattr(sf, sobject_name)
    except AttributeError:
        raise Exception(f"Salesforce object '{sobject_name}' does not exist")
    
    result = sobject.get(record_id)
    
    # Remove 'attributes' field for consistency with other functions
    if isinstance(result, dict) and 'attributes' in result:
        result = {k: v for k, v in result.items() if k != 'attributes'}
    
    return result 