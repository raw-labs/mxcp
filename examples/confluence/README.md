# MXCP Confluence Plugin Example

This example demonstrates how to use MXCP with Confluence data. It shows how to:
- Create and use a custom MXCP plugin for Confluence integration
- Query Confluence content using SQL
- Combine Confluence data with other data sources

## Overview

The plugin provides several UDFs that allow you to:
- Search pages using keywords and CQL queries
- Fetch page content and metadata
- List child pages and spaces
- Navigate the Confluence content hierarchy

## Configuration

### 1. Creating an Atlassian API Token

**Important:** This plugin currently only supports API tokens **without scopes**. While Atlassian has introduced scoped API tokens, there are known compatibility issues when using scoped tokens with basic authentication that this plugin relies on.

To create an API token without scopes:

1. **Log in to your Atlassian account** at [https://id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

2. **Verify your identity** (if prompted):
   - Atlassian may ask you to verify your identity before creating API tokens
   - Check your email for a one-time passcode and enter it when prompted

3. **Create the API token**:
   - Click **"Create API token"** (not "Create API token with scopes")
   - Enter a descriptive name for your token (e.g., "MXCP Confluence Integration")
   - Select an expiration date (tokens can last from 1 day to 1 year)
   - Click **"Create"**

4. **Copy and save your token**:
   - Click **"Copy to clipboard"** to copy the token
   - **Important:** Save this token securely (like in a password manager) as you won't be able to view it again
   - This token will be used as your "password" in the configuration below

### 2. User Configuration

Add the following to your MXCP user config (`~/.mxcp/config.yml`). You can use the example `config.yml` in this directory as a template:

```yaml
mxcp: 1

projects:
  confluence-demo:
    profiles:
      dev:
        plugin:
          config:
            confluence:
              url: "https://your-domain.atlassian.net/wiki"
              username: "your-email@example.com"
              password: "your-api-token"  # Use the API token you created above
```

**Configuration Notes:**
- Replace `your-domain` with your actual Atlassian domain
- Replace `your-email@example.com` with the email address of your Atlassian account
- Replace `your-api-token` with the API token you created in step 1
- The `password` field should contain your API token, not your actual Atlassian password

### 2. Site Configuration

Create an `mxcp-site.yml` file:

```yaml
mxcp: 1
project: confluence-demo
profile: dev
plugin:
  - name: confluence
    module: mxcp_plugin_confluence
    config: confluence
```

## Available Tools

### Search Pages
```sql
-- Search for pages containing specific text
SELECT search_pages_confluence($query, $limit) as result;
```

### Get Page
```sql
-- Fetch a page's content
SELECT get_page_confluence($page_id) as result;
```

### Get Children
```sql
-- List direct children of a page
SELECT get_children_confluence($page_id) as result;
```

### List Spaces
```sql
-- List all accessible spaces
SELECT list_spaces_confluence() as result;
```

### Describe Page
```sql
-- Show metadata about a page
SELECT describe_page_confluence($page_id) as result;
```

## Example Queries

1. Search and analyze page content:
```sql
WITH pages AS (
  SELECT * FROM search_pages_confluence('important documentation', 50)
)
SELECT 
  p.title as page_title,
  p.space.name as space_name,
  p.version.number as version,
  p.metadata.created as created_date
FROM pages p
ORDER BY p.metadata.created DESC;
```

## Plugin Development

The `mxcp_plugin_confluence` directory contains a complete MXCP plugin implementation that you can use as a reference for creating your own plugins. It demonstrates:

- Plugin class structure
- Type conversion
- UDF implementation
- Configuration handling

## Running the Example

1. Set the `MXCP_CONFIG` environment variable to point to your config file:
   ```bash
   export MXCP_CONFIG=/path/to/examples/confluence/config.yml
   ```

2. Start the MXCP server:
   ```bash
   mxcp serve
   ```

## Notes

- Make sure to keep your API token secure and never commit it to version control.
- The plugin requires proper authentication and API permissions to work with your Confluence instance.
- All functions return JSON strings containing the requested data. 