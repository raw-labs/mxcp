# Squirro Search MXCP Tool

This MXCP tool provides intelligent search capabilities for the Squirro knowledge management system. It allows natural language queries, full-text content extraction, and relevant excerpt identification.

## Setup

### 1. Install Dependencies

```bash
uv pip install -r requirements.txt
```

### 2. Configure Environment Variables

Set the following environment variables:

```bash
export SQUIRRO_BASE_URL="https://your-instance.squirro.cloud/"
export SQUIRRO_REFRESH_TOKEN="your_refresh_token_here"
export SQUIRRO_PROJECT_ID="your_project_id_here"
```

## Usage

### As MXCP Tool

The tool is defined in `tools/squirro-search.yml` and will be automatically available when running MXCP.

### Direct Python Usage

You can also use the function directly in Python:

```python
from python.squirro_search import search_squirro

# Simple search
results = search_squirro("RTGS payment procedures")

# Advanced search with filters
results = search_squirro(
    query="risk management framework",
    max_results=20,
    created_after="2025-01-01",
    include_file_content=True,
    highlight=True
)

# Fast metadata-only search
results = search_squirro(
    query="settlement system",
    max_results=10,
    include_file_content=False  # Much faster, returns only metadata
)
```

### Command Line Testing

```bash
# Activate virtual environment
source .venv/bin/activate

# Set environment variables
export SQUIRRO_BASE_URL="..."
export SQUIRRO_REFRESH_TOKEN="..."
export SQUIRRO_PROJECT_ID="..."

# Run a test search
python python/squirro_search.py "your search query"
```

## Features

### 🔍 **Intelligent Search**
- Natural language queries
- Keyword-based search
- Semantic relevance scoring
- Date range filtering

### 📄 **Content Extraction**
- Automatic PDF text extraction (via pdfminer)
- DOCX document parsing
- Full-text preview generation
- Relevant excerpt identification

### 🎯 **Result Enrichment**
- Document metadata (title, abstract, keywords)
- Relevance scores
- Creation and modification timestamps
- Highlighted query matches
- Context-aware text chunks

### ⚡ **Performance Options**
- **Full content mode**: Extracts and analyzes complete document text
- **Metadata-only mode**: Fast searches returning only document information
- Configurable pagination for large result sets
- Adjustable excerpt window sizes

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | *required* | Search query (natural language or keywords) |
| `max_results` | int | 10 | Maximum number of results (1-100) |
| `include_file_content` | boolean | true | Extract full text from files |
| `created_after` | string | - | Filter documents created after date (ISO 8601) |
| `created_before` | string | - | Filter documents created before date (ISO 8601) |
| `start` | int | 0 | Pagination offset |
| `highlight` | boolean | false | Include highlighted snippets |
| `abstract_size` | int | 250 | Abstract length in characters (50-1000) |
| `chunk_window` | int | 200 | Characters around query matches (50-500) |
| `max_chunks_per_result` | int | 5 | Maximum excerpts per document (1-10) |

## Return Value

```python
{
    "query": "search query",
    "total_count": 42,           # Total matching documents
    "returned_count": 10,         # Documents in this response
    "start": 0,                   # Pagination offset
    "has_more": true,             # More results available
    "results": [
        {
            "id": "doc_id",
            "title": "Document Title",
            "abstract": ["Summary paragraph 1", "..."],
            "score": 18.5,        # Relevance score
            "created_at": "2025-10-17T10:01:08Z",
            "modified_at": "2025-10-17T10:01:40Z",
            "keywords": {
                "file_name": ["document.pdf"],
                "nlp_tag__phrases": ["payment", "settlement", ...]
            },
            "file_info": {        # Present if document has a file
                "mime_type": "application/pdf",
                "filename": "document.pdf",
                "link": "/storage/..."
            },
            "content": {          # Present if include_file_content=true
                "full_text_preview": "First 500 chars...",
                "relevant_chunks": [
                    "...excerpt with query terms...",
                    "...another relevant section..."
                ],
                "extraction_status": "success"
            },
            "highlight": {...}    # Present if highlight=true
        }
    ]
}
```

## Use Cases

### 1. Find Recent Documents
```python
results = search_squirro(
    query="technical specifications",
    created_after="2025-10-01"
)
```

### 2. Deep Content Analysis
```python
results = search_squirro(
    query="What are the payment settlement procedures?",
    max_results=5,
    include_file_content=True,
    chunk_window=300,  # More context
    max_chunks_per_result=10  # More excerpts
)
```

### 3. Quick Overview Search
```python
results = search_squirro(
    query="regulatory compliance",
    max_results=20,
    include_file_content=False  # Fast, metadata only
)
```

### 4. Pagination Through Results
```python
# First page
page1 = search_squirro(query="banking regulations", max_results=10, start=0)

# Second page
if page1["has_more"]:
    page2 = search_squirro(query="banking regulations", max_results=10, start=10)
```

## Error Handling

The function validates inputs and provides clear error messages:

- `ValueError`: Invalid parameters or missing environment variables
- `ConnectionError`: Unable to connect to Squirro cluster
- `AuthenticationError`: Invalid refresh token

Individual document extraction errors are captured in the `extraction_status` field and don't break the entire search.

## Architecture

```
squirro-search/
├── python/
│   └── squirro_search.py       # Main function and helpers
├── tools/
│   └── squirro-search.yml      # MXCP tool definition
└── requirements.txt             # Python dependencies
```

### Private Helper Functions

The implementation uses modular helper functions for maintainability:

- `_authenticate_client()`: Handles Squirro authentication
- `_choose_best_file()`: Selects optimal file format (PDF > DOCX > other)
- `_fetch_file_bytes()`: Downloads files from Squirro storage
- `_extract_text()`: Extracts text from PDF and DOCX files
- `_find_relevant_chunks()`: Identifies query-relevant excerpts

## Testing

Run the test suite:

```bash
# Simple test
python python/squirro_search.py "test query"

# Full test with Python
python -c "
from python.squirro_search import search_squirro
import json

result = search_squirro('RTGS', max_results=3)
print(json.dumps(result, indent=2))
"
```

## Performance Tips

1. **Use `include_file_content=False`** for exploratory searches to get fast metadata results
2. **Start with smaller `max_results`** values (5-10) and paginate if needed
3. **Adjust `chunk_window`** based on your needs:
   - Smaller (100-150): Focused excerpts
   - Larger (300-500): More context
4. **Use date filters** when possible to reduce the search space

## Troubleshooting

### "SQUIRRO_BASE_URL environment variable is not set"
Set all required environment variables before running the tool.

### "Unable to extract text from file"
- Check if the file format is supported (PDF, DOCX)
- Verify the file is not corrupted
- Try setting `include_file_content=False` for metadata-only results

### Slow performance
- Set `include_file_content=False` to skip file downloads
- Reduce `max_results`
- Reduce `chunk_window` and `max_chunks_per_result`

## License

This tool is part of the MXCP examples and follows the same license as the MXCP project.

