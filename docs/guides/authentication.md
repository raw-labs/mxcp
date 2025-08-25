---
title: "Authentication"
description: "Set up OAuth authentication in MXCP with GitHub, Atlassian, or Salesforce. Secure your endpoints and tools with enterprise-grade authentication."
keywords:
  - mxcp authentication
  - oauth setup
  - github oauth
  - atlassian oauth
  - salesforce oauth
  - endpoint security
sidebar_position: 2
slug: /guides/authentication
---

# Authentication

MXCP supports OAuth authentication to protect your endpoints and tools. When authentication is enabled, all tools, resources, prompts, and built-in SQL features require valid authentication tokens.

## Overview

Authentication is configured in your user configuration file (`~/.mxcp/config.yml`) under each profile's `auth` section. MXCP supports multiple OAuth providers and can be easily extended to support additional providers.

### How It Works

When authentication is enabled:

1. **Server Startup**: The MXCP server initializes with OAuth support
2. **Client Registration**: MCP clients can register with the OAuth server
3. **Authorization Flow**: Clients are redirected to the OAuth provider for authentication
4. **Token Exchange**: Provider auth codes are exchanged for access tokens
5. **Protected Access**: All endpoints require valid tokens

### Protected Features

When authentication is enabled, the following features require authentication:

- **Custom Endpoints**: All tools, resources, and prompts defined in your YAML files
- **SQL Tools**: Built-in DuckDB querying and schema exploration tools

### User Information Logging

When OAuth authentication is enabled, MXCP automatically logs detailed user information for each authenticated request, including:

- Username and user ID
- OAuth provider (e.g., GitHub, Atlassian)
- User's display name and email (when available)

This information appears in the server logs whenever an authenticated user executes any tool, resource, or prompt.

## Supported Providers

Currently supported providers:
- `none` (default, no authentication)
- `github` (GitHub OAuth)
- `atlassian` (Atlassian Cloud - JIRA & Confluence)
- `salesforce` (Salesforce Cloud)
- `keycloak` (Keycloak - Open Source Identity and Access Management)
- `google` (Google OAuth - Google Workspace APIs)

## Provider Configuration

### Disable Authentication (Default)

By default, authentication is disabled:

```yaml
projects:
  my_project:
    profiles:
      dev:
        auth:
          provider: none
```

### GitHub OAuth

#### Creating a GitHub OAuth App

1. **Create a GitHub OAuth App**:
   - Go to GitHub Settings > Developer settings > OAuth Apps
   - Click "New OAuth App"
   - Set the Authorization callback URL to: `http://localhost:8000/github/callback` (adjust host/port as needed)

2. **Get Your Credentials**:
   - Copy your **Client ID** and **Client Secret**
   - Store these securely as environment variables

#### Environment Variables

Set these environment variables with your GitHub OAuth credentials:

```bash
export GITHUB_CLIENT_ID="your_github_client_id"
export GITHUB_CLIENT_SECRET="your_github_client_secret"
```

#### MXCP Configuration

Configure GitHub OAuth in your profile's auth section:

```yaml
projects:
  my_project:
    profiles:
      dev:
        auth:
          provider: github
          clients:
            - client_id: "${GITHUB_CLIENT_ID}"
              client_secret: "${GITHUB_CLIENT_SECRET}"
              name: "My MXCP Application"
              redirect_uris:
                - "http://localhost:8000/github/callback"
              scopes:
                - "mxcp:access"
          github:
            client_id: "${GITHUB_CLIENT_ID}"
            client_secret: "${GITHUB_CLIENT_SECRET}"
            scope: "user:email"
            callback_path: "/github/callback"
            auth_url: "https://github.com/login/oauth/authorize"
            token_url: "https://github.com/login/oauth/access_token"
```

#### Configuration Options

- `client_id`: Your GitHub OAuth app client ID
- `client_secret`: Your GitHub OAuth app client secret
- `scope`: OAuth scope to request (default: "user:email")
- `callback_path`: Callback path for OAuth flow (default: "/github/callback")
- `auth_url`: GitHub authorization URL
- `token_url`: GitHub token exchange URL

#### Testing Your Configuration

1. Start your MXCP server:
   ```bash
   mxcp serve --debug
   ```

2. The authentication flow will begin when a client connects
3. Users will be redirected to GitHub for authorization
4. After approval, they'll be redirected back to your callback URL
5. Check the logs for successful authentication

#### Troubleshooting

**Common Issues:**

1. **Invalid Client Configuration**:
   ```
   ValueError: GitHub OAuth configuration is incomplete
   ```
   - Ensure all required GitHub configuration fields are provided

2. **Environment Variables Not Set**:
   ```
   ValueError: Environment variable GITHUB_CLIENT_ID is not set
   ```
   - Set the required environment variables before starting the server

3. **Callback URL Mismatch**:
   ```
   HTTPException: Invalid state parameter
   ```
   - Ensure the callback URL in your GitHub OAuth app matches the configured callback_path

### Atlassian OAuth (JIRA & Confluence Cloud)

MXCP supports OAuth authentication with Atlassian Cloud products including JIRA and Confluence. This allows your MCP server to authenticate users and access Atlassian APIs on their behalf.

#### Creating an Atlassian OAuth App

Before configuring MXCP, you need to create an OAuth 2.0 (3LO) app in the Atlassian Developer Console:

**Step 1: Access the Developer Console**

1. Go to [developer.atlassian.com](https://developer.atlassian.com)
2. Sign in with your Atlassian account
3. Click your profile icon in the top-right corner
4. Select **Developer console** from the dropdown

**Step 2: Create a New App**

1. Click **Create** and select **OAuth 2.0 (3LO)**
2. Enter your app details:
   - **App name**: A descriptive name for your application
   - **Description**: Brief description of what your app does

**Step 3: Configure OAuth 2.0**

1. In your app, select **Authorization** from the left menu
2. Next to **OAuth 2.0 (3LO)**, click **Configure**
3. Set the **Callback URL** to match your MXCP server:
   - For local development: `http://localhost:8000/atlassian/callback`
   - For production: `https://your-domain.com/atlassian/callback`
4. Click **Save changes**

**Step 4: Add API Permissions**

1. Select **Permissions** from the left menu
2. Add the APIs you need:
   - **Jira platform REST API** - for JIRA access
   - **Confluence Cloud REST API** - for Confluence access
   - **User Identity API** - for user profile information
3. For each API, click **Add** and configure the required scopes.

**Step 5: Get Your Credentials**

1. Go to **Settings** in the left menu
2. Copy your **Client ID** and **Secret**
3. Store these securely as environment variables

#### Environment Variables

Set these environment variables with your Atlassian OAuth credentials:

```bash
export ATLASSIAN_CLIENT_ID="your_client_id_here"
export ATLASSIAN_CLIENT_SECRET="your_client_secret_here"
```

#### MXCP Configuration

Configure Atlassian OAuth in your profile's auth section:

```yaml
projects:
  my_project:
    profiles:
      production:
        auth:
          provider: atlassian
          clients:
            - client_id: "${ATLASSIAN_CLIENT_ID}"
              client_secret: "${ATLASSIAN_CLIENT_SECRET}"
              name: "My MXCP Application"
              redirect_uris:
                - "https://your-domain.com/atlassian/callback"
              scopes:
                - "mxcp:access"
          atlassian:
            client_id: "${ATLASSIAN_CLIENT_ID}"
            client_secret: "${ATLASSIAN_CLIENT_SECRET}"
            scope: "read:me read:jira-work read:jira-user read:confluence-content.all read:confluence-user offline_access"
            callback_path: "/atlassian/callback"
            auth_url: "https://auth.atlassian.com/authorize"
            token_url: "https://auth.atlassian.com/oauth/token"
```

#### OAuth Scopes

Atlassian uses granular scopes to control access. Common scopes include:

**JIRA Scopes:**
- `read:jira-work` - Read issues, projects, and work items
- `write:jira-work` - Create and update issues
- `read:jira-user` - Read user information
- `manage:jira-project` - Manage projects (admin level)
- `manage:jira-configuration` - Manage JIRA configuration (admin level)

**Confluence Scopes:**
- `read:confluence-content.all` - Read all Confluence content
- `write:confluence-content` - Create and update content
- `read:confluence-user` - Read user information
- `manage:confluence-configuration` - Manage Confluence settings (admin level)

**Universal Scopes:**
- `read:me` - Read user profile information
- `offline_access` - Enable refresh tokens for long-term access

#### Accessing Multiple Sites

Atlassian OAuth grants access to all sites where your app is installed. To work with specific sites:

1. **Get accessible resources**:
   ```bash
   curl -H "Authorization: Bearer ACCESS_TOKEN" \
        https://api.atlassian.com/oauth/token/accessible-resources
   ```

2. **Use the cloud ID** in API requests:
   ```bash
   # JIRA API example
   curl -H "Authorization: Bearer ACCESS_TOKEN" \
        https://api.atlassian.com/ex/jira/{cloudid}/rest/api/2/project
   
   # Confluence API example  
   curl -H "Authorization: Bearer ACCESS_TOKEN" \
        https://api.atlassian.com/ex/confluence/{cloudid}/rest/api/space
   ```

#### Testing Your Configuration

1. Start your MXCP server:
   ```bash
   mxcp serve --debug
   ```

2. The authentication flow will begin when a client connects
3. Users will be redirected to Atlassian for authorization
4. After approval, they'll be redirected back to your callback URL
5. Check the logs for successful authentication

#### Troubleshooting

**Common Issues:**

1. **Invalid Client Configuration**:
   ```
   ValueError: Atlassian OAuth configuration is incomplete
   ```
   - Ensure `client_id` and `client_secret` are provided
   - Check that environment variables are set correctly

2. **Callback URL Mismatch**:
   ```
   HTTPException: Invalid state parameter
   ```
   - Verify the callback URL in your Atlassian app matches your MXCP configuration
   - Ensure the URL scheme (http/https) is correct

3. **Insufficient Permissions**:
   ```
   403 Forbidden
   ```
   - Check that your app has the required API permissions in the Developer Console
   - Verify the user has access to the requested resources

4. **Site Access Issues**:
   ```
   No accessible resources found
   ```
   - Ensure your app is installed on the Atlassian site
   - Check that the user has granted access to your app

**Debug Tips:**

- Enable debug logging: `mxcp serve --debug`
- Check the Atlassian Developer Console for app installation status
- Verify OAuth scopes match your API requirements
- Test with a simple scope like `read:me` first

#### Security Best Practices

- **Store credentials securely**: Use environment variables, not config files
- **Use HTTPS**: Required for production OAuth flows
- **Minimal scopes**: Request only the permissions you need
- **Token management**: Implement proper token refresh logic
- **Site validation**: Verify users have access to required Atlassian sites

### Salesforce OAuth (Salesforce Cloud)

MXCP supports OAuth authentication with Salesforce Cloud. This allows your MCP server to authenticate users and access Salesforce APIs on their behalf, enabling powerful integrations with CRM data, custom objects, and Salesforce automation.

#### Creating a Salesforce Connected App

Before configuring MXCP, you need to create a Connected App in your Salesforce org:

**Step 1: Access Setup**

1. Log in to your Salesforce org
2. Click the **Setup** gear icon in the top-right corner
3. In the Quick Find box, search for "App Manager"
4. Click **App Manager** under Apps

**Step 2: Create a Connected App**

1. Click **New Connected App**
2. Fill in the basic information:
   - **Connected App Name**: A descriptive name for your application
   - **API Name**: Will be auto-generated from the name
   - **Contact Email**: Your email address

**Step 3: Enable OAuth Settings**

1. Check **Enable OAuth Settings**
2. Set the **Callback URL** to match your MXCP server:
   - For local development: `http://localhost:8000/salesforce/callback`
   - For production: `https://your-domain.com/salesforce/callback`
3. Select OAuth Scopes (move from Available to Selected):
   - **Access the identity URL service (openid)**
   - **Access your basic information (profile)**
   - **Access and manage your data (api)**
   - **Access your contact information (email)**
   - **Perform requests on your behalf at any time (refresh_token, offline_access)**
4. Click **Save**

**Step 4: Configure Security Settings**

1. After saving, click **Continue**
2. In the API section, note down your **Consumer Key** and **Consumer Secret**
3. Configure additional security settings as needed:
   - **IP Restrictions**: Set to "Relax IP restrictions" for development
   - **Permitted Users**: Set to "All users may self-authorize" or restrict as needed

**Step 5: Deploy the Connected App**

1. Go back to **Setup** > **App Manager**
2. Find your Connected App and click the dropdown arrow
3. Select **Edit Policies**
4. Set **Permitted Users** as appropriate for your use case
5. Click **Save**

#### Environment Variables

Set these environment variables with your Salesforce Connected App credentials:

```bash
export SALESFORCE_CLIENT_ID="your_consumer_key_here"
export SALESFORCE_CLIENT_SECRET="your_consumer_secret_here"
```

#### MXCP Configuration

Configure Salesforce OAuth in your profile's auth section:

```yaml
projects:
  my_project:
    profiles:
      production:
        auth:
          provider: salesforce
          clients:
            - client_id: "${SALESFORCE_CLIENT_ID}"
              client_secret: "${SALESFORCE_CLIENT_SECRET}"
              name: "My MXCP Application"
              redirect_uris:
                - "https://your-domain.com/salesforce/callback"
              scopes:
                - "mxcp:access"
          salesforce:
            client_id: "${SALESFORCE_CLIENT_ID}"
            client_secret: "${SALESFORCE_CLIENT_SECRET}"
            scope: "api refresh_token openid profile email"
            callback_path: "/salesforce/callback"
            auth_url: "https://login.salesforce.com/services/oauth2/authorize"
            token_url: "https://login.salesforce.com/services/oauth2/token"
```

#### OAuth Scopes

Salesforce uses specific scopes to control access to different resources:

**Core Scopes:**
- `api` - Access to Salesforce APIs and data
- `refresh_token` - Enable refresh tokens for long-term access
- `openid` - OpenID Connect for user identification
- `profile` - Access to user profile information
- `email` - Access to user email address

**Additional Scopes:**
- `full` - Full access (equivalent to api scope)
- `web` - Web-based access to Salesforce
- `custom_permissions` - Access to custom permissions
- `lightning` - Access to Lightning Platform APIs
- `wave_api` - Access to Salesforce Analytics Cloud APIs

#### Sandbox vs Production

For development, you can use a Salesforce Sandbox:

```yaml
salesforce:
  client_id: "${SALESFORCE_SANDBOX_CLIENT_ID}"
  client_secret: "${SALESFORCE_SANDBOX_CLIENT_SECRET}"
  # Use sandbox URLs for development
  auth_url: "https://test.salesforce.com/services/oauth2/authorize"
  token_url: "https://test.salesforce.com/services/oauth2/token"
  scope: "api refresh_token openid profile email"
  callback_path: "/salesforce/callback"
```

#### Testing Your Configuration

1. Start your MXCP server:
   ```bash
   mxcp serve --debug
   ```

2. The authentication flow will begin when a client connects
3. Users will be redirected to Salesforce for authorization
4. After approval, they'll be redirected back to your callback URL
5. Check the logs for successful authentication

#### Troubleshooting

**Common Issues:**

1. **Invalid Client Configuration**:
   ```
   ValueError: Salesforce OAuth configuration is incomplete
   ```
   - Ensure `client_id` and `client_secret` are provided
   - Check that environment variables are set correctly

2. **Callback URL Mismatch**:
   ```
   HTTPException: Invalid state parameter
   ```
   - Verify the callback URL in your Connected App matches your MXCP configuration
   - Ensure the URL scheme (http/https) is correct

3. **Insufficient Permissions**:
   ```
   403 Forbidden
   ```
   - Check that your Connected App has the required OAuth scopes
   - Verify the user has access to the Salesforce org

4. **Sandbox vs Production Issues**:
   ```
   Authentication failed
   ```
   - Ensure you're using the correct login URL (`login.salesforce.com` vs `test.salesforce.com`)
   - Verify your Connected App is deployed in the correct environment

**Debug Tips:**

- Enable debug logging: `mxcp serve --debug`
- Check the Connected App deployment status in Salesforce Setup
- Verify OAuth scopes match your API requirements
- Test with minimal scopes like `openid profile` first

#### Security Best Practices

- **Store credentials securely**: Use environment variables, not config files
- **Use HTTPS**: Required for production OAuth flows
- **Minimal scopes**: Request only the permissions you need
- **IP restrictions**: Configure IP restrictions in your Connected App for production
- **User permissions**: Use Salesforce profiles and permission sets to control user access
- **Token management**: Implement proper refresh token handling
- **Org validation**: Verify users belong to the correct Salesforce org

#### Working with Salesforce Data

Once authenticated, you can use the user's Salesforce token to access their data:

```sql
-- Example: Query Salesforce accounts using the user's token
SELECT *
FROM read_json_auto(
    'https://your-instance.salesforce.com/services/data/v58.0/sobjects/Account',
    headers = MAP {
        'Authorization': 'Bearer ' || get_user_external_token(),
        'Content-Type': 'application/json'
    }
);
```

**Finding Your Salesforce Instance URL:**
The instance URL is provided in the OAuth token response and varies by org (e.g., `https://na1.salesforce.com`, `https://eu2.salesforce.com`).

### Keycloak

MXCP supports OAuth authentication with Keycloak, an open-source identity and access management solution. This allows your MCP server to authenticate users through Keycloak, enabling single sign-on across multiple applications and integration with various identity providers.

#### Creating a Keycloak Client

Before configuring MXCP, you need to create a client in your Keycloak realm:

**Step 1: Access Keycloak Admin Console**

1. Log in to your Keycloak Admin Console (typically at `http://your-keycloak-server:8080/admin`)
2. Select your realm (or create a new one if needed)

**Step 2: Create a New Client**

1. In the sidebar, click **Clients**
2. Click **Create client**
3. Configure the client:
   - **Client type**: OpenID Connect
   - **Client ID**: Choose a unique identifier (e.g., `mxcp-client`)
   - Click **Next**

**Step 3: Configure Client Settings**

1. **Client authentication**: Toggle **ON** (for confidential client)
2. **Authorization**: Can be left OFF unless you need fine-grained authorization
3. Enable the following in **Authentication flow**:
   - **Standard flow** (Authorization Code flow)
   - **Direct access grants** (optional, for testing)
4. Click **Next**

**Step 4: Configure Login Settings**

1. **Valid redirect URIs**: Add your MXCP callback URL
   - For local development: `http://localhost:8000/*`
   - For production: `https://your-domain.com/*`
2. **Valid post logout redirect URIs**: Same as redirect URIs
3. **Web origins**: Add `+` to allow all Valid Redirect URI origins
4. Click **Save**

**Step 5: Get Client Credentials**

1. Go to the **Credentials** tab
2. Copy the **Client secret** (you'll need this for MXCP configuration)

#### Environment Variables

Set these environment variables with your Keycloak credentials:

```bash
export KEYCLOAK_CLIENT_ID="mxcp-client"
export KEYCLOAK_CLIENT_SECRET="your-client-secret-here"
export KEYCLOAK_REALM="your-realm-name"
export KEYCLOAK_SERVER_URL="http://localhost:8080"  # Your Keycloak server URL
```

#### MXCP Configuration

Configure Keycloak OAuth in your profile's auth section:

```yaml
projects:
  my_project:
    profiles:
      dev:
        auth:
          provider: keycloak
          clients:
            - client_id: "${KEYCLOAK_CLIENT_ID}"
              client_secret: "${KEYCLOAK_CLIENT_SECRET}"
              name: "My MXCP Application"
              redirect_uris:
                - "http://localhost:8000/keycloak/callback"
              scopes:
                - "mxcp:access"
          keycloak:
            client_id: "${KEYCLOAK_CLIENT_ID}"
            client_secret: "${KEYCLOAK_CLIENT_SECRET}"
            realm: "${KEYCLOAK_REALM}"
            server_url: "${KEYCLOAK_SERVER_URL}"
            scope: "openid profile email"
            callback_path: "/keycloak/callback"
```

#### Configuration Options

- `client_id`: Your Keycloak client ID
- `client_secret`: Your Keycloak client secret
- `realm`: The Keycloak realm name where your client is configured
- `server_url`: Base URL of your Keycloak server (without `/auth` suffix)
- `scope`: OAuth scopes to request (default: "openid profile email")
- `callback_path`: Callback path for OAuth flow (default: "/keycloak/callback")

#### Advanced Keycloak Features

**Multiple Realms:**
You can use different realms for different environments:

```yaml
# Development realm
dev:
  auth:
    provider: keycloak
    keycloak:
      realm: "development"
      # ... other config

# Production realm
prod:
  auth:
    provider: keycloak
    keycloak:
      realm: "production"
      # ... other config
```

**Custom Scopes:**
Keycloak allows you to define custom scopes and map them to user attributes or roles:

```yaml
keycloak:
  scope: "openid profile email custom_scope"
```

**Identity Brokering:**
Keycloak can act as a broker for other identity providers (Google, SAML, etc.). Users authenticated through these providers will work seamlessly with MXCP.

#### Testing Your Configuration

1. Start your MXCP server:
   ```bash
   mxcp serve --debug
   ```

2. The authentication flow will begin when a client connects
3. Users will be redirected to Keycloak for authentication
4. After successful login, they'll be redirected back to your callback URL
5. Check the logs for successful authentication

#### Troubleshooting

**Common Issues:**

1. **Invalid Client Configuration**:
   ```
   ValueError: Keycloak OAuth configuration is incomplete
   ```
   - Ensure all required fields (`client_id`, `client_secret`, `realm`, `server_url`) are provided
   - Check that environment variables are set correctly

2. **Callback URL Mismatch**:
   ```
   HTTPException: Invalid state parameter
   ```
   - Verify the redirect URI in your Keycloak client matches your MXCP configuration
   - Ensure the URL scheme (http/https) is correct

3. **Realm Not Found**:
   ```
   404 Not Found
   ```
   - Check that the realm name in your configuration matches the Keycloak realm
   - Verify the server URL is correct (should not include `/auth` suffix)

4. **Invalid Client Credentials**:
   ```
   401 Unauthorized
   ```
   - Verify client ID and secret are correct
   - Ensure the client is enabled in Keycloak
   - Check that "Client authentication" is ON for confidential clients

**Debug Tips:**

- Enable debug logging: `mxcp serve --debug`
- Check Keycloak logs for authentication errors
- Use Keycloak's built-in account console to test user login
- Verify OAuth endpoints using `.well-known/openid-configuration`:
  ```
  curl http://localhost:8080/realms/your-realm/.well-known/openid-configuration
  ```

#### Security Best Practices

- **Store credentials securely**: Use environment variables, not config files
- **Use HTTPS**: Required for production OAuth flows
- **Realm isolation**: Use separate realms for different environments
- **Client access**: Configure client-specific roles and scopes
- **Session management**: Configure appropriate session timeouts in Keycloak
- **Token validation**: Enable token signature validation
- **Audit logging**: Enable Keycloak's event logging for security monitoring

#### Working with Keycloak Tokens

Once authenticated, you can use the user's Keycloak token to access protected resources:

```sql
-- Example: Use Keycloak token to access a protected API
SELECT *
FROM read_json_auto(
    'https://api.example.com/protected/resource',
    headers = MAP {
        'Authorization': 'Bearer ' || get_user_external_token(),
        'Content-Type': 'application/json'
    }
);
```

Keycloak tokens are JWTs that contain user claims and can be decoded to access user information directly.

### Google OAuth

MXCP supports OAuth authentication with Google, enabling access to Google Workspace APIs including Calendar, Drive, Gmail, and more. This allows your MCP server to authenticate users through their Google accounts and access Google services on their behalf.

#### Creating a Google OAuth App

Before configuring MXCP, you need to create OAuth 2.0 credentials in the Google Cloud Console:

**Step 1: Create a Google Cloud Project**

1. Go to the [Google Cloud Console](https://console.cloud.google.com)
2. Click **Select a project** → **New Project**
3. Enter a project name and click **Create**

**Step 2: Enable Required APIs**

1. In your project, go to **APIs & Services** → **Library**
2. Search for and enable the APIs you need:
   - **Google Calendar API** (for calendar access)
   - **Google Drive API** (for file access)
   - **Gmail API** (for email access)
   - Enable other APIs as needed

**Step 3: Configure OAuth Consent Screen**

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** for user type (or **Internal** for Google Workspace users)
3. Fill in the required information:
   - **App name**: Your application name
   - **User support email**: Your email address
   - **Developer contact information**: Your email address
4. Add scopes (click **Add or Remove Scopes**):
   - `.../auth/userinfo.email` (for email address)
   - `.../auth/userinfo.profile` (for basic profile)
   - `.../auth/calendar.readonly` (for calendar read access)
   - Add other scopes as needed
5. Add test users if in testing mode
6. Review and save

**Step 4: Create OAuth 2.0 Credentials**

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Select **Web application** as the application type
4. Configure the client:
   - **Name**: A descriptive name for your client
   - **Authorized redirect URIs**: Add your callback URLs
     - For local development: `http://localhost:8000/google/callback`
     - For production: `https://your-domain.com/google/callback`
5. Click **Create**
6. Save your **Client ID** and **Client Secret**

#### Environment Variables

Set these environment variables with your Google OAuth credentials:

```bash
export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="your-client-secret"
```

#### MXCP Configuration

Configure Google OAuth in your profile's auth section:

```yaml
projects:
  my_project:
    profiles:
      production:
        auth:
          provider: google
          clients:
            - client_id: "${GOOGLE_CLIENT_ID}"
              client_secret: "${GOOGLE_CLIENT_SECRET}"
              name: "My MXCP Application"
              redirect_uris:
                - "https://your-domain.com/google/callback"
              scopes:
                - "mxcp:access"
          google:
            client_id: "${GOOGLE_CLIENT_ID}"
            client_secret: "${GOOGLE_CLIENT_SECRET}"
            scope: "https://www.googleapis.com/auth/calendar.readonly openid profile email"
            callback_path: "/google/callback"
            auth_url: "https://accounts.google.com/o/oauth2/v2/auth"
            token_url: "https://oauth2.googleapis.com/token"
```

#### OAuth Scopes

Google uses fine-grained OAuth scopes to control access to different services:

**Core Identity Scopes:**
- `openid` - OpenID Connect authentication
- `profile` - Basic profile information
- `email` - Email address

**Google Calendar Scopes:**
- `https://www.googleapis.com/auth/calendar.readonly` - Read calendar events
- `https://www.googleapis.com/auth/calendar` - Full calendar access
- `https://www.googleapis.com/auth/calendar.events` - Manage calendar events

**Google Drive Scopes:**
- `https://www.googleapis.com/auth/drive.readonly` - Read-only access to files
- `https://www.googleapis.com/auth/drive.file` - Access to files created by the app
- `https://www.googleapis.com/auth/drive` - Full Drive access

**Gmail Scopes:**
- `https://www.googleapis.com/auth/gmail.readonly` - Read emails
- `https://www.googleapis.com/auth/gmail.send` - Send emails
- `https://www.googleapis.com/auth/gmail.modify` - Read and modify emails

Always request the minimum scopes needed for your application.

#### Testing Your Configuration

1. Start your MXCP server:
   ```bash
   mxcp serve --debug
   ```

2. The authentication flow will begin when a client connects
3. Users will be redirected to Google for authentication
4. Google will show a consent screen listing the requested permissions
5. After approval, they'll be redirected back to your callback URL
6. Check the logs for successful authentication

#### Troubleshooting

**Common Issues:**

1. **Invalid Client Configuration**:
   ```
   ValueError: Google OAuth configuration is incomplete
   ```
   - Ensure `client_id` and `client_secret` are provided
   - Check that environment variables are set correctly

2. **Redirect URI Mismatch**:
   ```
   Error 400: redirect_uri_mismatch
   ```
   - Verify the callback URL in Google Cloud Console matches your MXCP configuration
   - Ensure the URL scheme (http/https) and port are exact matches

3. **Insufficient Scopes**:
   ```
   403 Forbidden - Insufficient Permission
   ```
   - Check that you've enabled the required APIs in Google Cloud Console
   - Verify the requested scopes match the enabled APIs
   - Ensure the user has granted all requested permissions

4. **Application Not Verified**:
   ```
   This app isn't verified
   ```
   - For development, add test users in the OAuth consent screen
   - For production, submit your app for Google verification

**Debug Tips:**

- Enable debug logging: `mxcp serve --debug`
- Check the Google Cloud Console for API quotas and errors
- Use the [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground/) to test scopes
- Verify API enablement in your Google Cloud project

#### Security Best Practices

- **Store credentials securely**: Use environment variables, not config files
- **Use HTTPS**: Required for production OAuth flows
- **Minimal scopes**: Request only the permissions you need
- **Domain verification**: Verify your domain for production apps
- **Regular audits**: Review OAuth consent screen and app permissions
- **Token management**: Implement proper token refresh logic
- **Rate limiting**: Be aware of Google API quotas and implement appropriate rate limiting

#### Working with Google APIs

Once authenticated, you can use the user's Google token to access various Google services:

```sql
-- Example: List Google Calendar events
SELECT *
FROM read_json_auto(
    'https://www.googleapis.com/calendar/v3/calendars/primary/events',
    headers = MAP {
        'Authorization': 'Bearer ' || get_user_external_token(),
        'Content-Type': 'application/json'
    }
);

-- Example: Search Google Drive files
SELECT *
FROM read_json_auto(
    'https://www.googleapis.com/drive/v3/files?q=name+contains+''report''',
    headers = MAP {
        'Authorization': 'Bearer ' || get_user_external_token()
    }
);
```

**API Endpoints:**
- Calendar API: `https://www.googleapis.com/calendar/v3/`
- Drive API: `https://www.googleapis.com/drive/v3/`
- Gmail API: `https://www.googleapis.com/gmail/v1/`

For detailed API documentation, refer to [Google Workspace Developer Guides](https://developers.google.com/workspace).

## OAuth Client Registration

MXCP supports multiple ways for OAuth clients to register and authenticate:

### Pre-registered Clients (Recommended for Development)

You can pre-register OAuth clients in your configuration file. This is the most straightforward approach for development and testing:

```yaml
projects:
  my_project:
    profiles:
      dev:
        auth:
          provider: github
          
          # Pre-registered OAuth clients
          clients:
            # MCP CLI client (public client)
            - client_id: "aa27466a-fd71-4c2a-9ecf-8b5db5d34384"
              name: "MCP CLI Development Client"
              redirect_uris:
                - "http://127.0.0.1:49153/oauth/callback"
                - "http://localhost:49153/oauth/callback"
              scopes:
                - "mxcp:access"
            
            # Custom application (confidential client)
            - client_id: "my-custom-app-client-id"
              client_secret: "${MY_APP_CLIENT_SECRET}"
              name: "My Custom Application"
              redirect_uris:
                - "https://myapp.example.com/oauth/callback"
              grant_types:
                - "authorization_code"
                - "refresh_token"
              scopes:
                - "mxcp:access"
                - "mxcp:admin"
          
          github:
            # ... GitHub configuration
```

**Client Configuration Options:**
- `client_id` (required): Unique identifier for the client
- `name` (required): Human-readable name for the client
- `client_secret` (optional): Secret for confidential clients (omit for public clients)
- `redirect_uris` (optional): Allowed redirect URIs (defaults to MCP CLI callback)
- `grant_types` (optional): Allowed OAuth grant types (defaults to `["authorization_code"]`)
- `scopes` (optional): Allowed OAuth scopes (defaults to `["mxcp:access"]`)

### Dynamic Client Registration (RFC 7591)

MXCP implements RFC 7591 Dynamic Client Registration. Clients can register themselves at runtime by making a POST request to `/register`:

```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "My Application",
    "redirect_uris": ["https://myapp.example.com/oauth/callback"],
    "grant_types": ["authorization_code"],
    "scope": "mxcp:access"
  }'
```

The server will respond with client credentials:

```json
{
  "client_id": "generated-client-id",
  "client_secret": "generated-client-secret",
  "client_id_issued_at": 1640995200,
  "client_secret_expires_at": 0,
  "redirect_uris": ["https://myapp.example.com/oauth/callback"],
  "grant_types": ["authorization_code"],
  "scope": "mxcp:access"
}
```

### OAuth State Persistence

MXCP supports persistent storage of OAuth authentication state to maintain user sessions across server restarts. By default, OAuth state (access tokens, authorization codes, and dynamically registered clients) is stored in memory and lost when the server restarts.

### Configuration

Configure persistence in your user config file (`~/.mxcp/config.yml`):

```yaml
projects:
  my_project:
    profiles:
      production:
        auth:
          provider: github
          
          # OAuth state persistence configuration
          persistence:
            type: sqlite
            path: "/var/lib/mxcp/oauth.db"  # Optional, defaults to ~/.mxcp/oauth.db
          
          clients:
            - client_id: "${GITHUB_CLIENT_ID}"
              client_secret: "${GITHUB_CLIENT_SECRET}"
              name: "Production Application"
              redirect_uris:
                - "https://myapp.example.com/oauth/callback"
```

### Configuration Options

- **`type`**: Backend type for persistence. Currently only `"sqlite"` is supported.
- **`path`**: Path to the SQLite database file. Optional, defaults to `~/.mxcp/oauth.db`.

### What Gets Persisted

The persistence system stores:

1. **Access Tokens**: Internal MXCP tokens and their mappings to external provider tokens
2. **Authorization Codes**: Temporary codes during OAuth flows (with automatic expiration cleanup)
3. **Dynamically Registered Clients**: OAuth clients registered via RFC 7591 Dynamic Client Registration

**Note**: Pre-configured clients from your config file are **not** persisted, as they are loaded from configuration on each startup.

### Benefits

- **Session Continuity**: User sessions survive server restarts
- **Zero-Downtime Deployments**: Users don't need to re-authenticate during updates
- **Better User Experience**: No interruption of OAuth flows during server maintenance
- **Production Ready**: Supports scaling and disaster recovery scenarios

### Security Considerations

- The SQLite database contains sensitive OAuth tokens and should be protected with appropriate file permissions (600)
- Consider encrypting the database file at rest in production environments
- Implement regular cleanup of expired tokens (automatic cleanup happens during normal operations)
- Back up the database for disaster recovery, but ensure backups are also secured

### Example Production Setup

```yaml
# ~/.mxcp/config.yml
projects:
  my_project:
    profiles:
      production:
        auth:
          provider: github
          
          persistence:
            type: sqlite
            path: "/var/lib/mxcp/oauth.db"
          
          clients:
            - client_id: "${GITHUB_CLIENT_ID}"
              client_secret: "${GITHUB_CLIENT_SECRET}"
              name: "Production Application"
              redirect_uris:
                - "https://myapp.example.com/oauth/callback"
              scopes:
                - "mxcp:access"
          
          github:
            client_id: "${GITHUB_CLIENT_ID}"
            client_secret: "${GITHUB_CLIENT_SECRET}"
            scope: "user:email"
            # ... other GitHub config
```

## Production Recommendations

For production deployments:

1. **Enable persistence**: Always configure OAuth persistence for production
2. **Secure database**: Set appropriate file permissions (600) on the OAuth database
3. **Remove development clients**: Don't include test/development client IDs in production configs
4. **Use environment variables**: Store client secrets in environment variables, not config files
5. **Limit redirect URIs**: Only include production callback URLs
6. **Scope restrictions**: Use minimal required scopes
7. **HTTPS only**: Ensure all redirect URIs use HTTPS in production
8. **Monitor logs**: Watch for OAuth persistence errors in production logs

Example production configuration:

```yaml
projects:
  my_project:
    profiles:
      prod:
        auth:
          provider: github
          
          persistence:
            type: sqlite
            path: "/var/lib/mxcp/oauth.db"
          
          clients:
            - client_id: "${PROD_CLIENT_ID}"
              client_secret: "${PROD_CLIENT_SECRET}"
              name: "Production Application"
              redirect_uris:
                - "https://myapp.example.com/oauth/callback"
              scopes:
                - "mxcp:access"
          
          github:
            client_id: "${GITHUB_CLIENT_ID}"
            client_secret: "${GITHUB_CLIENT_SECRET}"
            # ... other GitHub config
```

## Authorization Configuration

MXCP supports configurable scope-based authorization to control access to your endpoints and tools. You can specify which OAuth scopes are required for accessing your server's resources.

### Required Scopes

Configure authorization requirements using the `authorization` section in your auth configuration:

```yaml
projects:
  my_project:
    profiles:
      dev:
        auth:
          provider: github
          
          # Authorization configuration
          authorization:
            required_scopes:
              - "mxcp:access"  # Require this scope for all endpoint access
              - "mxcp:admin"   # Also require admin scope
          
          clients:
            - client_id: "${CLIENT_ID}"
              # ... client config
```

**Configuration Options:**

- `required_scopes`: List of OAuth scopes that users must have to access protected endpoints
- If `required_scopes` is empty (`[]`), only authentication is required (no authorization)
- If omitted entirely, defaults to no authorization requirements

**Example Configurations:**

```yaml
# Authentication only (no scope requirements)
authorization:
  required_scopes: []

# Require basic access scope
authorization:
  required_scopes:
    - "mxcp:access"

# Require multiple scopes (user must have ALL listed scopes)
authorization:
  required_scopes:
    - "mxcp:access"
    - "mxcp:admin"
    - "mxcp:write"
```

When authorization is configured, all protected endpoints (tools, resources, prompts, SQL features) will verify that the authenticated user's token contains the required scopes before allowing access.

## User Token Access in SQL

When authentication is enabled, MXCP automatically creates several built-in SQL functions that allow your DuckDB queries to access information about the authenticated user and their tokens. This enables SQL queries to make authenticated API calls or access user-specific data.

### Available User Functions

The following functions are automatically available in all SQL queries when a user is authenticated:

```sql
-- Get the user's original OAuth provider token (e.g., GitHub token)
SELECT get_user_external_token() as external_token;

-- Get user information
SELECT get_username() as username;
SELECT get_user_provider() as provider;  -- 'github', 'atlassian', etc.
SELECT get_user_email() as email;
```

### Example Use Cases

**Making API calls from SQL using httpfs extension:**

```sql
-- Use the user's GitHub token to fetch their repositories
SELECT *
FROM read_json_auto(
    'https://api.github.com/user/repos',
    headers = MAP {
        'Authorization': 'Bearer ' || get_user_external_token(),
        'User-Agent': 'MXCP-' || get_username()
    }
);

-- Filter data based on the authenticated user
SELECT *
FROM my_data_table
WHERE owner = get_username();
```

**User-specific data filtering:**

```sql
-- Only show records owned by the current user
SELECT *
FROM user_documents
WHERE created_by = get_username();

-- Log user activity
INSERT INTO audit_log (user_id, action, timestamp)
VALUES (get_username(), 'data_query', NOW());
```

### Function Behavior

- **When authentication is disabled**: All functions return empty strings (`""`)
- **When user is not authenticated**: All functions return empty strings (`""`)
- **When user is authenticated**: Functions return the actual user data
- **Token security**: Tokens are only available within the SQL context and are not logged

These functions enable powerful user-aware SQL queries while maintaining security through the authentication layer.

## Security Considerations

- **Environment Variables**: Store sensitive credentials in environment variables, not in config files
- **HTTPS**: Use HTTPS in production environments
- **Scope Limitation**: Request only the minimum required OAuth scopes
- **Token Expiration**: Tokens have a default expiration of 1 hour

## General Troubleshooting

### Debug Logging

Enable debug logging to troubleshoot authentication issues:

```bash
mxcp serve --debug
```

### Common Patterns

Most authentication issues fall into these categories:

1. **Configuration Issues**: Missing or incorrect OAuth app settings
2. **Environment Variables**: Credentials not properly set
3. **URL Mismatches**: Callback URLs don't match between provider and MXCP
4. **Permission Issues**: Insufficient scopes or user permissions
5. **Network Issues**: Connectivity problems with OAuth providers

## Reverse Proxy Deployment

When deploying MXCP behind a reverse proxy (nginx, HAProxy, AWS ELB, etc.) that handles SSL/TLS termination, you need to configure the URL scheme properly for OAuth callbacks to work correctly.

### The Problem

OAuth providers require HTTPS callback URLs in production. When MXCP runs behind a reverse proxy with SSL termination:

1. **Client** → **HTTPS** → **Reverse Proxy** → **HTTP** → **MXCP**
2. MXCP sees only HTTP requests but needs to generate HTTPS callback URLs
3. Without proper configuration, OAuth flows fail with "CSRF detected" or "invalid callback URL" errors

### Solution Options

MXCP provides three ways to handle this:

#### Option 1: Explicit Scheme Configuration (Recommended)

Set the scheme explicitly in your transport configuration:

```yaml
transport:
  provider: streamable-http
  http:
    port: 8000
    host: "0.0.0.0"
    scheme: "https"  # Force HTTPS for all generated URLs
```

#### Option 2: Automatic Proxy Header Detection

Enable proxy header trust to automatically detect scheme from `X-Forwarded-Proto`:

```yaml
transport:
  provider: streamable-http
  http:
    port: 8000
    host: "0.0.0.0"
    trust_proxy: true  # Trust X-Forwarded-Proto and X-Forwarded-Scheme headers
```

Your reverse proxy must set the appropriate headers:

```nginx
# nginx configuration
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

#### Option 3: Complete Base URL Override

Specify the complete external URL:

```yaml
transport:
  provider: streamable-http
  http:
    base_url: "https://api.example.com"  # Complete external URL
```

### Example nginx Configuration

Here's a complete nginx configuration for SSL termination with MXCP:

```nginx
server {
    listen 80;
    server_name api.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;
    
    ssl_certificate /path/to/ssl/certificate.crt;
    ssl_certificate_key /path/to/ssl/private.key;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### OAuth Client Configuration

Update your OAuth client redirect URIs to use HTTPS:

```yaml
auth:
  provider: github
  clients:
    - client_id: "${PROD_CLIENT_ID}"
      client_secret: "${PROD_CLIENT_SECRET}"
      name: "Production Application"
      redirect_uris:
        - "https://api.example.com/github/callback"  # HTTPS callback
      scopes:
        - "mxcp:access"
```

### Troubleshooting

**"CSRF detected" errors**: Usually indicates scheme mismatch. Check that:
- Your transport configuration specifies `scheme: "https"` or `trust_proxy: true`
- Your reverse proxy sets `X-Forwarded-Proto: https` header
- OAuth client redirect URIs use HTTPS

**"Invalid callback URL" errors**: OAuth provider rejects the callback URL. Verify:
- Callback URLs in OAuth provider settings match your configuration
- URLs use HTTPS in production environments
- No port numbers in URLs when using standard ports (80/443)

## Adding New Providers

The authentication system is designed to be extensible. Future OAuth providers can be added by:

1. Implementing the `ExternalOAuthHandler` interface in a new provider file
2. Adding provider-specific configuration to the schema
3. Updating the `create_oauth_handler` factory function
4. Adding documentation following the same structure as existing providers

## See Also

- **[SQL Reference](../reference/sql.md)** - Quick reference for authentication SQL functions
- **[Policy Enforcement](../features/policies.md)** - Control access to endpoints based on user context
- **[Audit Logging](../features/auditing.md)** - Track authentication events and access attempts
- **[Testing with User Context](quality.md#testing-policy-protected-endpoints)** - Test authenticated endpoints
- **[Configuration Guide](configuration.md)** - Complete configuration reference
- **[Features Overview](../features/overview.md)** - Explore all MXCP capabilities

---

*Ready to secure your MXCP server? Start with the [Quickstart Guide](../getting-started/quickstart.md) and add authentication as needed.*
