# MXCP Plugin Example

This example demonstrates how to create and use a custom MXCP plugin. The plugin provides various UDFs (User Defined Functions) that can be used in your SQL queries.

## Overview

This plugin implements the Caesar cipher, a simple encryption technique where each letter in the plaintext is shifted by a fixed number of positions in the alphabet.

## Project Structure

```
examples/plugin/
├── my_plugin/
│   ├── __init__.py
│   └── plugin.py          # Plugin implementation
├── config.yml             # Example plugin configuration
├── mxcp-site.yml          # Project configuration
├── decipher.yml           # Endpoint using the plugin
└── README.md
```

## Configuration

### 1. User Configuration

The example includes two plugin configurations in `config.yml`:
- `rot1`: Rotates letters by 1 position (A->B, B->C, etc.)
- `rot10`: Rotates letters by 10 positions (A->K, B->L, etc.)

To use the plugin, register these configurations in your MXCP user config (`~/.mxcp/config.yml`):

```yaml
mxcp: 1.0.0

projects:
  demo-plugin:
    default: dev
    profiles:
      dev:
        plugin:
          config:
            rot1:
              rotation: "1"
            rot10:
              rotation: "10"
```

Then in your `mxcp-site.yml`, you can reference one of these configurations:

```yaml
mxcp: 1.0.0
project: demo-plugin
profile: dev
plugin:
  - name: str_secret
    module: my_plugin
    config: rot1
  - name: tricky
    module: my_plugin
    config: rot10
```

## Running the MCP

To run the service using the example configuration:

1. Set the `MXCP_CONFIG` environment variable to point to the example's config file:
   ```bash
   export MXCP_CONFIG=/path/to/examples/plugin/config.yml
   ```

2. Start the MXCP server:
   ```bash
   mxcp serve
   ```

The service will now use the example configuration with both the `simple` (rot1) and `tricky` (rot10) Caesar cipher plugins.



