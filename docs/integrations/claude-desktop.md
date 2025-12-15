---
title: "Claude Desktop"
description: "Connect MXCP to Claude Desktop with native MCP support. Configuration, virtual environments, and troubleshooting."
sidebar:
  order: 2
---

> **Related Topics:** [Quickstart](/getting-started/quickstart#connect-to-claude-desktop) (first connection) | [Deployment](/operations/deployment) (production setup) | [Common Tasks](/reference/common-tasks#how-do-i-connect-to-claude-desktop) (quick how-to)

Claude Desktop has native Model Context Protocol (MCP) support, making it the easiest way to connect your MXCP endpoints to an AI assistant.

## Configuration

### Find the Config File

Claude Desktop's configuration is stored in:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Basic Configuration

Add your MXCP server to the configuration file:

```json
{
  "mcpServers": {
    "my-project": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/absolute/path/to/your/project"
    }
  }
}
```

**Important**: Use absolute paths for `cwd`. Relative paths will fail.

### Virtual Environment

If MXCP is installed in a virtual environment:

```json
{
  "mcpServers": {
    "my-project": {
      "command": "bash",
      "args": [
        "-c",
        "cd /path/to/project && source /path/to/.venv/bin/activate && mxcp serve --transport stdio"
      ]
    }
  }
}
```

Or use the full path to the Python executable:

```json
{
  "mcpServers": {
    "my-project": {
      "command": "/path/to/.venv/bin/mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/path/to/project"
    }
  }
}
```

### Multiple Servers

Connect multiple MXCP projects:

```json
{
  "mcpServers": {
    "analytics": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/path/to/analytics-project"
    },
    "customer-support": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/path/to/support-project"
    },
    "inventory": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/path/to/inventory-project"
    }
  }
}
```

### Environment Variables

Pass environment variables to the server:

```json
{
  "mcpServers": {
    "my-project": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/path/to/project",
      "env": {
        "MXCP_PROFILE": "production",
        "DATABASE_URL": "postgresql://localhost/mydb"
      }
    }
  }
}
```

## Activation

After modifying the configuration:

1. **Save** the configuration file
2. **Restart Claude Desktop** completely (quit and reopen)
3. **Verify** connection in Claude Desktop

You should see your tools available in Claude's interface.

## Usage

### Tool Discovery

Claude automatically discovers your MXCP tools. Ask Claude:

> "What tools do you have access to?"

Claude will list all available tools from your MXCP server.

### Calling Tools

Simply ask Claude to use your tools naturally:

> "Can you find the user with ID 123?"

Claude will call the appropriate tool and return results.

### Resource Access

Access MXCP resources:

> "Show me the user profile for alice@example.com"

### Using Prompts

Invoke MXCP prompts:

> "Use the customer-analysis prompt to analyze this data"

## Configuration Options

### Transport Options

```json
{
  "mcpServers": {
    "my-project": {
      "command": "mxcp",
      "args": [
        "serve",
        "--transport", "stdio",
        "--log-level", "INFO"
      ],
      "cwd": "/path/to/project"
    }
  }
}
```

### Debug Mode

Enable verbose logging:

```json
{
  "mcpServers": {
    "my-project": {
      "command": "mxcp",
      "args": [
        "serve",
        "--transport", "stdio",
        "--log-level", "DEBUG"
      ],
      "cwd": "/path/to/project"
    }
  }
}
```

### Profile Selection

Use a specific MXCP profile:

```json
{
  "mcpServers": {
    "my-project": {
      "command": "mxcp",
      "args": [
        "serve",
        "--transport", "stdio",
        "--profile", "production"
      ],
      "cwd": "/path/to/project"
    }
  }
}
```

## Troubleshooting

### Server Not Connecting

**Symptoms**: Claude doesn't show your tools

**Check**:
1. Configuration file syntax is valid JSON
2. Paths are absolute and correct
3. MXCP is installed and in PATH
4. Project has valid `mxcp-site.yml`

**Test manually**:
```bash
cd /path/to/project
mxcp serve --transport stdio
```

Type `{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}` and press Enter.

### Tool Calls Failing

**Symptoms**: Claude reports errors when using tools

**Check**:
1. Run `mxcp validate` in your project
2. Run `mxcp test` to verify functionality
3. Check Claude's developer console for errors

### Permission Errors

**Symptoms**: "Permission denied" or similar errors

**Check**:
1. Virtual environment activation
2. File permissions on project directory
3. Database connection permissions

### Slow Response Times

**Symptoms**: Tools take long to respond

**Optimize**:
1. Check database query performance
2. Enable caching where appropriate
3. Use materialized views for complex queries

### Developer Console

Access Claude Desktop's developer console:

1. **macOS**: `Cmd + Option + I`
2. **Windows/Linux**: `Ctrl + Shift + I`

Look for:
- Connection errors
- Request/response timing
- Error messages

## Best Practices

### 1. Use Descriptive Server Names

```json
{
  "mcpServers": {
    "sales-analytics": { ... },
    "customer-support-tools": { ... }
  }
}
```

### 2. Test Before Connecting

Always verify your MXCP project works:

```bash
cd /path/to/project
mxcp validate
mxcp test
mxcp serve --transport stdio
```

### 3. Start Simple

Begin with a single tool to verify the connection:

```yaml
# tools/hello.yml
mxcp: 1
tool:
  name: hello
  description: Test tool that says hello
  return:
    type: string
  source:
    code: "SELECT 'Hello from MXCP!'"
```

### 4. Monitor Logs

Keep an eye on logs during development:

```json
{
  "mcpServers": {
    "my-project": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio", "--log-level", "INFO"],
      "cwd": "/path/to/project"
    }
  }
}
```

### 5. Use Profiles for Environments

```json
{
  "mcpServers": {
    "dev-server": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio", "--profile", "dev"],
      "cwd": "/path/to/project"
    },
    "prod-server": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio", "--profile", "prod"],
      "cwd": "/path/to/project"
    }
  }
}
```

## Example Configuration

Complete example with multiple projects:

```json
{
  "mcpServers": {
    "sales-data": {
      "command": "/home/user/.venv/bin/mxcp",
      "args": [
        "serve",
        "--transport", "stdio",
        "--profile", "production",
        "--log-level", "INFO"
      ],
      "cwd": "/home/user/projects/sales-mcp",
      "env": {
        "WAREHOUSE_HOST": "analytics.company.com"
      }
    },
    "support-tools": {
      "command": "mxcp",
      "args": ["serve", "--transport", "stdio"],
      "cwd": "/home/user/projects/support-mcp"
    }
  }
}
```

## Next Steps

- [dbt Integration](/integrations/dbt) - Data transformation
- [DuckDB Integration](/integrations/duckdb) - SQL engine
- [Operations](/operations) - Production deployment
