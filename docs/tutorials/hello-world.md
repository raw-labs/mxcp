---
title: "Hello World Tutorial"
description: "Create your first MXCP tool. Learn the basics of tool definitions, SQL implementation, and running endpoints."
sidebar:
  order: 2
---

In this tutorial, you'll create your first MXCP tool - a simple greeting function. You'll learn the fundamental concepts that apply to all MXCP endpoints.

## Goal

Build a tool that:
- Accepts a name parameter
- Returns a greeting message
- Can be called from the CLI and AI clients

## Prerequisites

- MXCP installed (`pip install mxcp`)
- A terminal/command prompt

## Step 1: Create a Project

Initialize a new MXCP project:

```bash
mkdir hello-mxcp
cd hello-mxcp
mxcp init
```

This creates the basic structure:
```
hello-mxcp/
├── mxcp-site.yml
├── tools/
├── resources/
├── prompts/
├── evals/
├── python/
├── plugins/
├── sql/
├── drift/
└── audit/
```

## Step 2: Create the Tool Definition

Create `tools/hello.yml`:

```yaml
mxcp: 1
tool:
  name: hello
  description: Say hello to someone
  enabled: true

  parameters:
    - name: name
      type: string
      description: Name of the person to greet
      examples:
        - "World"
        - "Alice"
        - "Bob"

  return:
    type: string
    description: A friendly greeting message

  source:
    file: ../sql/hello.sql
```

Let's break down each part:

| Field | Purpose |
|-------|---------|
| `mxcp: 1` | Schema version (always 1) |
| `name` | Unique identifier for the tool |
| `description` | What the tool does (shown to AI) |
| `enabled` | Whether to load this tool |
| `parameters` | Input definitions |
| `return` | Output definition |
| `source` | Where the implementation lives |

## Step 3: Write the SQL Implementation

Create `sql/hello.sql`:

```sql
SELECT 'Hello, ' || $name || '!' AS greeting
```

The `$name` syntax binds the `name` parameter from the tool definition. DuckDB handles the parameter substitution safely (preventing SQL injection).

## Step 4: Validate Your Tool

Check that your tool is correctly defined:

```bash
mxcp validate
```

Expected output:
```
✓ tools/hello.yml (tool/hello)
Validation complete: 1 passed, 0 failed
```

## Step 5: Run the Tool

Execute the tool from the command line:

```bash
mxcp run tool hello --param name=World
```

Output:
```
greeting
--------
Hello, World!
```

Try different names:

```bash
mxcp run tool hello --param name=Alice
mxcp run tool hello --param name="MXCP User"
```

## Step 6: List Your Endpoints

See all available endpoints:

```bash
mxcp list
```

Output:
```
Endpoints:
  Tools:
    - hello: Say hello to someone

  Resources:
    (none)

  Prompts:
    (none)
```

## Step 7: Add Tests

Update `tools/hello.yml` to include tests:

```yaml
mxcp: 1
tool:
  name: hello
  description: Say hello to someone
  enabled: true

  parameters:
    - name: name
      type: string
      description: Name of the person to greet
      examples:
        - "World"
        - "Alice"

  return:
    type: string
    description: A friendly greeting message

  source:
    file: ../sql/hello.sql

  tests:
    - name: greet_world
      description: Test greeting World
      arguments:
        - key: name
          value: "World"
      result: "Hello, World!"

    - name: greet_alice
      description: Test greeting Alice
      arguments:
        - key: name
          value: "Alice"
      result_contains_text: "Alice"
```

Run the tests:

```bash
mxcp test
```

Output:
```
Testing tool/hello...
  ✓ greet_world
  ✓ greet_alice

Tests: 2 passed, 0 failed
```

## Step 8: Check for Issues

Run the linter to check for improvements:

```bash
mxcp lint
```

The linter checks for:
- Missing descriptions
- Missing examples
- Best practice violations

## Verification

Your project should now have:

```
hello-mxcp/
├── mxcp-site.yml
├── tools/
│   └── hello.yml
├── sql/
│   └── hello.sql
└── ... (other directories)
```

You can verify everything works:

```bash
# Validate structure
mxcp validate

# Run tests
mxcp test

# Run the tool
mxcp run tool hello --param name="Tutorial Complete"
```

## Understanding the Flow

When you run `mxcp run tool hello --param name=World`:

1. **Load** - MXCP reads `tools/hello.yml`
2. **Validate Input** - Checks `name` is a string
3. **Read SQL** - Loads `sql/hello.sql`
4. **Execute** - Runs the query with `$name` = "World"
5. **Validate Output** - Checks result matches return type
6. **Return** - Displays the result

## Inline SQL Alternative

Instead of a separate file, you can use inline SQL:

```yaml
source:
  code: |
    SELECT 'Hello, ' || $name || '!' AS greeting
```

External files are recommended for:
- Better version control
- Syntax highlighting in editors
- Reusable SQL across tools

## Next Steps

Now that you understand the basics:

1. **[SQL Endpoints Tutorial](sql-endpoints)** - Build more complex queries
2. **[Python Endpoints Tutorial](python-endpoints)** - Add Python logic
3. **[Endpoints Concept](/concepts/endpoints)** - Deep dive into endpoint types

## Common Issues

### "No tool found with name..."
- Check the `name` field in your YAML matches what you're calling
- Run `mxcp list` to see available tools

### "File not found..."
- Verify the path in `source.file` is correct
- Paths are relative to the YAML file location

### "Validation error..."
- Check YAML syntax (indentation matters)
- Ensure all required fields are present
- Run `mxcp validate` for detailed errors
