# MXCP Salesforce Plugin

This plugin provides integration between MXCP and Salesforce, allowing you to query and manipulate Salesforce data through SQL.

## Features

- Execute SOQL queries
- List available Salesforce objects
- Get object descriptions
- Query specific objects

## Installation

```bash
pip install -e .
```

## Usage

The plugin provides the following UDFs:

- `soql(query: string)`: Execute an SOQL query
- `list_sobjects()`: Get a list of available Salesforce objects
- `describe_sobject(type: string)`: Get field descriptions for an object type
- `get_sobject(type: string, id: string)`: Get a specific object by ID

See the parent directory for a complete example of how to use this plugin with MXCP. 