# MXCP Plugins Directory

This directory contains MXCP plugins that extend DuckDB with custom User Defined Functions (UDFs).

## Structure

Each plugin should be a Python module containing a class named `MXCPPlugin` that inherits from `MXCPBasePlugin`.

```
plugins/
├── my_plugin/
│   └── __init__.py    # Contains MXCPPlugin class
├── utils/
│   └── string_utils.py
└── integrations/
    └── api_plugin.py
```

## Usage

Plugins are referenced in `mxcp-site.yml`:

```yaml
plugin:
  - name: cipher
    module: my_plugin
    config: rot13
```

The functions are then available in SQL as `{function_name}_{plugin_name}`:
```sql
SELECT encrypt_cipher('hello world');
``` 