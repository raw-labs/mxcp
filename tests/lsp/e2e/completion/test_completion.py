import pytest
from lsprotocol.types import (
    CompletionList,
    CompletionParams,
    Position,
    TextDocumentIdentifier,
)
from pytest_lsp import LanguageClient
from pathlib import Path


@pytest.mark.asyncio
async def test_completions(client: LanguageClient):
    """Ensure that the server implements completions correctly."""

    # Reference the file from the isolated e2e config directory
    uri = Path("./tool_with_inlined_code.yml").resolve().as_uri()
    results = await client.text_document_completion_async(
        params=CompletionParams(
            position=Position(line=21, character=8),
            text_document=TextDocumentIdentifier(uri=uri),
        )
    )
    assert results is not None
    assert any(
        item.label == "min_magnitude" for item in results.items
    ), "'min_magnitude' should be in completion items"
