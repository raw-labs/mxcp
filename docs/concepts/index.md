---
title: "Core Concepts"
description: "MXCP fundamentals: tools vs resources vs prompts, type system basics, project structure, and execution flow. Essential reading before building."
sidebar:
  order: 1
---

> **Related Topics:** [Glossary](/getting-started/glossary) (term definitions) | [Quickstart](/getting-started/quickstart) (hands-on setup) | [Tutorials](/tutorials/) (step-by-step guides)

MXCP is built around a few core concepts that work together to provide a complete framework for building production AI tools. Understanding these concepts will help you design better endpoints and take full advantage of MXCP's features.

## Endpoints

MXCP supports three types of MCP endpoints:

### Tools
Tools are functions that AI can call to perform actions or retrieve data. They have:
- **Parameters** - Inputs with types, descriptions, and validation rules
- **Return type** - The structure of the output
- **Source** - SQL or Python implementation

```yaml
tool:
  name: get_user
  description: Get user by ID
  parameters:
    - name: user_id
      type: integer
  return:
    type: object
  source:
    file: ../sql/get_user.sql
```

### Resources
Resources are data sources that can be read by AI. They use URI templates:
- **URI** - Pattern like `users://{user_id}`
- **Parameters** - Extracted from the URI
- **MIME type** - Content type of the response

```yaml
resource:
  uri: "users://{user_id}"
  description: User profile data
  mime_type: application/json
```

### Prompts
Prompts are reusable message templates with Jinja2 templating:

```yaml
prompt:
  name: analyze_data
  description: Prompt for data analysis
  messages:
    - role: system
      prompt: "You are a data analyst."
    - role: user
      prompt: "Analyze this data: {{ data }}"
```

[Learn more about endpoints →](endpoints)

## Type System

MXCP uses a JSON Schema-compatible type system for validation:

### Base Types
- `string` - Text values
- `number` - Floating-point numbers
- `integer` - Whole numbers
- `boolean` - True/false values
- `array` - Ordered lists
- `object` - Key-value structures

### Format Annotations
Strings can have format annotations for specialized handling:
- `email` - Email addresses
- `uri` - URLs
- `date` - ISO 8601 dates
- `date-time` - ISO 8601 timestamps
- `duration` - ISO 8601 durations

### Validation Constraints
- `minimum`/`maximum` - Number bounds
- `minLength`/`maxLength` - String lengths
- `minItems`/`maxItems` - Array lengths
- `enum` - Allowed values
- `required` - Required object properties

### Sensitive Data
Mark fields as `sensitive: true` to:
- Redact in audit logs
- Filter with policies
- Protect in responses

[Learn more about the type system →](type-system)

## Project Structure

MXCP enforces a consistent directory structure:

```
my-project/
├── mxcp-site.yml       # Project configuration
├── tools/              # Tool definitions
├── resources/          # Resource definitions
├── prompts/            # Prompt definitions
├── evals/              # Evaluation definitions
├── python/             # Python code
├── plugins/            # DuckDB plugins
├── sql/                # SQL implementations
├── drift/              # Drift snapshots
└── audit/              # Audit logs
```

This structure enables:
- **Auto-discovery** - MXCP finds endpoints automatically
- **Separation of concerns** - Clear organization
- **Version control** - Easy diffs and reviews

[Learn more about project structure →](project-structure)

## Configuration

MXCP uses two configuration files:

### Site Configuration (`mxcp-site.yml`)
Project-specific settings that live in your repository:
- Project name and profile
- DuckDB settings
- Extensions and plugins
- dbt integration

### User Configuration (`~/.mxcp/config.yml`)
User-specific settings for secrets and authentication:
- Secrets and credentials
- OAuth provider settings
- Vault/1Password integration

[Learn more about configuration →](/operations/configuration)

## Execution Flow

When an endpoint is called:

1. **Validation** - Input is validated against parameter types
2. **Policy Check** - Input policies are evaluated
3. **Execution** - SQL or Python code runs
4. **Output Validation** - Result is validated against return type
5. **Policy Filter** - Output policies filter/mask data
6. **Audit Logging** - Execution is logged (if enabled)

This consistent flow ensures:
- Type safety at all stages
- Security through policies
- Traceability through audit logs

## Next Steps

- [Endpoints](endpoints) - Deep dive into tools, resources, and prompts
- [Type System](type-system) - Complete type reference
- [Project Structure](project-structure) - Directory organization
