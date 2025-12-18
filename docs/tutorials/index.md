---
title: "Tutorials"
description: "Hands-on MXCP tutorials: Hello World in 5 minutes, SQL data queries, Python with async and ML, combining SQL+Python. Copy-paste code included."
sidebar:
  order: 1
---

> **Related Topics:** [Quickstart](/getting-started/quickstart) (project setup) | [Concepts](/concepts/) (understand MXCP) | [Common Tasks](/reference/common-tasks) (quick how-to)

This section contains step-by-step tutorials to help you build MXCP endpoints. Each tutorial focuses on a specific skill and builds on the concepts from the quickstart guide.

## Getting Started Tutorials

### [Hello World](/tutorials/hello-world)
Your first MXCP tool. Learn the basics of:
- Creating a tool definition
- Writing SQL implementation
- Running and testing tools

### [SQL Endpoints](/tutorials/sql-endpoints)
Build data query tools with SQL:
- Parameter binding
- Complex queries with joins
- Aggregations and grouping
- Working with DuckDB features

### [Python Endpoints](/tutorials/python-endpoints)
Build complex logic with Python:
- Accessing the runtime API
- Database operations from Python
- Async operations
- Lifecycle hooks

## Prerequisites

Before starting these tutorials, ensure you have:

1. **MXCP installed**
   ```bash
   pip install mxcp
   ```

2. **A project initialized**
   ```bash
   mkdir tutorials
   cd tutorials
   mxcp init --bootstrap
   ```

3. **Basic understanding of**:
   - YAML syntax
   - SQL (for SQL tutorials)
   - Python (for Python tutorials)

## Tutorial Format

Each tutorial follows a consistent format:

1. **Goal** - What you'll build
2. **Prerequisites** - What you need
3. **Steps** - Detailed instructions
4. **Verification** - How to test your work
5. **Next Steps** - Where to go from here

All code examples are tested and working. You can copy-paste them directly into your project.

## Recommended Order

If you're new to MXCP, follow this learning path:

1. **[Hello World](/tutorials/hello-world)** - Understand the basics
2. **[SQL Endpoints](/tutorials/sql-endpoints)** - Master data queries
3. **[Python Endpoints](/tutorials/python-endpoints)** - Build complex logic

After completing these tutorials, explore:
- [Security section](/security/) - Add authentication and policies
- [Quality section](/quality/) - Test and validate your endpoints
- [Operations section](/operations/) - Deploy to production

## Quick Reference

### Running Tools

```bash
# Run with parameters
mxcp run tool tool_name --param key=value

# Run with complex values from JSON file
mxcp run tool tool_name --param data=@input.json

# Run with user context (for policy testing)
mxcp run tool tool_name --user-context '{"role": "admin"}'
```

### Validation Commands

```bash
# Validate all endpoints
mxcp validate

# Run tests
mxcp test

# Check for issues
mxcp lint

# List endpoints
mxcp list
```

### Server Commands

```bash
# Start stdio server (for Claude Desktop)
mxcp serve

# Start HTTP server
mxcp serve --transport streamable-http --port 8000

# Debug mode
mxcp serve --debug
```

## Testing with AI Tools

Your MXCP server works with any MCP-compatible AI client:

- **[Claude Desktop](https://claude.com/download)** - Anthropic's desktop app with native MCP support
- **[Claude Code](https://code.claude.com/docs)** - CLI tool for developers
- **Other MCP clients** - Any tool implementing the [Model Context Protocol](https://modelcontextprotocol.io/)

### MCP Inspector

For debugging and testing without an AI client, use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector):

```bash
npx @modelcontextprotocol/inspector
```

The Inspector provides:
- **Resources Tab** - Browse available resources
- **Tools Tab** - Test tools with custom inputs and view results
- **Prompts Tab** - Test prompt templates
- **Notifications** - View server logs and debug messages

This is useful for:
- Debugging tool implementations
- Testing parameter validation
- Verifying output formats
- Development without an AI client
