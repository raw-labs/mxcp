"""
Unit tests for squirro_search module using pytest

Tests all functions with mocked dependencies to ensure proper functionality
without requiring actual Squirro cluster access.

Run with: pytest python/test_squirro_search.py -v
"""

import os
import warnings
import threading
import concurrent.futures
from typing import Dict, Any
from unittest.mock import Mock, patch

# Suppress deprecation warnings from third-party squirro_client library
# (datetime.utcnow warning that we cannot fix)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import pytest
import squirro_search


# Fixtures


class MockSquirroClient:
    """Mock SquirroClient for testing"""

    def __init__(self, *args, **kwargs):
        self.authenticated = False
        self.cluster = kwargs.get("cluster")

    def authenticate(self, refresh_token: str):
        """Mock authentication"""
        if not refresh_token:
            raise ValueError("Invalid refresh token")
        self.authenticated = True

    def query(self, project_id: str, query: str = None, **kwargs) -> Dict[str, Any]:
        """Mock query method returning sample results"""
        if not self.authenticated:
            raise PermissionError("Not authenticated")

        # Return mock search results
        return {
            "count": 2,
            "items": [
                {
                    "id": "doc1",
                    "title": "Test Document 1",
                    "abstract": ["This is a test document about RTGS payments"],
                    "score": 18.5,
                    "created_at": "2025-10-17T10:00:00Z",
                    "modified_at": "2025-10-17T11:00:00Z",
                    "keywords": {"nlp_tag__phrases": ["payment", "rtgs", "settlement"]},
                    "files": [
                        {
                            "mime_type": "application/pdf",
                            "link": "/storage/test.pdf",
                            "filename": "test.pdf",
                        }
                    ],
                },
                {
                    "id": "doc2",
                    "title": "Test Document 2",
                    "abstract": ["Another document"],
                    "score": 12.3,
                    "created_at": "2025-10-16T10:00:00Z",
                    "modified_at": "2025-10-16T11:00:00Z",
                    "keywords": {},
                    "files": [],
                },
            ],
        }


@pytest.fixture
def env_vars():
    """Fixture providing test environment variables"""
    return {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    }


# Tests for _authenticate_client


@patch("squirro_search.SquirroClient", MockSquirroClient)
def test_authenticate_client_success():
    """Test successful client authentication"""
    client = squirro_search._authenticate_client("https://test.squirro.cloud/", "test_token")
    assert isinstance(client, MockSquirroClient)
    assert client.authenticated is True
    assert client.cluster == "https://test.squirro.cloud/"


@patch("squirro_search.SquirroClient", MockSquirroClient)
def test_authenticate_client_with_empty_token():
    """Test authentication with empty token"""
    with pytest.raises(ValueError):
        squirro_search._authenticate_client("https://test.squirro.cloud/", "")


# Tests for _choose_best_file


def test_choose_pdf_over_docx():
    """Test that PDF is preferred over DOCX"""
    files = [
        {
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "link": "/doc.docx",
            "filename": "doc.docx",
        },
        {"mime_type": "application/pdf", "link": "/doc.pdf", "filename": "doc.pdf"},
    ]
    mime, link, filename = squirro_search._choose_best_file(files)
    assert mime == "application/pdf"
    assert link == "/doc.pdf"
    assert filename == "doc.pdf"


def test_choose_docx_when_no_pdf():
    """Test that DOCX is chosen when PDF is not available"""
    files = [
        {
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "link": "/doc.docx",
            "filename": "doc.docx",
        }
    ]
    mime, link, filename = squirro_search._choose_best_file(files)
    assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert link == "/doc.docx"


def test_choose_any_file_when_no_preferred():
    """Test fallback to any file with a link"""
    files = [{"mime_type": "text/plain", "link": "/doc.txt", "name": "doc.txt"}]
    mime, link, filename = squirro_search._choose_best_file(files)
    assert mime == "text/plain"
    assert link == "/doc.txt"
    assert filename == "doc.txt"


def test_no_files_with_links():
    """Test behavior when no files have links"""
    files = [{"mime_type": "application/pdf"}]  # No link
    mime, link, filename = squirro_search._choose_best_file(files)
    assert mime is None
    assert link is None
    assert filename == "unknown"


def test_empty_files_list():
    """Test with empty files list"""
    mime, link, filename = squirro_search._choose_best_file([])
    assert mime is None
    assert link is None
    assert filename == "unknown"


# Tests for _filename_hint


def test_filename_from_filename_key():
    """Test extracting filename from 'filename' key"""
    file_dict = {"filename": "test.pdf"}
    result = squirro_search._filename_hint(file_dict)
    assert result == "test.pdf"


def test_filename_from_name_key():
    """Test extracting filename from 'name' key"""
    file_dict = {"name": "test.pdf"}
    result = squirro_search._filename_hint(file_dict)
    assert result == "test.pdf"


def test_filename_from_title_key():
    """Test extracting filename from 'title' key"""
    file_dict = {"title": "test.pdf"}
    result = squirro_search._filename_hint(file_dict)
    assert result == "test.pdf"


def test_filename_fallback():
    """Test fallback when no filename keys present"""
    file_dict = {}
    result = squirro_search._filename_hint(file_dict)
    assert result == "file"


# Tests for _fetch_file_bytes


@patch("squirro_search.requests")
def test_fetch_file_success(mock_requests):
    """Test successful file download"""
    mock_response = Mock()
    mock_response.content = b"PDF content here"
    mock_response.raise_for_status = Mock()
    mock_requests.get.return_value = mock_response

    content = squirro_search._fetch_file_bytes(
        "https://test.squirro.cloud/", "token123", "/storage/test.pdf"
    )

    assert content == b"PDF content here"
    mock_requests.get.assert_called_once_with(
        "https://test.squirro.cloud/storage/test.pdf",
        headers={"Authorization": "Bearer token123"},
        timeout=120,
    )


@patch("squirro_search.requests")
def test_fetch_file_http_error(mock_requests):
    """Test handling of HTTP errors"""
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception("404 Not Found")
    mock_requests.get.return_value = mock_response

    with pytest.raises(Exception, match="404 Not Found"):
        squirro_search._fetch_file_bytes(
            "https://test.squirro.cloud/", "token123", "/storage/missing.pdf"
        )


# Tests for _extract_text


@patch("squirro_search.pdf_extract_text")
def test_extract_from_pdf(mock_pdf_extract):
    """Test extracting text from PDF"""
    mock_pdf_extract.return_value = "Extracted PDF text"

    result = squirro_search._extract_text("application/pdf", b"fake pdf bytes", "doc.pdf")

    assert result == "Extracted PDF text"
    assert mock_pdf_extract.called


@patch("squirro_search.Document")
def test_extract_from_docx(mock_document_class):
    """Test extracting text from DOCX"""
    mock_doc = Mock()
    mock_paragraph1 = Mock()
    mock_paragraph1.text = "First paragraph"
    mock_paragraph2 = Mock()
    mock_paragraph2.text = "Second paragraph"
    mock_doc.paragraphs = [mock_paragraph1, mock_paragraph2]
    mock_document_class.return_value = mock_doc

    result = squirro_search._extract_text(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        b"fake docx bytes",
        "doc.docx",
    )

    assert result == "First paragraph\nSecond paragraph"


def test_extract_from_text_fallback():
    """Test fallback to UTF-8 decoding for unknown types"""
    result = squirro_search._extract_text("text/plain", b"Plain text content", "doc.txt")
    assert result == "Plain text content"


def test_extract_invalid_utf8():
    """Test handling of non-UTF8 content"""
    result = squirro_search._extract_text(
        "application/unknown", b"\xff\xfe invalid utf8", "unknown.bin"
    )
    # Should not raise an error, might return replacement chars
    assert isinstance(result, str)


# Tests for _find_relevant_chunks


def test_find_chunks_with_matches():
    """Test finding chunks with query matches"""
    text = (
        "This is some text before the match. "
        "Here is information about RTGS payment systems and their operation. "
        "More text after. "
        "Another mention of RTGS in a different context. "
        "Final text."
    )

    chunks = squirro_search._find_relevant_chunks(text, "RTGS payment", window=50, max_chunks=2)

    assert len(chunks) == 2
    assert "RTGS" in chunks[0]
    assert "payment" in chunks[0]


def test_find_chunks_no_matches():
    """Test when no matches are found"""
    text = "This text contains no relevant terms."
    chunks = squirro_search._find_relevant_chunks(text, "RTGS payment", window=50, max_chunks=5)
    assert len(chunks) == 0


def test_find_chunks_empty_query():
    """Test with empty query"""
    text = "Some text here"
    chunks = squirro_search._find_relevant_chunks(text, "", window=50, max_chunks=5)
    assert len(chunks) == 0


def test_find_chunks_empty_text():
    """Test with empty text"""
    chunks = squirro_search._find_relevant_chunks("", "query", window=50, max_chunks=5)
    assert len(chunks) == 0


def test_find_chunks_respects_max_chunks():
    """Test that max_chunks limit is respected"""
    text = "RTGS " * 100  # Many matches
    chunks = squirro_search._find_relevant_chunks(text, "RTGS", window=10, max_chunks=3)
    assert len(chunks) <= 3


def test_find_chunks_case_insensitive():
    """Test case-insensitive matching"""
    text = "Information about rtgs and RTGS and Rtgs systems"
    chunks = squirro_search._find_relevant_chunks(text, "RTGS", window=50, max_chunks=5)
    assert len(chunks) > 0


# Tests for main search_squirro function


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.SquirroClient", MockSquirroClient)
def test_search_basic_query():
    """Test basic search query without file content"""
    result = squirro_search.search_squirro(
        query="test query", max_results=10, include_file_content=False
    )

    assert result["query"] == "test query"
    assert result["total_count"] == 2
    assert result["returned_count"] == 2
    assert len(result["results"]) == 2
    assert result["has_more"] is False


@patch.dict(os.environ, {}, clear=True)
@patch("squirro_search.pdf_extract_text", Mock())
@patch("squirro_search.Document", Mock())
def test_search_missing_env_vars():
    """Test error when environment variables are missing"""
    with pytest.raises(ValueError, match="SQUIRRO_BASE_URL"):
        squirro_search.search_squirro("test query")


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.pdf_extract_text", Mock())
@patch("squirro_search.Document", Mock())
def test_search_invalid_parameters():
    """Test validation of invalid parameters"""
    # Empty query
    with pytest.raises(ValueError, match="query parameter cannot be empty"):
        squirro_search.search_squirro("")

    # Invalid max_results
    with pytest.raises(ValueError, match="max_results must be between"):
        squirro_search.search_squirro("query", max_results=0)

    with pytest.raises(ValueError, match="max_results must be between"):
        squirro_search.search_squirro("query", max_results=101)

    # Invalid abstract_size
    with pytest.raises(ValueError, match="abstract_size must be between"):
        squirro_search.search_squirro("query", abstract_size=10)

    # Invalid chunk_window
    with pytest.raises(ValueError, match="chunk_window must be between"):
        squirro_search.search_squirro("query", chunk_window=10)

    # Invalid max_chunks_per_result
    with pytest.raises(ValueError, match="max_chunks_per_result must be between"):
        squirro_search.search_squirro("query", max_chunks_per_result=0)


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.SquirroClient", MockSquirroClient)
def test_search_with_date_filters():
    """Test search with date filters"""
    result = squirro_search.search_squirro(
        query="test",
        created_after="2025-01-01",
        created_before="2025-12-31",
        include_file_content=False,
    )

    assert result is not None
    assert result["query"] == "test"


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.SquirroClient", MockSquirroClient)
def test_search_pagination():
    """Test pagination parameters"""
    result = squirro_search.search_squirro(
        query="test", max_results=1, start=0, include_file_content=False
    )

    # Check pagination fields exist
    assert "start" in result
    assert "has_more" in result
    assert result["start"] == 0


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.SquirroClient", MockSquirroClient)
def test_search_result_structure():
    """Test that result structure contains all expected fields"""
    result = squirro_search.search_squirro(query="test", include_file_content=False)

    # Check top-level structure
    assert "query" in result
    assert "total_count" in result
    assert "returned_count" in result
    assert "start" in result
    assert "has_more" in result
    assert "results" in result

    # Check first result structure
    if result["results"]:
        first_result = result["results"][0]
        assert "id" in first_result
        assert "title" in first_result
        assert "abstract" in first_result
        assert "score" in first_result
        assert "created_at" in first_result
        assert "modified_at" in first_result
        assert "keywords" in first_result


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.SquirroClient", MockSquirroClient)
@patch("squirro_search.pdf_extract_text", Mock())
@patch("squirro_search.Document", Mock())
@patch("squirro_search._fetch_file_bytes")
@patch("squirro_search._extract_text")
def test_search_with_file_content(mock_extract, mock_fetch):
    """Test search with file content extraction"""
    mock_fetch.return_value = b"fake pdf bytes"
    mock_extract.return_value = "Extracted text with RTGS payment information here"

    result = squirro_search.search_squirro(
        query="RTGS",
        max_results=1,
        include_file_content=True,
        chunk_window=50,
        max_chunks_per_result=3,
    )

    # First result should have file_info and content
    first_result = result["results"][0]
    assert "file_info" in first_result
    assert "content" in first_result

    content = first_result["content"]
    assert "full_text_preview" in content
    assert "relevant_chunks" in content
    assert "extraction_status" in content
    assert content["extraction_status"] == "success"


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.SquirroClient", MockSquirroClient)
@patch("squirro_search.pdf_extract_text", Mock())
@patch("squirro_search.Document", Mock())
@patch("squirro_search._fetch_file_bytes")
def test_search_file_extraction_error(mock_fetch):
    """Test handling of file extraction errors"""
    mock_fetch.side_effect = Exception("Network error")

    result = squirro_search.search_squirro(query="test", max_results=1, include_file_content=True)

    # Should still return results, with error in content
    first_result = result["results"][0]
    if "content" in first_result:
        assert "error" in first_result["content"]["extraction_status"]


# Tests for dependency checks


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.SquirroClient", None)
def test_missing_squirro_client():
    """Test error when SquirroClient is not installed"""
    with pytest.raises(ImportError, match="squirro_client"):
        squirro_search.search_squirro("test")


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.SquirroClient", MockSquirroClient)
@patch("squirro_search.requests", None)
def test_missing_requests():
    """Test error when requests is not installed"""
    with pytest.raises(ImportError, match="requests"):
        squirro_search.search_squirro("test")


# Tests for concurrency and thread safety


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.SquirroClient", MockSquirroClient)
def test_concurrent_searches_thread_safety():
    """Test that multiple concurrent searches work without interference"""

    def run_search(query_num):
        """Run a search with a unique query"""
        query = f"test query {query_num}"
        result = squirro_search.search_squirro(
            query=query, max_results=10, include_file_content=False
        )
        # Verify the result matches our query
        assert result["query"] == query
        assert result["total_count"] == 2
        assert result["returned_count"] == 2
        return result

    # Run 10 searches concurrently using threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(run_search, i) for i in range(10)]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    # All searches should complete successfully
    assert len(results) == 10

    # Verify each result has the correct structure
    for result in results:
        assert "query" in result
        assert "total_count" in result
        assert "results" in result


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.SquirroClient", MockSquirroClient)
@patch("squirro_search._fetch_file_bytes")
@patch("squirro_search._extract_text")
@patch("squirro_search.pdf_extract_text", Mock())
@patch("squirro_search.Document", Mock())
def test_concurrent_searches_with_file_content(mock_extract, mock_fetch):
    """Test concurrent searches with file content extraction"""

    # Mock different responses for different threads
    mock_fetch.return_value = b"fake pdf bytes"

    def extract_text_with_thread_id(*args, **kwargs):
        """Return different text based on thread to verify isolation"""
        thread_id = threading.current_thread().ident
        return f"Extracted text from thread {thread_id} with RTGS payment information"

    mock_extract.side_effect = extract_text_with_thread_id

    def run_search_with_content(query_num):
        """Run a search with file content extraction"""
        result = squirro_search.search_squirro(
            query=f"RTGS {query_num}",
            max_results=1,
            include_file_content=True,
            chunk_window=50,
            max_chunks_per_result=3,
        )
        # Verify structure
        assert "results" in result
        if result["results"] and "content" in result["results"][0]:
            assert result["results"][0]["content"]["extraction_status"] == "success"
        return result

    # Run 20 searches concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(run_search_with_content, i) for i in range(20)]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    # All searches should complete successfully
    assert len(results) == 20


def test_helper_functions_thread_safety():
    """Test that helper functions are thread-safe and stateless"""

    def test_choose_best_file():
        files = [{"mime_type": "application/pdf", "link": "/doc.pdf", "filename": "doc.pdf"}]
        return squirro_search._choose_best_file(files)

    def test_filename_hint():
        return squirro_search._filename_hint({"filename": "test.pdf"})

    def test_find_chunks():
        text = "This is RTGS payment system information " * 10
        return squirro_search._find_relevant_chunks(text, "RTGS payment", window=50, max_chunks=3)

    # Run helper functions concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        # Mix different helper function calls
        futures = []
        for i in range(10):
            futures.append(executor.submit(test_choose_best_file))
            futures.append(executor.submit(test_filename_hint))
            futures.append(executor.submit(test_find_chunks))

        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    # All should complete without errors
    assert len(results) == 30


@patch.dict(
    os.environ,
    {
        "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
        "SQUIRRO_REFRESH_TOKEN": "test_token",
        "SQUIRRO_PROJECT_ID": "project123",
    },
)
@patch("squirro_search.SquirroClient", MockSquirroClient)
def test_concurrent_searches_different_parameters():
    """Test concurrent searches with different parameter combinations"""

    def run_search_with_params(params):
        """Run search with specific parameters"""
        query, max_results, start, highlight = params
        result = squirro_search.search_squirro(
            query=query,
            max_results=max_results,
            start=start,
            highlight=highlight,
            include_file_content=False,
        )
        # Verify parameters were used correctly
        assert result["query"] == query
        assert result["start"] == start
        return result

    # Create different parameter combinations
    param_sets = [(f"query_{i}", 5, i, i % 2 == 0) for i in range(15)]

    # Run all searches concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(run_search_with_params, params) for params in param_sets]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    # All searches should complete successfully
    assert len(results) == 15


def test_no_global_state_modification():
    """Verify that the module doesn't use or modify any global state"""
    import sys

    # Get module globals before
    module = sys.modules["squirro_search"]
    initial_globals = {k: v for k, v in vars(module).items() if not k.startswith("__")}

    # Run some operations
    with patch.dict(
        os.environ,
        {
            "SQUIRRO_BASE_URL": "https://test.squirro.cloud/",
            "SQUIRRO_REFRESH_TOKEN": "test_token",
            "SQUIRRO_PROJECT_ID": "project123",
        },
    ):
        with patch("squirro_search.SquirroClient", MockSquirroClient):
            for i in range(5):
                squirro_search.search_squirro(query=f"test {i}", include_file_content=False)

    # Get module globals after
    final_globals = {k: v for k, v in vars(module).items() if not k.startswith("__")}

    # Compare - should be identical (same objects)
    assert set(initial_globals.keys()) == set(final_globals.keys())

    # Verify no new global variables were added
    for key in initial_globals:
        if callable(initial_globals[key]):
            # Functions should be the same object
            assert initial_globals[key] is final_globals[key]
        elif key in ["requests", "SquirroClient", "pdf_extract_text", "Document"]:
            # Module imports might be different due to mocking, that's ok
            continue
        else:
            # Other values should be identical
            assert initial_globals[key] is final_globals[key]
