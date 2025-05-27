# MXCP Salesforce Example

This example demonstrates how to use MXCP with Salesforce data. It shows how to:
- Create and use a custom MXCP plugin for Salesforce integration
- Query Salesforce data using SQL
- Combine Salesforce data with other data sources

## Setup

1. First, install the Salesforce plugin:
   ```bash
   cd mxcp_plugin_salesforce
   pip install -e .
   cd ..
   ```

2. Create a configuration file with your Salesforce credentials:
   ```bash
   cp salesforce-config.example.yml salesforce-config.yml
   # Edit salesforce-config.yml with your credentials
   ```

3. Start the MXCP server:
   ```bash
   mxcp serve
   ```

## Available Tools

The example provides a tool that demonstrates various Salesforce operations:

- List available Salesforce objects
- Get object descriptions
- Query specific objects
- Execute SOQL queries

Try these example queries:

1. List all available objects:
```sql
SELECT * FROM list_sobjects();
```

2. Get field descriptions for Account:
```sql
SELECT * FROM describe_sobject('Account');
```

3. Get a specific account:
```sql
SELECT * FROM get_sobject('Account', '001xx000003DIloAAG');
```

4. Query accounts with their contacts:
```sql
WITH accounts AS (
  SELECT * FROM soql('SELECT Id, Name FROM Account')
),
contacts AS (
  SELECT * FROM soql('SELECT Id, Name, AccountId FROM Contact')
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

## Security Note

Always ensure your Salesforce credentials are kept secure and never committed to version control. The example uses a separate configuration file that is git-ignored. 