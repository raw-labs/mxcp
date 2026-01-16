---
title: "Prompt Schema"
description: "Complete YAML schema reference for MXCP prompt definitions. Messages, parameters, Jinja2 templates, and multi-turn conversations."
sidebar:
  order: 4
---

> **Related Topics:** [Endpoints](/concepts/endpoints) (prompt concepts) | [Type System](/concepts/type-system) (parameter types)

This reference documents the complete YAML schema for prompt definitions in MXCP.

## Complete Example

```yaml
mxcp: 1
prompt:
  name: analyze_data
  description: Analyze data with customizable focus areas
  tags:
    - analysis
    - data

  parameters:
    - name: topic
      type: string
      description: The topic or dataset to analyze
      examples: ["sales trends", "user behavior", "performance metrics"]

    - name: focus_areas
      type: array
      description: Specific areas to focus the analysis on
      items:
        type: string
      default: []

    - name: output_format
      type: string
      description: Desired output format
      enum: ["summary", "detailed", "bullet_points"]
      default: "summary"

  messages:
    - role: system
      type: text
      prompt: |
        You are an expert data analyst. Provide clear, actionable insights.
        {% if focus_areas %}
        Focus particularly on: {{ focus_areas | join(', ') }}
        {% endif %}

    - role: user
      type: text
      prompt: |
        Please analyze the following topic: {{ topic }}

        Provide your analysis in {{ output_format }} format.

  tests:
    - name: basic_analysis
      arguments:
        - key: topic
          value: "quarterly sales"
      result_contains_text: "analysis"

  enabled: true
```

## Root Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `mxcp` | integer | Yes | - | Schema version. Must be `1`. |
| `prompt` | object | Yes | - | Prompt definition object. |
| `metadata` | object | No | - | Custom metadata (not processed by MXCP). |

> **Note:** The `mxcp` field accepts both integer (`1`) and string (`"1"`) values - strings are automatically coerced to integers.

## Prompt Object

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Unique identifier. Must start with letter/underscore, alphanumeric only. |
| `description` | string | No | - | Human-readable description for AI clients. |
| `tags` | array | No | - | List of tags for categorization. |
| `parameters` | array | No | - | Template parameter definitions. |
| `return` | object | No | - | Return type definition. |
| `messages` | array | Yes | - | Message sequence with Jinja2 templates. |
| `policies` | object | No | - | Input and output policy rules. |
| `tests` | array | No | - | Test case definitions. |
| `enabled` | boolean | No | `true` | Whether the prompt is enabled. |

## Messages Array

Messages define the conversation structure.

### Message Object

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prompt` | string | Yes | - | Text content with Jinja2 templates, or resource URI when `type: resource`. |
| `role` | string | No | - | Message role: `system`, `user`, or `assistant`. |
| `type` | string | No | - | Content type: `text` or `resource`. |

### Text Messages

```yaml
messages:
  - role: system
    type: text
    prompt: "You are a helpful assistant specialized in {{ domain }}."

  - role: user
    type: text
    prompt: "{{ user_query }}"
```

### Resource Messages

Embed resource content directly into prompts by setting `type: resource` and putting the URI in the `prompt` field:

```yaml
messages:
  - role: system
    type: text
    prompt: "You are a code reviewer."

  - role: user
    type: resource
    prompt: "file://{{ file_path }}"

  - role: user
    type: text
    prompt: "Please review the code above for {{ review_focus }}."
```

> **Note:** When `type: resource`, the `prompt` field contains the resource URI instead of text content.

### Multi-Turn Conversations

```yaml
messages:
  - role: system
    type: text
    prompt: "You are a technical interviewer."

  - role: user
    type: text
    prompt: "I'd like to discuss {{ topic }}."

  - role: assistant
    type: text
    prompt: "I'd be happy to discuss {{ topic }}. Let me start with a question."

  - role: user
    type: text
    prompt: "{{ candidate_response }}"
```

## Jinja2 Templates

Prompts support Jinja2 templating for dynamic content.

### Variable Substitution

```yaml
prompt: "Analyze {{ topic }} for {{ time_period }}."
```

### Conditionals

```yaml
prompt: |
  {% if include_examples %}
  Here are some examples:
  {{ examples | join('\n') }}
  {% endif %}

  Now analyze: {{ query }}
```

### Loops

```yaml
prompt: |
  Review the following items:
  {% for item in items %}
  - {{ item.name }}: {{ item.description }}
  {% endfor %}
```

### Filters

Common Jinja2 filters:

| Filter | Description | Example |
|--------|-------------|---------|
| `upper` | Convert to uppercase | `{{ text \| upper }}` |
| `lower` | Convert to lowercase | `{{ text \| lower }}` |
| `title` | Convert to titlecase | `{{ text \| title }}` |
| `trim` | Strip leading/trailing whitespace | `{{ text \| trim }}` |
| `default` | Provide fallback for undefined | `{{ value \| default('N/A') }}` |
| `join` | Join array elements with separator | `{{ items \| join(', ') }}` |
| `length` | Get array/string length | `{{ items \| length }}` |
| `first` | Get first element | `{{ items \| first }}` |
| `last` | Get last element | `{{ items \| last }}` |
| `replace` | Replace substring | `{{ text \| replace('old', 'new') }}` |
| `sort` | Sort an iterable | `{{ items \| sort }}` |

### Complex Template Example

```yaml
prompt: |
  {% set priority_label = {
    'high': 'URGENT',
    'medium': 'Standard',
    'low': 'When possible'
  } %}

  Task: {{ task_name }}
  Priority: {{ priority_label[priority] | default('Unknown') }}

  {% if context %}
  Context:
  {{ context }}
  {% endif %}

  {% if constraints %}
  Constraints:
  {% for constraint in constraints %}
  - {{ constraint }}
  {% endfor %}
  {% endif %}

  Please provide your response.
```

## Parameters Array

Each parameter defines an input to the prompt template.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Parameter identifier (snake_case). |
| `type` | string | Yes | - | Data type: `string`, `integer`, `number`, `boolean`, `array`, `object`. |
| `description` | string | No | - | Human-readable description. |
| `default` | any | No | - | Default value (makes parameter optional). |
| `examples` | array | No | - | Example values for documentation. |
| `enum` | array | No | - | Allowed values. |

### Type-Specific Constraints

**String constraints:**

| Field | Type | Description |
|-------|------|-------------|
| `minLength` | integer | Minimum string length. |
| `maxLength` | integer | Maximum string length. |
| `pattern` | string | Regex pattern to match. |
| `format` | string | Format hint: `email`, `uri`, `date`, `time`, `date-time`, `duration`, `timestamp`. |

**Number/Integer constraints:**

| Field | Type | Description |
|-------|------|-------------|
| `minimum` | number | Minimum value (inclusive). |
| `maximum` | number | Maximum value (inclusive). |
| `exclusiveMinimum` | number | Minimum value (exclusive). |
| `exclusiveMaximum` | number | Maximum value (exclusive). |
| `multipleOf` | number | Value must be multiple of this. |

**Array constraints:**

| Field | Type | Description |
|-------|------|-------------|
| `items` | object | Type definition for array items. |
| `minItems` | integer | Minimum array length. |
| `maxItems` | integer | Maximum array length. |
| `uniqueItems` | boolean | Whether items must be unique. |

**Object constraints:**

| Field | Type | Description |
|-------|------|-------------|
| `properties` | object | Map of property names to type definitions. |
| `required` | array | List of required property names. |
| `additionalProperties` | boolean | Whether extra (unspecified) object properties are accepted and preserved. Default: `true` (if omitted). Use `false` to reject unknown keys. |

**Note:** If `additionalProperties` is omitted, MXCP treats it as `true` (extra keys are allowed and preserved). Set `additionalProperties: false` to forbid unknown keys.

```yaml
# Allow unknown keys (default behavior)
type: object
properties:
  objid:
    type: integer
required: ["objid"]

# Forbid unknown keys
type: object
properties:
  objid:
    type: integer
required: ["objid"]
additionalProperties: false
```

### Parameter Examples

```yaml
parameters:
  # Required string
  - name: query
    type: string
    description: The user's question or request
    minLength: 1
    maxLength: 10000

  # Optional with default
  - name: tone
    type: string
    description: Response tone
    enum: ["formal", "casual", "technical"]
    default: "formal"

  # Array parameter
  - name: topics
    type: array
    description: Topics to cover
    items:
      type: string
    minItems: 1
    maxItems: 10

  # Object parameter
  - name: context
    type: object
    description: Additional context
    properties:
      user_role:
        type: string
      preferences:
        type: array
        items:
          type: string
```

## Return Object

Define the expected structure of the prompt's output:

```yaml
return:
  type: object
  properties:
    summary:
      type: string
      description: Brief summary of the analysis
    findings:
      type: array
      items:
        type: object
        properties:
          category:
            type: string
          insight:
            type: string
          confidence:
            type: number
    recommendations:
      type: array
      items:
        type: string
```

## Tests Array

Tests verify prompt behavior.

```yaml
tests:
  - name: basic_prompt
    description: Test basic prompt generation
    arguments:
      - key: topic
        value: "machine learning"
    result_contains_text: "machine learning"

  - name: with_options
    description: Test with all options
    arguments:
      - key: topic
        value: "data analysis"
      - key: output_format
        value: "detailed"
      - key: focus_areas
        value: ["trends", "anomalies"]
    result_contains_text: "trends"
```

### Test Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique test identifier. |
| `description` | string | No | Human-readable description. |
| `arguments` | array | Yes | Input arguments as key-value pairs. |
| `user_context` | object | No | Simulated user context for policy testing. |

### Test Assertions

| Field | Type | Description |
|-------|------|-------------|
| `result` | any | Expected exact result. |
| `result_contains` | any | Partial match - fields must exist with values. |
| `result_contains_text` | string | Output must contain substring. |
| `result_not_contains` | array | Field names that must NOT exist. |

See [Testing](/quality/testing) for complete documentation.

## Policies Object

Policies control access and data filtering for prompts.

```yaml
policies:
  input:
    - condition: "user.role == 'guest'"
      action: deny
      reason: "Guests cannot use this prompt"

  output:
    - condition: "user.role != 'admin'"
      action: filter_fields
      fields: ["internal_notes"]
      reason: "Internal fields restricted"
```

### Policy Rule Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `condition` | string | Yes | CEL expression to evaluate. |
| `action` | string | Yes | Action to take: `deny`, `filter_fields`, `mask_fields`, `filter_sensitive_fields`. |
| `reason` | string | No | Human-readable reason. |
| `fields` | array | No | Fields to filter/mask (for `filter_fields`, `mask_fields`). |

See [Policies](/security/policies) for complete documentation.

## Common Patterns

### Analysis Prompt

```yaml
mxcp: 1
prompt:
  name: analyze_document
  description: Analyze a document for key insights

  parameters:
    - name: document
      type: string
      description: The document content to analyze
    - name: analysis_type
      type: string
      enum: ["summary", "sentiment", "key_points", "full"]
      default: "summary"

  messages:
    - role: system
      type: text
      prompt: |
        You are an expert document analyst.
        Provide {{ analysis_type }} analysis.

    - role: user
      type: text
      prompt: |
        Please analyze the following document:

        {{ document }}
```

### Code Review Prompt

```yaml
mxcp: 1
prompt:
  name: code_review
  description: Review code for quality and issues

  parameters:
    - name: code
      type: string
      description: Code to review
    - name: language
      type: string
      description: Programming language
    - name: focus
      type: array
      items:
        type: string
        enum: ["security", "performance", "readability", "best_practices"]
      default: ["best_practices"]

  messages:
    - role: system
      type: text
      prompt: |
        You are an expert {{ language }} code reviewer.
        Focus on: {{ focus | join(', ') }}

    - role: user
      type: text
      prompt: |
        Please review this {{ language }} code:

        ```{{ language }}
        {{ code }}
        ```
```

### Q&A with Context

```yaml
mxcp: 1
prompt:
  name: contextual_qa
  description: Answer questions with provided context

  parameters:
    - name: context
      type: string
      description: Background information
    - name: question
      type: string
      description: The question to answer
    - name: response_style
      type: string
      enum: ["concise", "detailed", "eli5"]
      default: "concise"

  messages:
    - role: system
      type: text
      prompt: |
        Answer questions based on the provided context.
        Style: {{ response_style }}
        Only use information from the context.

    - role: user
      type: text
      prompt: |
        Context:
        {{ context }}

        Question: {{ question }}
```

## Naming Conventions

- **Prompt names**: Use `snake_case` (e.g., `analyze_data`, `code_review`)
- **Parameter names**: Use `snake_case` (e.g., `user_query`, `output_format`)
- **File paths**: Relative to the YAML file location

## Validation

Validate your prompt definitions:

```bash
mxcp validate
mxcp validate prompts/my-prompt.yml
```

## Next Steps

- [Endpoints](/concepts/endpoints) - Understand prompt concepts
- [Type System](/concepts/type-system) - Detailed type documentation
- [Testing](/quality/testing) - Write comprehensive tests
