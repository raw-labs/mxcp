# Connect Jira to MXCP with OAuth

This example shows how to connect JIRA to MXCP using secure OAuth authentication.

## What You Get

Once configured, you can interact with your Jira data through MXCP tools:

- **JQL Query**: Execute JQL queries to search for issues
- **List Projects**: Get all your accessible projects
- **Get Project**: Get detailed information about a specific project
- **Get Issue**: Retrieve detailed issue information by key
- **User Management**: Search users and get user details
- **Project Roles**: View project roles and their members

These tools provide comprehensive access to your Jira instance through a secure OAuth connection.

## Quick Setup Guide

### Step 1: Create Your OAuth App in Atlassian

1. Go to [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/)
2. Click **Create** → **OAuth 2.0 (3LO)**
3. Fill in your app details:
   - **App name**: `MXCP Jira Integration` (or whatever you prefer)
   - **Description**: `OAuth integration for MXCP`
4. Click **Create**

### Step 2: Configure OAuth Settings

After creating your app:

1. Click on your newly created app
2. Go to **Permissions** → **Add** → **Jira API**
3. Add these scopes:
   - `read:me` (to read your own profile information)
   - `read:jira-work` (to read issues and projects)
   - `read:jira-user` (to read user information)
   - `offline_access` (to refresh tokens)

4. Go to **Authorization** → **OAuth 2.0 (3LO)**
5. Add your callback URL based on your deployment:
   - **For production**: `https://your-domain.com/atlassian/callback`
   - **For local development**: `http://localhost:8000/atlassian/callback`
   - **For ngrok testing**: `https://your-ngrok-url.ngrok.io/atlassian/callback`

6. **Important**: Save your **Client ID** and **Client Secret** - you'll need these next!

### Step 3: Set Up Environment Variables

Create a `.env` file or set these environment variables:

```bash
export ATLASSIAN_CLIENT_ID="your-client-id-here"
export ATLASSIAN_CLIENT_SECRET="your-client-secret-here"
```

### Step 4: Configure MXCP

This example includes a ready-to-use `config.yml` file that you can customize with your OAuth credentials. You can either:

- **Use the included file**: Edit the existing `config.yml` in this directory
- **Create your own**: Use the template below

Configuration template:

```yaml
mxcp: 1.0.0
transport:
  http:
    port: 8000
    host: 0.0.0.0
    # Set base_url to your server's public URL for production
    base_url: http://localhost:8000

projects:
  my-jira-project:
    profiles:
      dev:
        # OAuth Configuration
        auth:
          provider: atlassian
          atlassian:
            client_id: "${ATLASSIAN_CLIENT_ID}"
            client_secret: "${ATLASSIAN_CLIENT_SECRET}"
            scope: "read:me read:jira-work read:jira-user offline_access"
            callback_path: "/atlassian/callback"
            auth_url: "https://auth.atlassian.com/authorize"
            token_url: "https://auth.atlassian.com/oauth/token"
```

### Step 5: Install and Run

1. **Install dependencies**:
   ```bash
   pip install atlassian-python-api requests
   ```

2. **Start MXCP**:
   ```bash
   # From the examples/jira-oauth directory:
   MXCP_CONFIG=config.yml mxcp serve
   ```

3. **Authenticate**:
   - Configure the MXCP server in your MCP client (e.g., Claude Desktop)
   - When the client connects, you'll be redirected to Atlassian to authorize the app
   - After authorization, you'll be redirected back to your MCP client
   - You're now ready to use the Jira tools!

## Available Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `jql_query` | Execute JQL queries to search for issues | `query`, `start` (optional), `limit` (optional) |
| `list_projects` | List all your accessible projects | None |
| `get_project` | Get details for a specific project | `project_key` |
| `get_issue` | Get detailed information for a specific issue | `issue_key` |
| `get_user` | Get user information by account ID | `account_id` |
| `search_user` | Search for users by query string | `query` |
| `get_project_roles` | Get all roles available in a project | `project_key` |
| `get_project_role_users` | Get users and groups for a specific role | `project_key`, `role_name` |

## Example Usage

When connected to an MCP client (like Claude Desktop), you can use these tools to interact with your Jira instance:

**Find Issues:**
- Use `jql_query` with queries like `"assignee = currentUser() AND status != Done"` to find your open issues
- Search for bugs with `"priority = High AND type = Bug"`
- Find recent activity with `"project = MYPROJECT AND updated >= -3d"`

**Manage Projects:**
- Use `list_projects` to see all accessible projects
- Use `get_project` with a project key like `"TEST"` to get project details
- Use `get_project_roles` to see available roles in a project

**User Management:**
- Use `search_user` with queries like `"john@company.com"` or `"Benjamin"` to find users
- Use `get_user` with an account ID to get detailed user information
- Use `get_project_role_users` to see who has specific roles in projects

**Issue Details:**
- Use `get_issue` with an issue key like `"RD-123"` to get comprehensive issue information
