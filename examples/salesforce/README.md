# MXCP Salesforce Example

This example demonstrates how to use MXCP with Salesforce data. It shows how to:
- Create and use a custom MXCP plugin for Salesforce integration
- Query Salesforce data using SQL
- Combine Salesforce data with other data sources

## Setup

1. Configure your Salesforce credentials:
   Add the following to your MXCP user config (`~/.mxcp/config.yml`). You can use the example `config.yml` in this directory as a template:

   ```yaml
   mxcp: 1.0.0

   projects:
     salesforce-demo:
       profiles:
         dev:
           plugin:
             config:
               salesforce:
                 instance_url: "https://your-instance.salesforce.com"
                 username: "your-username@example.com"
                 password: "your-password"
                 security_token: "your-security-token"
                 client_id: "your-client-id"
   ```

2. Create an `mxcp-site.yml` file:

   ```yaml
   mxcp: 1.0.0
   project: salesforce-demo
   profile: dev
   plugin:
     - name: salesforce
       module: mxcp_plugin_salesforce
       config: salesforce
   ```

3. Start the MXCP server:
   ```bash
   mxcp serve
   ```

## Available Tools

The example provides several tools for interacting with Salesforce:

### List Objects
```sql
-- List all available Salesforce objects
SELECT list_sobjects_salesforce() as result;
```

### Describe Object
```sql
-- Get field descriptions for an object
SELECT describe_sobject_salesforce($object_name) as result;
```

### Get Object
```sql
-- Get a specific record
SELECT get_sobject_salesforce($object_name, $record_id) as result;
```

### SOQL Query
```sql
-- Execute a SOQL query
SELECT soql_salesforce($query) as result;
```

### SOSL Search
```sql
-- Execute a SOSL search
SELECT sosl_salesforce($query) as result;
```

## Example Queries

1. Query accounts with their contacts:
```sql
WITH accounts AS (
  SELECT * FROM soql_salesforce('SELECT Id, Name FROM Account')
),
contacts AS (
  SELECT * FROM soql_salesforce('SELECT Id, Name, AccountId FROM Contact')
)
SELECT 
  a.Name as account_name,
  ARRAY_AGG(c.Name) as contact_names
FROM accounts a
LEFT JOIN contacts c ON c.AccountId = a.Id
GROUP BY a.Name;
```

## Plugin Development

The `mxcp_plugin_salesforce` directory contains a complete MXCP plugin implementation that you can use as a reference for creating your own plugins. It demonstrates:

- Plugin class structure
- Type conversion
- UDF implementation
- Configuration handling

## Notes

- Make sure to keep your Salesforce credentials secure and never commit them to version control.
- The plugin requires proper authentication and API permissions to work with your Salesforce instance.
- All functions return JSON strings containing the requested data. 