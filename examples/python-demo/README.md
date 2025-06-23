# Python Endpoints Demo

This example demonstrates how to create and use Python-based endpoints in MXCP.

## Features Demonstrated

### 1. Basic Python Functions
- `analyze_numbers` - Statistical analysis with various operations
- `create_sample_data` - Database operations from Python

### 2. Async Functions
- `process_time_series` - Demonstrates async Python endpoint

### 3. Database Access
- Using `mxcp.runtime.db` to execute SQL queries
- Parameter binding for safe SQL execution

## Running the Examples

1. Start the MXCP server:
```bash
mxcp serve
```

2. In another terminal, test the endpoints:

```bash
# Create sample data
mxcp run tool create_sample_data --param table_name=test_data --param row_count=100

# Analyze numbers
mxcp run tool analyze_numbers --param numbers="[1, 2, 3, 4, 5]" --param operation=mean

# Process time series (async function)
mxcp run tool process_time_series --param table_name=test_data --param window_days=7
```

## Project Structure

```
python-demo/
├── mxcp-site.yml         # Project configuration
├── python/               # Python modules
│   └── data_analysis.py  # Python endpoint implementations
├── tools/                # Tool definitions
│   ├── analyze_numbers.yml
│   ├── create_sample_data.yml
│   └── process_time_series.yml
└── README.md
```

## Key Concepts

1. **Language Declaration**: Set `language: python` in the tool definition
2. **Function Names**: The function name must match the tool name
3. **Return Types**: Functions must return data matching the declared return type
4. **Database Access**: Use `db.execute()` for SQL queries
5. **Async Support**: Both sync and async functions are supported 
