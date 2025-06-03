import pytest
from lsprotocol.types import (
    SemanticTokens,
    SemanticTokensParams,
    TextDocumentIdentifier,
    Position,
)
from pytest_lsp import LanguageClient
from pathlib import Path


@pytest.mark.asyncio
async def test_semantic_tokens_basic(client: LanguageClient):
    """Test basic semantic token functionality with a simple SQL query."""
    # Arrange - Reference file from isolated e2e config directory
    uri = Path("./tool_with_inlined_code.yml").resolve().as_uri()

    # Act
    result = await client.text_document_semantic_tokens_full_async(
        params=SemanticTokensParams(text_document=TextDocumentIdentifier(uri=uri))
    )

    # Assert
    assert result is not None
    assert isinstance(result, SemanticTokens)
    assert len(result.data) > 0, "Should return some semantic tokens"

    # Verify token data format: [line, offset, length, token_type, token_modifiers]
    for i in range(0, len(result.data), 5):
        line, offset, length, token_type, modifiers = result.data[i : i + 5]
        assert isinstance(line, int), "Line should be an integer"
        assert isinstance(offset, int), "Offset should be an integer"
        assert isinstance(length, int), "Length should be an integer"
        assert isinstance(token_type, int), "Token type should be an integer"
        assert isinstance(modifiers, int), "Modifiers should be an integer"


@pytest.mark.asyncio
async def test_semantic_tokens_keywords(client: LanguageClient):
    """Test that SQL keywords are properly tokenized."""
    uri = Path("./tool_with_inlined_code.yml").resolve().as_uri()

    result = await client.text_document_semantic_tokens_full_async(
        params=SemanticTokensParams(text_document=TextDocumentIdentifier(uri=uri))
    )

    assert result is not None
    # Find a token that should be a keyword (e.g., SELECT, FROM, WHERE)
    keyword_indices = [
        i for i in range(0, len(result.data), 5) if result.data[i + 3] == 0
    ]  # Assuming 0 is the index for keyword type

    assert len(keyword_indices) > 0, "Should find at least one keyword token"


@pytest.mark.asyncio
async def test_semantic_tokens_multiline(client: LanguageClient):
    """Test semantic tokens in a multiline SQL query."""
    uri = Path("./tool_with_inlined_code.yml").resolve().as_uri()

    result = await client.text_document_semantic_tokens_full_async(
        params=SemanticTokensParams(text_document=TextDocumentIdentifier(uri=uri))
    )

    assert result is not None
    # Verify that we have tokens on different lines
    lines = set(result.data[i] for i in range(0, len(result.data), 5))
    assert len(lines) > 1, "Should have tokens on multiple lines"


@pytest.mark.asyncio
async def test_semantic_tokens_empty_document(client: LanguageClient):
    """Test semantic tokens with an empty document."""
    # Create a temporary empty YAML file in the e2e config directory
    empty_yaml = """
mxcp: 1.0.0
tool:
  name: "empty_tool"
  source:
    code: |
    # Empty code block
"""
    uri = Path("./empty_tool.yml").resolve().as_uri()

    # Write the empty YAML to a file in the e2e config directory
    with open("./empty_tool.yml", "w") as f:
        f.write(empty_yaml)

    try:
        result = await client.text_document_semantic_tokens_full_async(
            params=SemanticTokensParams(text_document=TextDocumentIdentifier(uri=uri))
        )

        assert result is not None
        assert len(result.data) == 0, "Empty document should return no tokens"
    finally:
        # Clean up the temporary file
        Path("./empty_tool.yml").unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_semantic_tokens_invalid_sql(client: LanguageClient):
    """Test semantic tokens with invalid SQL syntax."""
    # Create a temporary YAML file with invalid SQL in the e2e config directory
    invalid_sql_yaml = """
mxcp: 1.0.0
tool:
  name: "invalid_sql_tool"
  source:
    code: |
      SELECT * FROM WHERE INVALID SQL SYNTAX
"""
    uri = Path("./invalid_sql_tool.yml").resolve().as_uri()

    # Write the invalid SQL YAML to a file in the e2e config directory
    with open("./invalid_sql_tool.yml", "w") as f:
        f.write(invalid_sql_yaml)

    try:
        result = await client.text_document_semantic_tokens_full_async(
            params=SemanticTokensParams(text_document=TextDocumentIdentifier(uri=uri))
        )

        assert result is not None
        # Even with invalid SQL, we should still get some tokens
        assert len(result.data) > 0, "Should still tokenize invalid SQL"
    finally:
        # Clean up the temporary file
        Path("./invalid_sql_tool.yml").unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_semantic_tokens_positions(client: LanguageClient):
    """Test that token positions are correctly adjusted based on the code section's position in the YAML file."""
    # Arrange
    uri = Path("./tool_with_inlined_code.yml").resolve().as_uri()

    # Act
    result = await client.text_document_semantic_tokens_full_async(
        params=SemanticTokensParams(text_document=TextDocumentIdentifier(uri=uri))
    )

    # Assert
    assert result is not None
    assert isinstance(result, SemanticTokens)
    assert len(result.data) > 0, "Should return some semantic tokens"

    # First token (WITH) - absolute position since it's the first token
    line, offset, length, token_type, modifiers = result.data[0:5]
    assert line == 17, "First token line should be 17 (absolute position, 0-based)"
    assert offset == 6, "First token offset should be 6 (absolute position)"
    assert length == 4, "First token length should be 4"
    assert token_type == 0, "First token type should be 0 (keyword)"

    # Second token (raw) - relative to first token
    line, offset, length, token_type, modifiers = result.data[5:10]
    assert line == 0, "Second token line should be 0 (same line as previous)"
    assert offset == 5, "Second token offset should be 5 (relative to end of 'WITH')"
    assert length == 3, "Second token length should be 3"
    assert token_type == 7, "Second token type should be 7 (identifier)"

    # Third token (AS) - relative to second token
    line, offset, length, token_type, modifiers = result.data[10:15]
    assert line == 0, "Third token line should be 0 (same line as previous)"
    assert offset == 4, "Third token offset should be 4 (relative to end of 'raw')"
    assert length == 2, "Third token length should be 2"
    assert token_type == 0, "Third token type should be 0 (keyword)"

    # Fourth token (() - relative to third token
    line, offset, length, token_type, modifiers = result.data[15:20]
    assert line == 0, "Fourth token line should be 0 (same line as previous)"
    assert offset == 3, "Fourth token offset should be 3 (relative to end of 'AS')"
    assert length == 1, "Fourth token length should be 1"
    assert token_type == 5, "Fourth token type should be 5 (operator)"

    # Fifth token (SELECT) - relative to fourth token
    line, offset, length, token_type, modifiers = result.data[20:25]
    assert line == 1, "Fifth token line should be 0 (same line as previous)"
    assert offset == 8, "Fifth token offset should be 8 (relative to end of '(')"
    assert length == 6, "Fifth token length should be 6"
    assert token_type == 0, "Fifth token type should be 0 (keyword)"
