# MXCP Salesforce Python Endpoints Example

This example demonstrates how to use MXCP with Salesforce data using **plain Python endpoints** instead of plugins. This approach is simpler, more direct, and easier to debug than the plugin-based approach.

## Overview

This example provides Python MCP endpoints that allow you to:
- Execute SOQL queries to retrieve Salesforce data
- Execute SOSL searches across multiple objects
- List all available Salesforce objects
- Get detailed object descriptions
- Retrieve specific records by ID
- Perform simple text searches across common objects

## Key Differences from Plugin Approach

- **No custom plugins required** - just plain Python functions
- **Direct MCP tool calls** - no SQL wrapper layer needed
- **Simpler configuration** - no plugin registration required
- **Easier debugging** - standard Python debugging works naturally
- **More flexible** - can return any JSON-serializable data

## Configuration

### 1. Getting Salesforce Credentials

To use this example, you'll need:

1. **Salesforce Username**: Your Salesforce username (email address)
2. **Salesforce Password**: Your Salesforce password
3. **Security Token**: Your Salesforce security token (get from Setup → My Personal Information → Reset My Security Token)
4. **Instance URL**: Your Salesforce instance URL (e.g., https://your-domain.salesforce.com)
5. **Client ID**: A connected app client ID (you can use any valid client ID)

### 2. User Configuration

Add the following to your MXCP user config (`~/.mxcp/config.yml`):

```yaml
mxcp: 1

projects:
  salesforce-demo:
    profiles:
      dev:
        secrets:
          salesforce:
            instance_url: "https://your-instance.salesforce.com"
            username: "your-username@example.com"
            password: "your-password"
            security_token: "your-security-token"
            client_id: "your-client-id"
```

### 3. Site Configuration

Create an `mxcp-site.yml` file:

```yaml
mxcp: 1
project: salesforce-demo
profile: dev
secrets:
  - salesforce

extensions:
  - json
```

## Available Tools

### SOQL Query
Execute SOQL queries directly as Python function calls:
```bash
mxcp run tool soql --param query="SELECT Id, Name FROM Account LIMIT 10"
```

### SOSL Search
Execute SOSL searches across multiple objects:
```bash
mxcp run tool sosl --param query="FIND {Acme} IN ALL FIELDS RETURNING Account(Name, Phone)"
```

### Simple Search
Perform simple text searches across common objects:
```bash
mxcp run tool search --param search_term="Acme"
```

### List Objects
List all available Salesforce objects:
```bash
mxcp run tool list_sobjects
```

### Describe Object
Get detailed information about a specific object:
```bash
mxcp run tool describe_sobject --param sobject_name="Account"
```

### Get Object
Get a specific record by its ID:
```bash
mxcp run tool get_sobject --param sobject_name="Account" --param record_id="001xx000003DIloAAG"
```

## Example Usage

1. Start the MXCP server:
   ```bash
   mxcp serve
   ```

2. Or run tools directly:
   ```bash
   # List all available objects
   mxcp run tool list_sobjects
   
   # Get Account object description
   mxcp run tool describe_sobject --param sobject_name="Account"
   
   # Query all accounts
   mxcp run tool soql --param query="SELECT Id, Name, Phone FROM Account LIMIT 10"
   
   # Search for records containing "Acme"
   mxcp run tool search --param search_term="Acme"
   
   # Get specific account by ID
   mxcp run tool get_sobject --param sobject_name="Account" --param record_id="001xx000003DIloAAG"
   
   # Execute SOSL search
   mxcp run tool sosl --param query="FIND {John} IN NAME FIELDS RETURNING Contact(FirstName, LastName, Email)"
   ```

## Project Structure

```
salesforce/
├── mxcp-site.yml           # Simple site configuration
├── python/                 # Python implementations
│   └── salesforce_endpoints.py # All Salesforce endpoint functions
├── tools/                  # Tool definitions
│   ├── soql.yml
│   ├── sosl.yml
│   ├── search.yml
│   ├── list_sobjects.yml
│   ├── describe_sobject.yml
│   └── get_sobject.yml
└── README.md
```

## Key Features

- **Direct Python Functions**: No SQL wrapper layer needed
- **Async Support**: Functions can be async for better performance
- **Database Integration**: Can optionally store results in DuckDB
- **Error Handling**: Proper error responses for invalid requests
- **Type Safety**: Full type hints for better IDE support
- **Logging**: Comprehensive logging for debugging

## Migration from Plugin Approach

This example demonstrates how much simpler the Python endpoint approach is:

- **Plugin approach**: Plugin class → UDFs → SQL calls → Tool definitions
- **Python approach**: Python functions → Tool definitions

The functionality is identical, but the implementation is much more straightforward!

## Common Use Cases

### 1. Explore Your Salesforce Org
```bash
# First, see what objects are available
mxcp run tool list_sobjects

# Then describe an object to see its fields
mxcp run tool describe_sobject --param sobject_name="Account"
```

### 2. Query Specific Data
```bash
# Get all accounts in a specific city
mxcp run tool soql --param query="SELECT Id, Name, Phone FROM Account WHERE BillingCity = 'New York'"

# Get contacts for a specific account
mxcp run tool soql --param query="SELECT Id, Name, Email FROM Contact WHERE AccountId = '001xx000003DIloAAG'"
```

### 3. Search for Records
```bash
# Find all records mentioning "Acme"
mxcp run tool search --param search_term="Acme"

# More specific SOSL search
mxcp run tool sosl --param query="FIND {Acme} IN ALL FIELDS RETURNING Account(Name, Phone), Contact(FirstName, LastName)"
```

## Notes

- Make sure to keep your Salesforce credentials secure and never commit them to version control
- The example requires proper authentication and API permissions to work with your Salesforce instance
- Functions return JSON data that can be directly used by MCP clients
- Results can optionally be stored in DuckDB for further SQL analysis
- All query results have the 'attributes' field removed for cleaner output 