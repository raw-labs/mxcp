# MXCP Jira Plugin Example

This example demonstrates how to use MXCP with Jira data. It shows how to:
- Create and use a custom MXCP plugin for Jira integration
- Query Jira data using SQL
- Combine Jira data with other data sources

## Overview

The plugin provides several UDFs that allow you to:
- Execute JQL queries to search issues
- Get user information
- List projects and their details
- Get project metadata

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
   - Enter a descriptive name for your token (e.g., "MXCP Jira Integration")
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
  jira-demo:
    profiles:
      dev:
        plugin:
          config:
            jira:
              url: "https://your-domain.atlassian.net"
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
project: jira-demo
profile: dev
plugin:
  - name: jira
    module: mxcp_plugin_jira
    config: jira
```

## Available Tools

### JQL Query
```sql
-- Execute a JQL query to search issues
SELECT jql_query_jira($jql, $limit) as result;
```

### Get User
```sql
-- Get user information
SELECT get_user_jira($username) as result;
```

### List Projects
```sql
-- List all projects
SELECT list_projects_jira($project_name) as result;
```

### Get Project
```sql
-- Get project details
SELECT get_project_jira($project_key) as result;
```

## Example Queries

1. Query issues with their assignees:
```sql
WITH issues AS (
  SELECT * FROM jql_query_jira('project = "PROJ" ORDER BY created DESC', 100)
)
SELECT 
  i.key as issue_key,
  i.fields.summary as summary,
  i.fields.assignee.displayName as assignee
FROM issues i;
```

## Plugin Development

The `mxcp_plugin_jira` directory contains a complete MXCP plugin implementation that you can use as a reference for creating your own plugins. It demonstrates:

- Plugin class structure
- Type conversion
- UDF implementation
- Configuration handling

## Running the Example

1. Set the `MXCP_CONFIG` environment variable to point to your config file:
   ```bash
   export MXCP_CONFIG=/path/to/examples/jira/config.yml
   ```

2. Start the MXCP server:
   ```bash
   mxcp serve
   ```

## Notes

- Make sure to keep your API token secure and never commit it to version control.
- The plugin requires proper authentication and API permissions to work with your Jira instance.
- All functions return JSON strings containing the requested data. 