# MXCP Jira Python Endpoints Example

This example demonstrates how to use MXCP with Jira data using **plain Python endpoints** instead of plugins. This approach is simpler, more direct, and easier to debug than the plugin-based approach.

## Overview

This example provides Python MCP endpoints that allow you to:
- Execute JQL queries to search issues
- Get detailed information for specific issues
- Get user information
- List projects and their details
- Get project metadata

## Key Differences from Plugin Approach

- **No custom plugins required** - just plain Python functions
- **Direct MCP tool calls** - no SQL wrapper layer needed
- **Simpler configuration** - no plugin registration required
- **Easier debugging** - standard Python debugging works naturally
- **More flexible** - can return any JSON-serializable data

## Configuration

### 1. Creating an Atlassian API Token

Follow the same process as the plugin example:

1. **Log in to your Atlassian account** at [https://id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

2. **Create the API token**:
   - Click **"Create API token"** (not "Create API token with scopes")
   - Enter a descriptive name for your token (e.g., "MXCP Jira Python Integration")
   - Select an expiration date
   - Click **"Create"**

3. **Copy and save your token** securely

### 2. User Configuration

Add the following to your MXCP user config (`~/.mxcp/config.yml`):

```yaml
mxcp: 1

projects:
  jira-python-demo:
    profiles:
      default:
        secrets:
          # JIRA credentials - using "python" type to demonstrate behavior
          - name: "jira"
            type: "python"  # This will cause DuckDB injection to fail (but continue gracefully)
            parameters:
              url: "https://your-domain.atlassian.net"
              username: "your-email@example.com"
              password: "your-api-token"  # Use the API token you created above
```

### Experimental Setup: DuckDB Secret Injection

This example is set up to demonstrate what happens when:
1. **Secret is required** - Listed in `mxcp-site.yml`'s `secrets` array
2. **Invalid DuckDB type** - Using `type: "python"` which DuckDB doesn't understand

**Expected behavior:**
- DuckDB injection will fail during startup (logged as debug message)
- Python endpoints will still work perfectly via `config.get_secret()`  
- Server will continue running normally

This shows MXCP's graceful handling of unsupported secret types!

### 3. Site Configuration

Create an `mxcp-site.yml` file:

```yaml
mxcp: 1
project: jira-python-demo
profile: default
secrets:
  - jira  # This forces the secret to be injected into DuckDB
```

Note: We're listing the JIRA secret as required to demonstrate DuckDB injection behavior.

## Available Tools

### JQL Query
Execute JQL queries directly as Python function calls:
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



## Example Usage

1. Start the MXCP server:
   ```bash
   mxcp serve
   ```

2. Or run tools directly:
      ```bash
   # Query recent issues
   mxcp run tool jql_query --param query="project = TEST ORDER BY created DESC" --param limit=5
   
   # Get specific issue details
   mxcp run tool get_issue --param issue_key="RD-123"
   
        # Get specific user by account ID
     mxcp run tool get_user --param account_id="557058:ab168c94-8485-405c-88e6-6458375eb30b"
    
    # Search for users
    mxcp run tool search_user --param query="admin"
   
   # List all projects
   mxcp run tool list_projects
   
       # Get specific project
    mxcp run tool get_project --param project_key="TEST"
    
    # Get project roles
    mxcp run tool get_project_roles --param project_key="TEST"
    
    # Get users for specific role
    mxcp run tool get_project_role_users --param project_key="TEST" --param role_name="Developers"
    ```

## Project Structure

```
jira-python/
├── mxcp-site.yml           # Simple site configuration
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

## Notes

- Make sure to keep your API token secure and never commit it to version control
- The plugin requires proper authentication and API permissions to work with your Jira instance
- Functions return JSON data that can be directly used by MCP clients
- Results can optionally be stored in DuckDB for further SQL analysis 