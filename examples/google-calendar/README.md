# Google Calendar OAuth Demo (Read-Only)

This example demonstrates how to create safe, read-only MCP tools that interact with Google Calendar using the MXCP OAuth authentication system with the Google Calendar API.

## Features Demonstrated

### 1. MXCP OAuth Authentication
- Project-wide Google OAuth configuration
- Automatic token management through MXCP authentication system
- User authentication via standard OAuth 2.0 flow
- Error handling for authentication failures

### 2. Google Calendar API Integration (Read-Only)
- `whoami` - Display information about the current authenticated Google user
- `list_calendars` - Retrieve all accessible calendars with filtering options
- `get_calendar` - Get detailed information for a specific calendar
- `list_events` - List events from a calendar with time filtering and pagination
- `get_event` - Retrieve detailed information for a specific event
- `search_events` - Search for events matching text queries
- `get_freebusy` - Check availability across multiple calendars
- Token-based API access using authenticated user context
- **Safe Design**: Only read operations - no calendar or event modifications

## Prerequisites

1. **Google Account**: You need a Google account with Calendar access
2. **Google Cloud Project**: Create a project in Google Cloud Console with Calendar API enabled
3. **OAuth Credentials**: Create OAuth 2.0 credentials for your application
4. **Python Dependencies**: The `google-api-python-client` and related libraries (automatically managed by MXCP)

## Setup

### 1. Create Google Cloud Project and Enable APIs

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Calendar API:
   - Go to **APIs & Services** → **Library**
   - Search for "Google Calendar API"
   - Click on it and press **Enable**

### 2. Configure OAuth Consent Screen (Required First)

1. In Google Cloud Console, go to **APIs & Services** → **OAuth consent screen**
2. Configure the consent screen:
   - **User Type**: External (for testing) or Internal (for organization use)
   - **App Name**: "MXCP Google Calendar Integration" (or your preferred name)
   - **User Support Email**: Your email
   - **Developer Contact**: Your email
3. **Add Scopes** (under "Data access" section): 
   - Click "Add or Remove Scopes" 
   - In the scope selection dialog, search for "calendar"
   - Find and select `https://www.googleapis.com/auth/calendar.readonly` (Calendar read-only access)
   - Click "Update" to save the scopes
4. Save the consent screen configuration

**Note**: The scopes are configured in the OAuth Consent Screen, not when creating the Client ID. This is why you don't see scope options when creating credentials.

### 3. Create OAuth 2.0 Client ID

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth 2.0 Client IDs**
3. Configure the client:
   - **Application Type**: Web application
   - **Name**: "MXCP Calendar Client" (or your preferred name)
   - **Authorized Redirect URIs**: Add based on your deployment:
     - **Local Development**: `http://localhost:8000/google/callback`
     - **Remote/Production**: `https://your-domain.com/google/callback` (replace with your actual server URL)
4. Save and note down the **Client ID** and **Client Secret**

### 4. Configure Environment Variables

Set your Google OAuth credentials:
```bash
export GOOGLE_CLIENT_ID="your-client-id-from-google-cloud"
export GOOGLE_CLIENT_SECRET="your-client-secret-from-google-cloud"
```

### 5. Configure Callback URL for Your Deployment

The callback URL configuration depends on where your MXCP server will run:

#### Local Development
For local development, the default configuration in `config.yml` uses `http://localhost:8000/google/callback`. This works when:
- You're running MXCP locally on your development machine
- Users authenticate from the same machine where MXCP is running

#### Remote/Production Deployment
For remote servers or production deployments, you need to:

1. **Update config.yml**: Modify the callback URL:
   ```yaml
   redirect_uris:
     - "https://your-domain.com/google/callback"  # Your actual URL
   ```

2. **Update base_url**: Set the correct base URL in your config:
   ```yaml
   transport:
     http:
       base_url: https://your-domain.com  # Your actual server URL
   ```

3. **Configure OAuth Credentials**: Add the production callback URL to your Google Cloud OAuth credentials

**Important**: 
- The callback URL must be accessible from the user's browser, not just from your server
- For production deployments, Google requires HTTPS for callback URLs
- You can configure multiple callback URLs in your OAuth credentials to support both local development and production

## Running the Examples

### 1. Authenticate with Google

When you first run MXCP, you'll need to authenticate with Google:

```bash
# Start the MXCP server with the config file - this will prompt for authentication
mxcp serve --config config.yml
```

The authentication flow will:
1. Open your browser to Google's OAuth consent screen
2. You'll log in with your Google credentials
3. Grant permission for read-only calendar access
4. Redirect back to complete authentication

### 2. Test the Tools

Once authenticated, you can test the tools:

```bash
# Get information about the authenticated user
mxcp run tool whoami --config config.yml

# List all your calendars
mxcp run tool list_calendars --config config.yml

# List events from your primary calendar for today
mxcp run tool list_events --config config.yml \
  --time_min "2024-01-15T00:00:00Z" \
  --time_max "2024-01-15T23:59:59Z"

# Search for meetings with a specific person
mxcp run tool search_events --config config.yml \
  --q "John Smith"

# Check your availability for tomorrow
mxcp run tool get_freebusy --config config.yml \
  --calendar_ids '["primary"]' \
  --time_min "2024-01-16T09:00:00Z" \
  --time_max "2024-01-16T17:00:00Z"
```

### 3. Use with MCP Clients

```bash
# Start the MXCP server for use with MCP clients like Claude Desktop
mxcp serve --config config.yml
```

## Project Structure

```
google-calendar/
├── mxcp-site.yml              # Project metadata
├── config.yml                 # Server and authentication configuration
├── python/                    # Python modules
│   └── google_calendar_client.py  # Google Calendar API implementations
├── tools/                     # Tool definitions (read-only)
│   ├── whoami.yml             # Current user information
│   ├── list_calendars.yml     # List accessible calendars
│   ├── get_calendar.yml       # Get calendar details
│   ├── list_events.yml        # List calendar events
│   ├── get_event.yml          # Get event details
│   ├── search_events.yml      # Search for events
│   └── get_freebusy.yml       # Check availability
└── README.md                  # This file
```

## Key Concepts

1. **MXCP OAuth Integration**: Uses MXCP's built-in Google OAuth provider for secure authentication
2. **User Context**: Access tokens are automatically managed and provided through `get_user_context()`
3. **Token-based Authentication**: Google API client is initialized with OAuth tokens instead of service account credentials
4. **Project-wide Configuration**: Authentication is configured at the project level in `config.yml`
5. **Error Handling**: Comprehensive error handling for authentication and API failures
6. **Type Safety**: Uses Python type hints and comprehensive error handling for data validation

## Example Usage

When you use the tools through an MCP client, you can:

### Get User Information
```
Use the whoami tool to see your Google profile information
```

### Manage Calendars
```
List all your calendars, get details for specific calendars, and check which ones you can modify
```

### View Calendar Events
```
- List events: "What's on my calendar this week?"
- Search events: "Find all meetings with John"
- Get event details: "Show me details for my 3 PM meeting"
- View event information: "What meetings do I have with the marketing team?"
```

### Check Availability
```
Use the freebusy tool to find available time slots across multiple calendars
```

## Troubleshooting

### Authentication Errors
- **"No user context available"**: User needs to authenticate first by running `mxcp serve` and completing OAuth flow
- **"No Google access token found"**: Authentication was incomplete or token expired - re-authenticate
- **OAuth Credentials Issues**: Verify your `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are correct
- **Callback URL Mismatch**: Ensure the callback URL in your Google Cloud OAuth credentials matches where your MXCP server is accessible
- **API Not Enabled**: Make sure the Google Calendar API is enabled in your Google Cloud project

### API Errors
- **403 Forbidden**: Check that the Calendar API is enabled and your OAuth scopes include calendar access
- **404 Not Found**: Verify calendar IDs and event IDs are correct and accessible to the authenticated user
- **Rate Limiting**: Google Calendar API has rate limits - implement appropriate retry logic if needed

### OAuth Setup Issues
- **Consent Screen**: Make sure your OAuth consent screen is properly configured with the correct scopes
- **Redirect URI**: The redirect URI must exactly match your MXCP server's accessible address
- **Scopes**: Ensure your OAuth configuration includes `https://www.googleapis.com/auth/calendar.readonly` scope

## Next Steps

This example demonstrates a comprehensive set of read-only Google Calendar integration tools. You could extend it with additional features like:
- Advanced calendar filtering and search capabilities
- Integration with other Google Workspace services (read-only)
- Calendar analytics and reporting
- Event pattern analysis and insights
- Multi-calendar comparison and availability analysis

**Note**: This example is intentionally read-only for safety. If you need write operations (create, update, delete), you would need to:
- Change the OAuth scope to `https://www.googleapis.com/auth/calendar` (full access)
- Add appropriate write functions with proper validation and error handling
- Implement additional safety measures and user confirmations