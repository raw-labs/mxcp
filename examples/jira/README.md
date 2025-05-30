# MXCP Jira Plugin Example

This example demonstrates how to use the MXCP Jira plugin to interact with Jira.

## Overview

The plugin provides several UDFs that allow you to:
- Execute JQL queries
- Get user information
- List projects
- Get project details

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
-- Execute a JQL query
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