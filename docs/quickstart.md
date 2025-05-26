# MXCP Quickstart Guide

This guide will help you get started with MXCP quickly. We'll cover both creating a new project from scratch and exploring existing examples.

## Installation

First, install MXCP:

```bash
pip install mxcp
```

## Option 1: Create a New Project

### 1. Initialize a Project

Create a new project with a hello world example:

```bash
# Create a new directory and initialize MXCP
mkdir my-mxcp-project
cd my-mxcp-project
mxcp init --bootstrap
```

This creates:
- `mxcp-site.yml` - Project configuration
- `endpoints/hello-world.yml` - A simple hello world tool
- `endpoints/hello-world.sql` - The SQL implementation

### 2. Explore the Generated Files

The bootstrap creates a simple hello world tool:

```yaml
# endpoints/hello-world.yml
mxcp: "1.0.0"
tool:
  name: "hello_world"
  description: "A simple hello world tool"
  enabled: true
  parameters:
    - name: "name"
      type: "string"
      description: "Name to greet"
      examples: ["World"]
  return:
    type: "string"
    description: "Greeting message"
  source:
    file: "hello-world.sql"
```

```sql
-- endpoints/hello-world.sql
SELECT 'Hello, ' || $name || '!' as greeting
```

### 3. Start the MCP Server

Run the MCP server to expose your endpoints:

```bash
mxcp serve
```

The server starts in stdio mode by default, ready to be integrated with MCP-compatible tools. You can test your endpoint using:

#### Option A: Claude Desktop Integration

1. Create a `server_config.json` file:
```json
{
  "mcpServers": {
    "local": {
      "command": "bash",
      "args": [
        "-c",
        "cd ~/my-mxcp-project && source ../../.venv/bin/activate && mxcp serve --transport stdio"
      ],
      "env": {
        "PATH": "/your/path/to/.venv/bin:/usr/local/bin:/usr/bin",
        "HOME": "/your/home"
      }
    }
  }
}
```

2. Configure Claude Desktop to use this server config
3. Ask Claude to use your hello world tool:
   ```
   User: Can you greet me with the hello_world tool?
   Claude: I'll use the hello_world tool to greet you.
   [Tool Call: hello_world]
   Parameters: {"name": "User"}
   Result: "Hello, User!"
   ```

#### Option B: mcp-cli Integration

1. Install mcp-cli:
```bash
pip install mcp-cli
```

2. Create a `server_config.json` file:
```json
{
  "mcpServers": {
    "local": {
      "command": "bash",
      "args": [
        "-c",
        "cd ~/my-mxcp-project && source ../../.venv/bin/activate && mxcp serve --transport stdio"
      ],
      "env": {
        "PATH": "/your/path/to/.venv/bin:/usr/local/bin:/usr/bin",
        "HOME": "/your/home"
      }
    }
  }
}
```

3. Use mcp-cli to interact with your endpoint:
```bash
mcp-cli tools call hello_world --name "World"
```

## Option 2: Try an Example

MXCP comes with several example projects that demonstrate different features:

### Earthquakes Example

This example shows how to:
- Query real-time earthquake data
- Transform JSON data with SQL
- Create type-safe endpoints

```bash
cd examples/earthquakes
mxcp serve
```


## Next Steps

Now that you have MXCP running, here are some next steps:

1. **Explore the CLI**
   ```bash
   mxcp list         # List all endpoints
   mxcp validate     # Check your endpoints
   mxcp test         # Run endpoint tests
   ```

2. **Learn More**
   - [Type System](type-system.md) - Understand MXCP's type system
   - [Configuration](configuration.md) - Configure your project
   - [Integrations](integrations.md) - Connect with dbt and DuckDB

3. **Create Your Own Endpoints**
   - Start with simple SQL queries
   - Add type definitions
   - Test your endpoints
   - Iterate and improve

## Common Patterns

### 1. Reading Data

```sql
-- Read from a CSV file
SELECT * FROM read_csv('data/*.csv');

-- Read from a JSON API
SELECT * FROM read_json_auto('https://api.example.com/data');
```

### 2. Transforming Data

```sql
-- Aggregate data
SELECT 
  date,
  COUNT(*) as count,
  AVG(value) as average
FROM data
GROUP BY date;

-- Join multiple sources
SELECT 
  a.id,
  b.name,
  c.value
FROM source_a a
JOIN source_b b ON a.id = b.id
JOIN source_c c ON a.id = c.id;
```

### 3. Type-Safe Parameters

```yaml
parameters:
  - name: "date"
    type: "date"
    description: "Date to filter by"
  - name: "threshold"
    type: "number"
    description: "Minimum value"
```

## Need Help?

- Check the [CLI Reference](cli.md) for all available commands
- Join our community for support
- Report issues on GitHub

Remember: MXCP is designed to be simple but powerful. Start small, experiment, and gradually build more complex solutions. 