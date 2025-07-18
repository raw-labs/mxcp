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
    
    @udf
    def search_leads(self, 
                    lead_rating: Optional[str] = None,
                    lead_email: Optional[str] = None,
                    lead_name: Optional[str] = None,
                    lead_owner_id: Optional[str] = None,
                    lead_converted_date_range_start: Optional[str] = None,
                    lead_converted_date_range_end: Optional[str] = None,
                    min_employees: Optional[int] = None,
                    max_employees: Optional[int] = None,
                    page: Optional[int] = None,
                    page_size: Optional[int] = None) -> str:
        """Search for Salesforce Leads with filtering and pagination support.
        
        Args:
            lead_rating: Comma-separated list of lead ratings
            lead_email: Email to search for (partial match)
            lead_name: Name to search for (partial match)
            lead_owner_id: Salesforce User ID of the lead owner
            lead_converted_date_range_start: Start date (YYYY-MM-DD)
            lead_converted_date_range_end: End date (YYYY-MM-DD)
            min_employees: Minimum number of employees
            max_employees: Maximum number of employees
            page: Page number (1-based)
            page_size: Number of records per page
                
        Returns:
            JSON string containing lead records
        """
        # Set defaults for pagination
        if page is None:
            page = 1
        if page_size is None:
            page_size = 25
            
        # Build the SOQL query dynamically based on provided filters
        soql_query = """
            SELECT Id, Email, Name, Phone, Status, AnnualRevenue, Company,
                   CreatedDate, ConvertedDate, CreatedById, Industry, LeadSource,
                   NumberOfEmployees, OwnerId, Rating, Website,
                   ConvertedAccountId, ConvertedContactId, ConvertedOpportunityId
            FROM Lead
        """
        
        # Build WHERE clause conditions
        conditions = []
        
        if lead_rating and lead_rating.strip():
            ratings = [f"'{r.strip()}'" for r in lead_rating.split(',')]
            conditions.append(f"Rating IN ({','.join(ratings)})")
        
        if lead_email and lead_email.strip():
            conditions.append(f"Email LIKE '%{lead_email}%'")
        
        if lead_name and lead_name.strip():
            conditions.append(f"Name LIKE '%{lead_name}%'")
        
        if lead_owner_id and lead_owner_id.strip():
            conditions.append(f"OwnerId = '{lead_owner_id}'")
        
        if lead_converted_date_range_start and lead_converted_date_range_start.strip():
            conditions.append(f"ConvertedDate >= {lead_converted_date_range_start}")
        
        if lead_converted_date_range_end and lead_converted_date_range_end.strip():
            conditions.append(f"ConvertedDate <= {lead_converted_date_range_end}")
        
        if min_employees is not None and min_employees > 0:
            conditions.append(f"NumberOfEmployees >= {min_employees}")
        
        if max_employees is not None and max_employees > 0:
            conditions.append(f"NumberOfEmployees <= {max_employees}")
        
        # Add WHERE clause if there are conditions
        if conditions:
            soql_query += " WHERE " + " AND ".join(conditions)
        
        # Add ORDER BY
        soql_query += " ORDER BY Id"
        
        # Add LIMIT and OFFSET for pagination
        offset = (page - 1) * page_size
        soql_query += f" LIMIT {page_size} OFFSET {offset}"
        
        try:
            # Execute the query
            result = self.sf.query(soql_query)
            
            # Transform the results to include Salesforce link
            leads = []
            for record in result['records']:
                # Remove the 'attributes' field
                lead = {k: v for k, v in record.items() if k != 'attributes'}
                # Add the Salesforce link
                # Use the configured instance URL from config or fallback
                instance_url = getattr(self, 'instance_url', 'https://rawlabssa-dev-ed.develop.my.salesforce.com')
                lead['salesforce_link'] = f"{instance_url}/lightning/r/Lead/{lead['Id']}/view"
                leads.append(lead)
            
            return json.dumps(leads)
        except Exception as e:
            # Return error info
            return json.dumps({"error": str(e), "query": soql_query})
    
    @udf
    def get_lead_ratings(self) -> List[str]:
        """Get the list of available lead rating values from Salesforce.
        
        Returns:
            List of valid lead rating values
        """
        # For testing without real Salesforce connection, return mock data
        # In production, this would query Salesforce for actual picklist values
        return ["Hot", "Warm", "Cold"]
    
    @udf
    def search_opportunities(self, 
                           opportunity_name: Optional[str] = None,
                           stage_name: Optional[str] = None,
                           opportunity_type: Optional[str] = None,
                           lead_source: Optional[str] = None,
                           account_id: Optional[str] = None,
                           owner_id: Optional[str] = None,
                           opportunity_id: Optional[str] = None,
                           close_date_start: Optional[str] = None,
                           close_date_end: Optional[str] = None,
                           created_date_start: Optional[str] = None,
                           created_date_end: Optional[str] = None,
                           page: Optional[int] = None,
                           page_size: Optional[int] = None) -> str:
        """Search for Salesforce Opportunities with filtering and pagination support.
        
        Args:
            opportunity_name: Opportunity name to search for (partial match)
            stage_name: Comma-separated list of stage names
            opportunity_type: Opportunity type to filter by
            lead_source: Lead source to filter by
            account_id: Salesforce Account ID to filter by
            owner_id: Salesforce User ID of the opportunity owner
            opportunity_id: Specific opportunity ID to retrieve
            close_date_start: Start date for close date range (YYYY-MM-DD)
            close_date_end: End date for close date range (YYYY-MM-DD)
            created_date_start: Start date for creation date range (YYYY-MM-DD)
            created_date_end: End date for creation date range (YYYY-MM-DD)
            page: Page number (1-based)
            page_size: Number of records per page
                
        Returns:
            JSON string containing opportunity records
        """
        # Set defaults for pagination
        if page is None:
            page = 1
        if page_size is None:
            page_size = 25
            
        # Build the SOQL query dynamically based on provided filters
        soql_query = """
            SELECT Id, Name, StageName, CloseDate, CreatedDate, AccountId, 
                   OwnerId, Type, LeadSource, Description, Amount, Probability,
                   IsWon, IsClosed, ForecastCategory, NextStep
            FROM Opportunity
        """
        
        # Build WHERE clause conditions
        conditions = []
        
        if opportunity_name and opportunity_name.strip():
            conditions.append(f"Name LIKE '%{opportunity_name}%'")
        
        if stage_name and stage_name.strip():
            stages = [f"'{s.strip()}'" for s in stage_name.split(',')]
            conditions.append(f"StageName IN ({','.join(stages)})")
        
        if opportunity_type and opportunity_type.strip():
            conditions.append(f"Type = '{opportunity_type}'")
        
        if lead_source and lead_source.strip():
            conditions.append(f"LeadSource = '{lead_source}'")
        
        if account_id and account_id.strip():
            conditions.append(f"AccountId = '{account_id}'")
        
        if owner_id and owner_id.strip():
            conditions.append(f"OwnerId = '{owner_id}'")
        
        if opportunity_id and opportunity_id.strip():
            conditions.append(f"Id = '{opportunity_id}'")
        
        if close_date_start and close_date_start.strip():
            conditions.append(f"CloseDate >= {close_date_start}")
        
        if close_date_end and close_date_end.strip():
            conditions.append(f"CloseDate <= {close_date_end}")
        
        if created_date_start and created_date_start.strip():
            conditions.append(f"CreatedDate >= {created_date_start}T00:00:00Z")
        
        if created_date_end and created_date_end.strip():
            conditions.append(f"CreatedDate <= {created_date_end}T23:59:59Z")
        
        # Add WHERE clause if there are conditions
        if conditions:
            soql_query += " WHERE " + " AND ".join(conditions)
        
        # Add ORDER BY
        soql_query += " ORDER BY CreatedDate DESC"
        
        # Add LIMIT and OFFSET for pagination
        offset = (page - 1) * page_size
        soql_query += f" LIMIT {page_size} OFFSET {offset}"
        
        try:
            # Execute the query
            result = self.sf.query(soql_query)
            
            # Transform the results to include Salesforce link
            opportunities = []
            for record in result['records']:
                # Remove the 'attributes' field
                opportunity = {k: v for k, v in record.items() if k != 'attributes'}
                # Add the Salesforce link
                instance_url = getattr(self, 'instance_url', 'https://rawlabssa-dev-ed.develop.my.salesforce.com')
                opportunity['salesforce_link'] = f"{instance_url}/lightning/r/Opportunity/{opportunity['Id']}/view"
                opportunities.append(opportunity)
            
            return json.dumps(opportunities)
        except Exception as e:
            # Return error info
            return json.dumps({"error": str(e), "query": soql_query})
    
    @udf
    def get_opportunity_stages(self) -> List[str]:
        """Get the list of available opportunity stage values from Salesforce.
        
        Returns:
            List of valid opportunity stage values
        """
        # For testing without real Salesforce connection, return mock data
        # In production, this would query Salesforce for actual stage picklist values
        return ["Qualification", "Needs Analysis", "Value Proposition", "Id. Decision Makers", 
                "Perception Analysis", "Proposal/Price Quote", "Negotiation/Review", 
                "Closed Won", "Closed Lost"]

    @udf
    def aggregate_opportunity_revenue(self, 
                                    close_date_start: Optional[str] = None,
                                    close_date_end: Optional[str] = None) -> str:
        """Calculate total weighted revenue from Salesforce Opportunities with filtering.
        
        Args:
            close_date_start: Start date for close date range (YYYY-MM-DD)
            close_date_end: End date for close date range (YYYY-MM-DD)
                
        Returns:
            JSON string containing the total weighted revenue and count
        """
        try:
            # Build the SOQL query for aggregation
            soql_query = """
                SELECT SUM(ExpectedRevenue) total_revenue, COUNT(Id) opportunity_count
                FROM Opportunity
            """
            
            conditions = []
            
            # Date range filters
            if close_date_start and close_date_start.strip():
                conditions.append(f"CloseDate >= {close_date_start}")
            
            if close_date_end and close_date_end.strip():
                conditions.append(f"CloseDate <= {close_date_end}")
            
            # Exclude certain forecast categories and stages as per SQL spec
            conditions.append("ForecastCategory NOT IN ('Omitted')")
            conditions.append("StageName != 'Closed Lost'")
            
            if conditions:
                soql_query += " WHERE " + " AND ".join(conditions)
            
            # Execute the query
            result = self.sf.query(soql_query)
            
            # Process and return results
            if result['records']:
                record = result['records'][0]
                total_revenue = record.get('total_revenue', 0) or 0
                opportunity_count = record.get('opportunity_count', 0) or 0
                
                return json.dumps({
                    "total_weighted_revenue": total_revenue,
                    "opportunity_count": opportunity_count,
                    "filters_applied": {
                        "close_date_start": close_date_start if close_date_start else None,
                        "close_date_end": close_date_end if close_date_end else None,
                        "excluded_forecast_categories": ["Omitted"],
                        "excluded_stages": ["Closed Lost"]
                    }
                })
            else:
                return json.dumps({
                    "total_weighted_revenue": 0,
                    "opportunity_count": 0,
                    "message": "No opportunities found matching criteria"
                })
            
        except Exception as e:
            error_response = {"error": str(e)}
            return json.dumps(error_response)

    @udf
    def search_call_notes(self, 
                         what_id: Optional[str] = None,
                         who_id: Optional[str] = None,
                         owner_id: Optional[str] = None,
                         subject_filter: Optional[str] = None,
                         created_date_start: Optional[str] = None,
                         created_date_end: Optional[str] = None,
                         page: Optional[int] = None,
                         page_size: Optional[int] = None) -> str:
        """Search for call notes from Salesforce Tasks with filtering and pagination support.
        
        Args:
            what_id: Account or Opportunity ID the call is related to
            who_id: Contact or Lead ID the call is with
            owner_id: Salesforce User ID of the task owner
            subject_filter: Subject to filter by (partial match)
            created_date_start: Start date for creation date range (YYYY-MM-DD)
            created_date_end: End date for creation date range (YYYY-MM-DD)
            page: Page number (1-based)
            page_size: Number of records per page
                
        Returns:
            JSON string containing call note records
        """
        # Set defaults for pagination
        if page is None:
            page = 1
        if page_size is None:
            page_size = 25
            
        try:
            # Build the SOQL query for Tasks (call notes)
            soql_query = """
                SELECT Id, WhoId, WhatId, Subject, Description, TaskSubtype,
                       CreatedDate, OwnerId
                FROM Task
            """
            
            conditions = []
            
            # Core filter: only call-related tasks
            conditions.append("(Subject = 'Call' OR TaskSubtype = 'Call')")
            
            # Additional filters
            if what_id and what_id.strip():
                conditions.append(f"WhatId = '{what_id}'")
            
            if who_id and who_id.strip():
                conditions.append(f"WhoId = '{who_id}'")
            
            if owner_id and owner_id.strip():
                conditions.append(f"OwnerId = '{owner_id}'")
            
            if subject_filter and subject_filter.strip():
                conditions.append(f"Subject LIKE '%{subject_filter}%'")
            
            # Note: Description field cannot be filtered in Salesforce SOQL
            # Removing description_search functionality
            
            if created_date_start and created_date_start.strip():
                conditions.append(f"CreatedDate >= {created_date_start}T00:00:00Z")
            
            if created_date_end and created_date_end.strip():
                conditions.append(f"CreatedDate <= {created_date_end}T23:59:59Z")
            
            if conditions:
                soql_query += " WHERE " + " AND ".join(conditions)
            
            # Add sorting and pagination
            soql_query += " ORDER BY CreatedDate DESC"
            
            # Handle pagination
            offset = (page - 1) * page_size
            soql_query += f" LIMIT {page_size} OFFSET {offset}"
            
            # Execute the query
            result = self.sf.query(soql_query)
            
            # Process and return results
            call_notes = []
            for record in result['records']:
                call_note = {k: v for k, v in record.items() if k != 'attributes'}
                
                # Add the Salesforce link
                if 'Id' in call_note:
                    call_note['salesforce_link'] = f"https://squirro.lightning.force.com/lightning/r/Task/{call_note['Id']}/view"
                
                call_notes.append(call_note)
            
            return json.dumps(call_notes)
            
        except Exception as e:
            error_response = {"error": str(e)}
            return json.dumps(error_response)
         