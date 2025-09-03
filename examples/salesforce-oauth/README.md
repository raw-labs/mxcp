# Salesforce OAuth Demo

This example demonstrates how to create MCP tools that interact with Salesforce using the MXCP OAuth authentication system with the `simple_salesforce` library.

## Features Demonstrated

### 1. MXCP OAuth Authentication
- Project-wide Salesforce OAuth configuration
- Automatic token management through MXCP authentication system
- User authentication via standard OAuth 2.0 flow
- Error handling for authentication failures

### 2. Salesforce API Integration
- `list_sobjects` - Retrieve all available Salesforce objects (sObjects) from your org with optional filtering
- `describe_sobject` - Get detailed metadata for a specific Salesforce object, including field information
- `get_sobject` - Retrieve a specific Salesforce record by its ID
- `search` - Search across all searchable Salesforce objects using simple search terms
- `soql` - Execute SOQL (Salesforce Object Query Language) queries
- `sosl` - Execute SOSL (Salesforce Object Search Language) queries for complex searches
- `whoami` - Display information about the current authenticated Salesforce user
- Token-based API access using authenticated user context

## Prerequisites

1. **Salesforce Org**: You need access to a Salesforce org (Developer Edition is fine)
2. **Salesforce Connected App**: Create a Connected App in Salesforce with OAuth settings
3. **Python Dependencies**: The `simple_salesforce` library (automatically managed by MXCP)

## Setup

### 1. Create Salesforce Connected App

1. Log into your Salesforce org
2. Go to **Setup** → **App Manager** → **New Connected App**
3. Fill in basic information:
   - **Connected App Name**: "MXCP Integration" (or your preferred name)
   - **API Name**: Will auto-populate
   - **Contact Email**: Your email
4. Enable OAuth Settings:
   - **Enable OAuth Settings**: Check this box
   - **Callback URL**: This depends on your deployment:
     - **Local Development**: `http://localhost:8000/salesforce/callback`
     - **Remote/Production**: `https://your-domain.com/salesforce/callback` (replace with your actual server URL)
   - **Selected OAuth Scopes**: Add these scopes:
     - Access and manage your data (api)
     - Perform requests on your behalf at any time (refresh_token, offline_access)
     - Access your basic information (id, profile, email, address, phone)
5. Save the Connected App
6. Note down the **Consumer Key** (Client ID) and **Consumer Secret** (Client Secret)

### 2. Configure Environment Variables

Set your Salesforce OAuth credentials:
```bash
export SALESFORCE_CLIENT_ID="your-consumer-key-from-connected-app"
export SALESFORCE_CLIENT_SECRET="your-consumer-secret-from-connected-app"
```

### 3. Configure Callback URL for Your Deployment

The callback URL configuration depends on where your MXCP server will run:

#### Local Development
For local development, the default configuration in `config.yml` uses `http://localhost:8000/salesforce/callback`. This works when:
- You're running MXCP locally on your development machine
- Users authenticate from the same machine where MXCP is running

#### Remote/Production Deployment
For remote servers or production deployments, you need to:

1. **Update config.yml**: Uncomment and modify the production callback URL:
   ```yaml
   redirect_uris:
     - "http://localhost:8000/salesforce/callback"  # Keep for local dev
     - "https://your-domain.com/salesforce/callback"  # Add your actual URL
   ```

2. **Update base_url**: Set the correct base URL in your config:
   ```yaml
   transport:
     http:
       base_url: https://your-domain.com  # Your actual server URL
   ```

3. **Configure Connected App**: Add the production callback URL to your Salesforce Connected App's callback URLs

**Important**: 
- The callback URL must be accessible from the user's browser, not just from your server
- For production deployments, Salesforce requires HTTPS for callback URLs
- You can configure multiple callback URLs in your Connected App to support both local development and production

## Authenticate with Salesforce

When you first run MXCP, you'll need to authenticate with Salesforce:

```bash
# Start the MXCP server with the config file - this will prompt for authentication
MXCP_CONFIG=config.yml mxcp serve
```

The authentication flow will:
1. Open your browser to Salesforce login
2. You'll log in with your Salesforce credentials
3. Authorize the MXCP application
4. Redirect back to complete authentication


## Project Structure

```
salesforce-oauth/
├── mxcp-site.yml              # Project metadata
├── config.yml                 # Server and authentication configuration
├── python/                    # Python modules
│   └── salesforce_client.py   # Salesforce API implementations
├── tools/                     # Tool definitions
│   ├── list_sobjects.yml      # List all Salesforce objects
│   ├── describe_sobject.yml   # Get object metadata
│   ├── get_sobject.yml        # Get record by ID
│   ├── search.yml             # Search across objects
│   ├── soql.yml               # Execute SOQL queries
│   ├── sosl.yml               # Execute SOSL queries
│   └── whoami.yml             # Current user information
└── README.md                  # This file
```

## Key Concepts

1. **MXCP OAuth Integration**: Uses MXCP's built-in Salesforce OAuth provider for secure authentication
2. **User Context**: Access tokens are automatically managed and provided through `user_context()`
3. **Token-based Authentication**: simple_salesforce is initialized with OAuth tokens instead of credentials
4. **Project-wide Configuration**: Authentication is configured at the project level in `mxcp-site.yml`
5. **Error Handling**: Comprehensive error handling for authentication and API failures
6. **API Integration**: Demonstrates calling Salesforce REST API endpoints with proper OAuth tokens

## Example Output

When you run `list_sobjects`, you'll get a response like:

```json
[
  "Account",
  "Contact", 
  "Lead",
  "Opportunity",
  "Case",
  "Product2",
  "Task",
  "Event",
  "User",
  "CustomObject__c",
  ...
]
```

## Troubleshooting

### Authentication Errors
- **"No user context available"**: User needs to authenticate first by running `mxcp serve` and completing OAuth flow
- **"No Salesforce access token found"**: Authentication was incomplete or token expired - re-authenticate
- **Connected App Issues**: Verify your `SALESFORCE_CLIENT_ID` and `SALESFORCE_CLIENT_SECRET` are correct
- **Callback URL Mismatch**: Ensure the callback URL in your Connected App matches where your MXCP server is accessible:
  - Local development: `http://localhost:8000/salesforce/callback`
  - Remote/production: `https://your-domain.com/salesforce/callback`
- **OAuth Scopes**: Verify your Connected App has the required OAuth scopes (api, refresh_token, id, profile, email)

### API Errors
- Verify you have the necessary permissions in Salesforce
- Check that your org is accessible and not in maintenance mode
- Ensure your Connected App is approved and not restricted by IP ranges

### Connected App Setup Issues
- **App Not Found**: Make sure your Connected App is saved and the Consumer Key/Secret are copied correctly
- **Callback URL**: The callback URL must exactly match your MXCP server's accessible address:
  - For local development: `http://localhost:8000/salesforce/callback`
  - For remote deployment: `https://your-domain.com/salesforce/callback`
- **OAuth Scopes**: Missing scopes will cause authentication to fail - ensure all required scopes are selected

## Next Steps

This example demonstrates a comprehensive set of Salesforce integration tools. You could extend it with additional tools for data manipulation like:
- `create_record` - Create new records in Salesforce objects
- `update_record` - Update existing records
- `delete_record` - Delete records
- `bulk_operations` - Handle bulk data operations for large datasets 