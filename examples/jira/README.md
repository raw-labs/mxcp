# MXCP Jira Python Endpoints Example

This example demonstrates how to use MXCP with Jira data using Python endpoints. This approach uses Python functions directly as MCP tools.

## Overview

This example provides Python MCP endpoints that allow you to:
- Execute JQL queries to search issues
- Get detailed information for specific issues
- Get user information
- List projects and their details
- Get project metadata

## Implementation Approach

This example uses Python functions that are exposed as MCP tools:
- Python functions handle the Jira API interactions
- Tool definitions map to these Python functions
- Results are returned as JSON data

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
   - Enter a descriptive name for your token (e.g., "MXCP Jira Python Integration")
   - Select an expiration date (tokens can last from 1 day to 1 year)
   - Click **"Create"**

4. **Copy and save your token**:
   - Click **"Copy to clipboard"** to copy the token
   - **Important:** Save this token securely (like in a password manager) as you won't be able to view it again
   - This token will be used as your "password" in the configuration below

### 2. User Configuration

Add the following to your MXCP user config (`~/.mxcp/config.yml`):

```yaml
mxcp: 1

projects:
  jira-demo:
    profiles:
      default:
        secrets:
          - name: "jira"
            type: "python"
            parameters:
              url: "https://your-domain.atlassian.net"
              username: "your-email@example.com"
              password: "your-api-token"  # Use the API token you created above
```

### 3. Site Configuration

Create an `mxcp-site.yml` file:

```yaml
mxcp: 1
project: jira-demo
profile: default
secrets:
  - jira
```

## Available Tools

### JQL Query
Execute JQL queries:
```bash
mxcp run tool jql_query --param query="project = TEST" --param limit=10
```

### Get Issue
Get detailed information for a specific issue by its key:
```bash
mxcp run tool get_issue --param issue_key="RD-123"
```

### Get User
Get a specific user by their account ID:
```bash
mxcp run tool get_user --param account_id="557058:ab168c94-8485-405c-88e6-6458375eb30b"
```

### Search Users
Search for users by name, email, or other criteria:
```bash
mxcp run tool search_user --param query="john.doe@example.com"
```

### List Projects
List all projects:
```bash
mxcp run tool list_projects
```

### Get Project
Get project details:
```bash
mxcp run tool get_project --param project_key="TEST"
```

### Get Project Roles
Get all roles available in a project:
```bash
mxcp run tool get_project_roles --param project_key="TEST"
```

### Get Project Role Users
Get users and groups for a specific role in a project:
```bash
mxcp run tool get_project_role_users --param project_key="TEST" --param role_name="Developers"
```

## Project Structure

```
jira-python/
├── mxcp-site.yml           # Site configuration
├── python/                 # Python implementations
│   └── jira_endpoints.py   # All JIRA endpoint functions
├── tools/                  # Tool definitions
│   ├── jql_query.yml
│   ├── get_issue.yml
│   ├── get_user.yml
│   ├── search_user.yml
│   ├── list_projects.yml
│   ├── get_project.yml
│   ├── get_project_roles.yml
│   └── get_project_role_users.yml
└── README.md
```