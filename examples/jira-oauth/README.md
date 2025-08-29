# Connect Jira to MXCP with OAuth

This example shows how to connect JIRA to MXCP using secure OAuth authentication.

## What You Get

Once configured, you can query your Jira data directly from MXCP:

```sql
-- Find all issues assigned to you
SELECT jql_query_jira('assignee = currentUser()') AS my_issues;

-- Get recent bugs in a project
SELECT jql_query_jira('project = MYPROJECT AND type = Bug AND created >= -7d') AS recent_bugs;

-- List all your accessible projects
SELECT list_projects_jira() AS projects;

-- Get user information
SELECT get_user_jira('john.doe@company.com') AS user_info;
```

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
          clients:
            - client_id: "${ATLASSIAN_CLIENT_ID}"
              client_secret: "${ATLASSIAN_CLIENT_SECRET}"
              name: "MXCP Jira Integration"
              redirect_uris:
                # For production, use your actual domain (must match base_url above)
                - "https://your-domain.com/atlassian/callback"
                # For local development, uncomment the line below:
                # - "http://localhost:8000/atlassian/callback"
              scopes:
                - "mxcp:access"
          atlassian:
            client_id: "${ATLASSIAN_CLIENT_ID}"
            client_secret: "${ATLASSIAN_CLIENT_SECRET}"
            scope: "read:me read:jira-work read:jira-user offline_access"
            callback_path: "/atlassian/callback"
            auth_url: "https://auth.atlassian.com/authorize"
            token_url: "https://auth.atlassian.com/oauth/token"
        
        # Plugin Configuration (minimal setup required!)
        plugin:
          config:
            jira_oauth: {}  # Named 'jira_oauth' here, but UDFs use 'jira' suffix from mxcp-site.yml
```

### Step 5: Install and Run

1. **Install dependencies**:
   ```bash
   pip install atlassian-python-api requests
   ```

2. **Start MXCP**:
   ```bash
   # From the examples/jira-oauth directory:
   mxcp serve --config config.yml
   ```

3. **Authenticate**:
   - Configure the MXCP server in your MCP client (e.g., Claude Desktop)
   - When the client connects, you'll be redirected to Atlassian to authorize the app
   - After authorization, you'll be redirected back to your MCP client
   - You're now ready to query Jira!

## Available Functions

| Function | Description | Example |
|----------|-------------|---------|
| `jql_query_jira(query, start, limit)` | Execute JQL queries | `SELECT jql_query_jira('project = TEST')` |
| `list_projects_jira()` | List all your accessible projects | `SELECT list_projects_jira()` |
| `get_project_jira(key)` | Get details for a specific project | `SELECT get_project_jira('TEST')` |
| `get_user_jira(username)` | Get user information | `SELECT get_user_jira('john@company.com')` |

## Example Queries

```sql
-- Get your assigned issues
SELECT jql_query_jira('assignee = currentUser() AND status != Done', 0, 20) AS my_open_issues;

-- Find high priority bugs
SELECT jql_query_jira('priority = High AND type = Bug', 0, 10) AS high_priority_bugs;

-- Recent activity in a project
SELECT jql_query_jira('project = MYPROJECT AND updated >= -3d') AS recent_activity;

-- Get project information
SELECT 
    list_projects_jira() AS all_projects,
    get_project_jira('MYPROJECT') AS project_details;

-- Find issues by reporter
SELECT jql_query_jira('reporter = "john.doe@company.com"') AS johns_issues;
```
