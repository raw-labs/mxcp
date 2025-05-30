# MXCP Confluence Plugin Example

This example demonstrates how to use the MXCP Confluence plugin to interact with Confluence.

## Overview

The plugin provides several UDFs that allow you to:
- Search pages using keywords
- Fetch page content
- List child pages
- List spaces
- Get page metadata

## Configuration

### 1. User Configuration

Add the following to your MXCP user config (`~/.mxcp/config.yml`). You can use the example `config.yml` in this directory as a template:

```yaml
mxcp: 1.0.0

projects:
  confluence-demo:
    profiles:
      dev:
        plugin:
          config:
            confluence:
              url: "https://your-domain.atlassian.net/wiki"
              username: "your-email@example.com"
              password: "your-api-token"
```

### 2. Site Configuration

Create an `mxcp-site.yml` file:

```yaml
mxcp: 1.0.0
project: confluence-demo
profile: dev
plugin:
  - name: confluence
    module: mxcp_plugin_confluence
    config: confluence
```

## Available Tools

### Search Pages
```sql
-- Search for pages containing specific text
SELECT search_pages_confluence($query, $limit) as result;
```

### Get Page
```sql
-- Fetch a page's content
SELECT get_page_confluence($page_id) as result;
```

### Get Children
```sql
-- List direct children of a page
SELECT get_children_confluence($page_id) as result;
```

### List Spaces
```sql
-- List all accessible spaces
SELECT list_spaces_confluence() as result;
```

### Describe Page
```sql
-- Show metadata about a page
SELECT describe_page_confluence($page_id) as result;
```

## Running the Example

1. Set the `MXCP_CONFIG` environment variable to point to your config file:
   ```bash
   export MXCP_CONFIG=/path/to/examples/confluence/config.yml
   ```

2. Start the MXCP server:
   ```bash
   mxcp serve
   ```

## Notes

- Make sure to keep your API token secure and never commit it to version control.
- The plugin requires proper authentication and API permissions to work with your Confluence instance.
- All functions return JSON strings containing the requested data. 