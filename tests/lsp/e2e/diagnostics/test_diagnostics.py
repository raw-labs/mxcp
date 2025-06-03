import pytest
from lsprotocol.types import (
    TextDocumentIdentifier,
    DidOpenTextDocumentParams,
    TextDocumentItem,
    DidCloseTextDocumentParams,
    TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS,
)
from pytest_lsp import LanguageClient
from pathlib import Path
import asyncio


@pytest.mark.asyncio
async def test_diagnostics_invalid_sql(client: LanguageClient):
    """Test that invalid SQL generates diagnostics"""
    
    # Reference the file with invalid SQL
    uri = Path("./tool_with_invalid_sql.yml").resolve().as_uri()
    
    # Read the file content
    with open("./tool_with_invalid_sql.yml", "r") as f:
        content = f.read()
    
    # Start waiting for diagnostics before opening the document
    diagnostics_task = asyncio.create_task(
        client.wait_for_notification(TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    )
    
    # Open the document to trigger diagnostics
    client.text_document_did_open(
        DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri=uri,
                language_id="yaml",
                version=1,
                text=content
            )
        )
    )
    
    # Wait for diagnostics notification to be received
    await diagnostics_task
    
    # Check if diagnostics were published
    assert uri in client.diagnostics, "Diagnostics should be published for invalid SQL"
    diagnostics = client.diagnostics[uri]
    
    # Should have at least one diagnostic for the invalid SQL
    assert len(diagnostics) > 0, "Should have diagnostics for invalid SQL"
    
    # Check that at least one diagnostic is related to SQL error
    has_sql_error = any(
        "syntax" in diagnostic.message.lower() or 
        "error" in diagnostic.message.lower() or
        "invalid" in diagnostic.message.lower()
        for diagnostic in diagnostics
    )
    assert has_sql_error, "Should have SQL syntax error diagnostics"
    
    # Close the document
    client.text_document_did_close(
        DidCloseTextDocumentParams(
            text_document=TextDocumentIdentifier(uri=uri)
        )
    )


@pytest.mark.asyncio 
async def test_diagnostics_valid_sql(client: LanguageClient):
    """Test that valid SQL does not generate diagnostics (or generates fewer diagnostics)"""
    
    # Reference the file with valid SQL
    uri = Path("./tool_with_inlined_code.yml").resolve().as_uri()
    
    # Read the file content
    with open("./tool_with_inlined_code.yml", "r") as f:
        content = f.read()
    
    # Start waiting for diagnostics before opening the document
    # Use a timeout since valid SQL might not generate any diagnostics
    try:
        diagnostics_task = asyncio.create_task(
            client.wait_for_notification(TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
        )
        
        # Open the document to trigger diagnostics
        client.text_document_did_open(
            DidOpenTextDocumentParams(
                text_document=TextDocumentItem(
                    uri=uri,
                    language_id="yaml", 
                    version=1,
                    text=content
                )
            )
        )
        
        # Wait for diagnostics with a timeout (valid SQL might not generate any)
        await asyncio.wait_for(diagnostics_task, timeout=3.0)
        
        # If we reach here, diagnostics were published
        diagnostics = client.diagnostics.get(uri, [])
        
    except asyncio.TimeoutError:
        # No diagnostics were published within timeout - this is fine for valid SQL
        diagnostics = []
    
    # If there are diagnostics, they should not be severe SQL errors
    if diagnostics:
        severe_sql_errors = [
            d for d in diagnostics 
            if d.severity and d.severity.value <= 2 and (  # Error or Warning severity
                "syntax" in d.message.lower() or 
                "invalid" in d.message.lower()
            )
        ]
        assert len(severe_sql_errors) == 0, f"Valid SQL should not have severe syntax errors, but got: {[d.message for d in severe_sql_errors]}"
    
    # Close the document
    client.text_document_did_close(
        DidCloseTextDocumentParams(
            text_document=TextDocumentIdentifier(uri=uri)
        )
    ) 