"""
Squirro Search Tool for MXCP

This module provides a search interface to the Squirro knowledge management system,
allowing users to query documents and extract relevant content with full-text search capabilities.

Environment Variables Required:
    SQUIRRO_BASE_URL: The base URL of your Squirro cluster (e.g., https://your-instance.squirro.cloud/)
    SQUIRRO_REFRESH_TOKEN: Your Squirro API refresh token for authentication
    SQUIRRO_PROJECT_ID: The project ID to search within
"""

import os
import re
import tempfile
from typing import Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urljoin

# Import dependencies with graceful fallback for validation
try:
    import requests
except ImportError:
    requests = None

try:
    from squirro_client import SquirroClient
except ImportError:
    SquirroClient = None

try:
    from pdfminer.high_level import extract_text as pdf_extract_text
except ImportError:
    pdf_extract_text = None

try:
    from docx import Document
except ImportError:
    Document = None


def search_squirro(
    query: str,
    max_results: int = 10,
    include_file_content: bool = True,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    start: int = 0,
    highlight: bool = False,
    abstract_size: int = 250,
    chunk_window: int = 200,
    max_chunks_per_result: int = 5,
) -> Dict[str, Any]:
    """
    Search the Squirro system for documents and content matching the query.

    This function searches across all documents in the configured Squirro project,
    optionally downloads and extracts full text from files (PDF, DOCX), and returns
    relevant chunks of content around the search terms.

    Args:
        query: The search query string. Use natural language or keywords to find relevant documents.
               Examples: "RTGS transactions", "payment settlement procedures", "risk management"

        max_results: Maximum number of search results to return (1-100). Default is 10.
                    Higher values provide more comprehensive results but take longer to process.

        include_file_content: If True, downloads and extracts full text from document files (PDF, DOCX).
                             If False, returns only metadata and abstracts (much faster).
                             Set to False for quick metadata-only searches. Default is True.

        created_after: Filter to only include documents created after this date.
                      Format: ISO 8601 datetime string (e.g., "2025-01-01T00:00:00Z" or "2025-01-01").
                      Useful for finding recent documents. Optional.

        created_before: Filter to only include documents created before this date.
                       Format: ISO 8601 datetime string (e.g., "2025-12-31T23:59:59Z" or "2025-12-31").
                       Useful for historical searches. Optional.

        start: Pagination offset - number of results to skip before returning matches.
              Use this with max_results to paginate through large result sets.
              Example: start=10, max_results=10 returns results 11-20. Default is 0.

        highlight: If True, returns highlighted snippets showing where query terms appear in documents.
                  Useful for understanding why a document matched. Default is False.

        abstract_size: Maximum length of the document abstract/summary in characters (50-1000).
                      Longer abstracts provide more context but take more space. Default is 250.

        chunk_window: When extracting file content, the number of characters to include
                     around each query match (50-500). Larger windows provide more context
                     but may include less relevant text. Default is 200.

        max_chunks_per_result: Maximum number of relevant text chunks to extract per document (1-10).
                              More chunks give better coverage but increase response size. Default is 5.

    Returns:
        A dictionary containing:
        {
            "query": str,                    # The original search query
            "total_count": int,              # Total number of matching documents in Squirro
            "returned_count": int,           # Number of results actually returned
            "start": int,                    # Pagination offset used
            "has_more": bool,                # True if more results are available for pagination
            "results": [                     # List of search results
                {
                    "id": str,               # Unique document ID in Squirro
                    "title": str,            # Document title
                    "abstract": List[str],   # Document summary/abstract (list of paragraphs)
                    "score": float,          # Relevance score (higher = more relevant)
                    "created_at": str,       # Document creation timestamp (ISO 8601)
                    "modified_at": str,      # Last modification timestamp (ISO 8601)
                    "keywords": Dict,        # Extracted keywords, tags, and metadata
                    "file_info": {           # Present if document has an attached file
                        "mime_type": str,    # File type (e.g., "application/pdf")
                        "filename": str,     # Original filename
                        "link": str          # Relative URL to download file
                    },
                    "content": {             # Present if include_file_content=True and extraction succeeded
                        "full_text_preview": str,      # First 500 characters of extracted text
                        "relevant_chunks": List[str],  # Text excerpts containing query terms
                        "extraction_status": str       # "success" or error message
                    },
                    "highlight": Dict        # Present if highlight=True, shows match locations
                }
            ]
        }

    Raises:
        ValueError: If required environment variables are not set or parameters are invalid
        ConnectionError: If unable to connect to Squirro cluster
        AuthenticationError: If authentication fails (invalid token)

    Example:
        # Simple search
        results = search_squirro("RTGS payment procedures")

        # Search recent documents only, with pagination
        results = search_squirro(
            query="risk management",
            max_results=20,
            created_after="2025-01-01",
            start=0
        )

        # Fast metadata-only search with highlighting
        results = search_squirro(
            query="settlement system",
            include_file_content=False,
            highlight=True
        )
    """
    # Check runtime dependencies
    if SquirroClient is None:
        raise ImportError(
            "squirro_client is not installed. Install with: pip install SquirroClient"
        )
    if requests is None:
        raise ImportError("requests is not installed. Install with: pip install requests")
    if include_file_content and (pdf_extract_text is None or Document is None):
        raise ImportError(
            "pdfminer.six and python-docx are required for file content extraction. "
            "Install with: pip install pdfminer.six python-docx"
        )

    # Validate environment variables
    base_url = os.getenv("SQUIRRO_BASE_URL")
    refresh_token = os.getenv("SQUIRRO_REFRESH_TOKEN")
    project_id = os.getenv("SQUIRRO_PROJECT_ID")

    if not base_url:
        raise ValueError("SQUIRRO_BASE_URL environment variable is not set")
    if not refresh_token:
        raise ValueError("SQUIRRO_REFRESH_TOKEN environment variable is not set")
    if not project_id:
        raise ValueError("SQUIRRO_PROJECT_ID environment variable is not set")

    # Validate parameters
    if not query or not query.strip():
        raise ValueError("query parameter cannot be empty")
    if max_results < 1 or max_results > 100:
        raise ValueError("max_results must be between 1 and 100")
    if abstract_size < 50 or abstract_size > 1000:
        raise ValueError("abstract_size must be between 50 and 1000")
    if chunk_window < 50 or chunk_window > 500:
        raise ValueError("chunk_window must be between 50 and 500")
    if max_chunks_per_result < 1 or max_chunks_per_result > 10:
        raise ValueError("max_chunks_per_result must be between 1 and 10")

    # Authenticate and execute search
    client = _authenticate_client(base_url, refresh_token)

    # Build query options
    options = {"abstract_size": abstract_size}
    highlight_config = {"query": True} if highlight else None

    # Execute query
    search_results = client.query(
        project_id=project_id,
        query=query,
        fields=[
            "id",
            "title",
            "files",
            "abstract",
            "keywords",
            "score",
            "created_at",
            "modified_at",
            "external_id",
        ],
        count=max_results,
        start=start,
        created_after=created_after,
        created_before=created_before,
        highlight=highlight_config,
        options=options,
    )

    # Process results
    items = search_results.get("items", [])
    total_count = search_results.get("count", 0)

    results = []
    for item in items:
        result_item = {
            "id": item.get("id"),
            "title": item.get("title"),
            "abstract": item.get("abstract", []),
            "score": item.get("score"),
            "created_at": item.get("created_at"),
            "modified_at": item.get("modified_at"),
            "keywords": item.get("keywords", {}),
        }

        # Add highlight if available
        if highlight and "highlight" in item:
            result_item["highlight"] = item["highlight"]

        # Process file content if requested
        files = item.get("files") or []
        if files:
            mime_type, rel_link, filename = _choose_best_file(files)
            if rel_link:
                result_item["file_info"] = {
                    "mime_type": mime_type,
                    "filename": filename,
                    "link": rel_link,
                }

                if include_file_content:
                    try:
                        file_bytes = _fetch_file_bytes(base_url, refresh_token, rel_link)
                        full_text = _extract_text(mime_type, file_bytes, filename)

                        if full_text and full_text.strip():
                            chunks = _find_relevant_chunks(
                                full_text, query, chunk_window, max_chunks_per_result
                            )
                            result_item["content"] = {
                                "full_text_preview": full_text[:500]
                                + ("..." if len(full_text) > 500 else ""),
                                "relevant_chunks": chunks,
                                "extraction_status": "success",
                            }
                        else:
                            result_item["content"] = {"extraction_status": "no_text_extracted"}
                    except Exception as e:
                        result_item["content"] = {"extraction_status": f"error: {str(e)}"}

        results.append(result_item)

    return {
        "query": query,
        "total_count": total_count,
        "returned_count": len(results),
        "start": start,
        "has_more": (start + len(results)) < total_count,
        "results": results,
    }


# Private helper functions


def _authenticate_client(base_url: str, refresh_token: str) -> SquirroClient:
    """
    Create and authenticate a Squirro client.

    Args:
        base_url: The Squirro cluster URL
        refresh_token: The refresh token for authentication

    Returns:
        Authenticated SquirroClient instance
    """
    client = SquirroClient(None, None, cluster=base_url)
    client.authenticate(refresh_token=refresh_token)
    return client


def _choose_best_file(files: List[Dict[str, Any]]) -> tuple[Optional[str], Optional[str], str]:
    """
    Select the best file representation from available files.

    Prefers: 1) PDF conversions, 2) Original DOCX, 3) First available file with link.

    Args:
        files: List of file dictionaries from Squirro item

    Returns:
        Tuple of (mime_type, link, filename_hint)
    """
    # Prefer converted PDF
    pdf = next(
        (f for f in files if f.get("mime_type") == "application/pdf" and f.get("link")), None
    )
    if pdf:
        return pdf["mime_type"], pdf["link"], _filename_hint(pdf)

    # Then original DOCX
    docx = next(
        (
            f
            for f in files
            if f.get("mime_type")
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            and f.get("link")
        ),
        None,
    )
    if docx:
        return docx["mime_type"], docx["link"], _filename_hint(docx)

    # Fallback to any file with a link
    other = next((f for f in files if f.get("link")), None)
    if other:
        return other.get("mime_type"), other["link"], _filename_hint(other)

    return None, None, "unknown"


def _filename_hint(file_dict: Dict[str, Any]) -> str:
    """Extract filename from file dictionary."""
    return file_dict.get("filename") or file_dict.get("name") or file_dict.get("title") or "file"


def _fetch_file_bytes(base_url: str, refresh_token: str, relative_link: str) -> bytes:
    """
    Download file bytes from Squirro storage.

    Args:
        base_url: The Squirro cluster URL
        refresh_token: Authentication token
        relative_link: Relative URL to the file

    Returns:
        File content as bytes
    """
    url = urljoin(base_url, relative_link)
    response = requests.get(url, headers={"Authorization": f"Bearer {refresh_token}"}, timeout=120)
    response.raise_for_status()
    return response.content


def _extract_text(mime_type: str, file_bytes: bytes, filename_hint: str = "file") -> str:
    """
    Extract text content from file bytes.

    Supports PDF and DOCX formats. Falls back to UTF-8 decoding for other types.

    Args:
        mime_type: MIME type of the file
        file_bytes: Raw file content
        filename_hint: Filename for extension-based fallback

    Returns:
        Extracted text content
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Handle PDF
        if mime_type == "application/pdf" or filename_hint.lower().endswith(".pdf"):
            file_path = os.path.join(temp_dir, "document.pdf")
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            return pdf_extract_text(file_path)

        # Handle DOCX
        if (
            mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or filename_hint.lower().endswith(".docx")
        ):
            file_path = os.path.join(temp_dir, "document.docx")
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            doc = Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

        # Fallback: try UTF-8 decoding
        try:
            return file_bytes.decode("utf-8", errors="replace")
        except Exception:
            return ""


def _find_relevant_chunks(
    text: str, query: str, window: int = 200, max_chunks: int = 5
) -> List[str]:
    """
    Find and extract text chunks containing query terms.

    Extracts windows of text around each occurrence of query terms,
    providing context for why the document matched.

    Args:
        text: Full text to search within
        query: Search query
        window: Number of characters to include around each match
        max_chunks: Maximum number of chunks to return

    Returns:
        List of text excerpts containing query terms
    """
    # Split query into tokens
    tokens = [t for t in re.split(r"\W+", query) if t]
    if not tokens or not text:
        return []

    # Build regex pattern for all tokens
    pattern = r"|".join(re.escape(t) for t in tokens)
    chunks = []

    # Find matches and extract windows
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        start = max(0, match.start() - window)
        end = min(len(text), match.end() + window)
        snippet = text[start:end].strip()

        # Deduplicate similar chunks
        if not chunks or snippet not in chunks[-1]:
            chunks.append(snippet)

        if len(chunks) >= max_chunks:
            break

    return chunks


# For backwards compatibility and testing
if __name__ == "__main__":
    # Simple test if called directly
    import sys

    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])
    else:
        test_query = "RTGS transactions"

    print(f"Searching for: {test_query}\n")

    try:
        results = search_squirro(query=test_query, max_results=5, include_file_content=True)

        print(f"Found {results['total_count']} total results")
        print(f"Returning {results['returned_count']} results\n")

        for i, result in enumerate(results["results"], 1):
            print(f"{i}. {result['title']}")
            print(f"   Score: {result['score']:.2f}")
            print(
                f"   Abstract: {' '.join(result['abstract'][:2]) if result['abstract'] else 'N/A'}"
            )

            if "content" in result and result["content"].get("extraction_status") == "success":
                chunks = result["content"]["relevant_chunks"]
                print(f"   Found {len(chunks)} relevant chunks")
                if chunks:
                    print(f"   Sample: {chunks[0][:100]}...")
            print()

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
