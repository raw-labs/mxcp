# MXCP Salesforce Python Endpoints Example

This example demonstrates how to use MXCP with Salesforce data using **Python endpoints**.

## Overview

This example provides Python MCP endpoints that allow you to:
- Execute SOQL queries to retrieve Salesforce data
- Execute SOSL searches across multiple objects
- List all available Salesforce objects
- Get detailed object descriptions
- Retrieve specific records by ID
- Perform simple text searches across common objects

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

## Project Structure

```
salesforce/
├── mxcp-site.yml           # Site configuration
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