"""
Salesforce Plugin for MXCP

This plugin provides integration with Salesforce, allowing you to query and manipulate Salesforce data through SQL.
It uses simple_salesforce for authentication and API calls.

Example usage:
    >>> plugin = MXCPPlugin({
        "username": "user@example.com",
        "password": "password",
        "security_token": "token",
        "instance_url": "https://instance.salesforce.com",
        "client_id": "client_id"
    })
    >>> plugin.soql("SELECT Id, Name FROM Account")  # Returns list of accounts
"""

from typing import List, Dict, Any, Optional, TypedDict
import simple_salesforce
import json
from mxcp.plugins import MXCPBasePlugin, udf

class SalesforceRecord(TypedDict):
    """Type definition for a Salesforce record."""
    Id: str
    Name: str
    # Add other common fields as needed

class MXCPPlugin(MXCPBasePlugin):
    """Plugin that provides Salesforce integration functions.
    
    This plugin allows you to interact with Salesforce data through SQL queries,
    providing functions to execute SOQL queries, list objects, and retrieve
    object descriptions.
    
    Example:
        >>> plugin = MXCPPlugin({
            "username": "user@example.com",
            "password": "password",
            "security_token": "token",
            "instance_url": "https://instance.salesforce.com",
            "client_id": "client_id"
        })
        >>> plugin.soql("SELECT Id, Name FROM Account")  # Returns list of accounts
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the plugin with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - username: Salesforce username
                - password: Salesforce password
                - security_token: Salesforce security token
                - instance_url: Salesforce instance URL
                - client_id: Salesforce client ID (required for authentication)
        """
        super().__init__(config)
        self.sf = simple_salesforce.Salesforce(
            username=config['username'],
            password=config['password'],
            security_token=config['security_token'],
            instance_url=config['instance_url'],
            client_id=config['client_id']
        )

    @udf
    def soql(self, query: str) -> List[Dict[str, str]]:
        """Execute an SOQL query against Salesforce.
        
        Args:
            query: The SOQL query to execute
            
        Returns:
            List of records returned by the query, with 'attributes' field removed
            
        Example:
            >>> plugin.soql("SELECT Id, Name FROM Account")
        """
        result = self.sf.query(query)
        # remove 'attributes' field from each record
        return [{k: v for k, v in r.items() if k != 'attributes'} for r in result['records']]

    @udf
    def sosl(self, query: str) -> str:
        """Execute a SOSL query against Salesforce.
        
        Args:
            query: The SOSL query to execute
            
        Returns:
            JSON string containing the search results from searchRecords
            
        Example:
            >>> plugin.sosl("FIND {Acme} IN ALL FIELDS RETURNING Account(Name), Contact(FirstName,LastName)")
        """
        result = self.sf.search(query)
        return json.dumps(result['searchRecords'])

    @udf
    def search(self, search_term: str) -> str:
        """Search across all Salesforce objects using a simple search term.
        
        Args:
            search_term: The term to search for
            
        Returns:
            JSON string containing the search results
            
        Example:
            >>> plugin.search("Acme")  # Searches for "Acme" across all objects
        """
        # Build a SOSL query that searches across common objects
        sosl_query = f"FIND {{{search_term}}} IN ALL FIELDS RETURNING Account(Name, Phone, BillingCity), Contact(FirstName, LastName, Email), Lead(FirstName, LastName, Company), Opportunity(Name, Amount, StageName)"
        return self.sosl(sosl_query)

    @udf
    def list_sobjects(self) -> List[str]:
        """Get a list of all available Salesforce objects.
        
        Returns:
            List of object names from the org
            
        Example:
            >>> plugin.list_sobjects()  # Returns ['Account', 'Contact', ...]
        """
        return [obj['name'] for obj in self.sf.describe()['sobjects']]

    @udf
    def describe_sobject(self, type_name: str) -> str:
        """Get the description of a Salesforce object type.
        
        Args:
            type_name: The name of the Salesforce object type
            
        Returns:
            JSON string containing the object's field descriptions
            
        Example:
            >>> plugin.describe_sobject("Account")
        """
        result = self.sf.__getattr__(type_name).describe()
        return json.dumps(result)

    @udf
    def get_sobject(self, type_name: str, id: str) -> str:
        """Get a specific Salesforce object by its ID.
        
        Args:
            type_name: The name of the Salesforce object type
            id: The Salesforce ID of the object
            
        Returns:
            JSON string containing the object's field values
            
        Example:
            >>> plugin.get_sobject("Account", "001xx000003DIloAAG")
        """
        result = self.sf.__getattr__(type_name).get(id)
        return json.dumps(result) 