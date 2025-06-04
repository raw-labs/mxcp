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

### 1. User Configuration

Add the following to your MXCP user config (`~/.mxcp/config.yml`). You can use the example `config.yml` in this directory as a template:

```yaml
mxcp: 1.0.0

projects:
  jira-demo:
    profiles:
      dev:
        plugin:
          config:
            jira:
              url: "https://your-domain.atlassian.net"
              username: "your-email@example.com"
              password: "your-api-token"
```

### 2. Site Configuration

Create an `mxcp-site.yml` file:

```yaml
mxcp: 1.0.0
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