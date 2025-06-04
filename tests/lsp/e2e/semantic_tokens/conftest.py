import os
from pathlib import Path

import pytest_lsp
from lsprotocol.types import (
    ClientCapabilities,
    InitializeParams,
)
from pytest_lsp import ClientServerConfig, LanguageClient

# Get the path to the e2e config directory with isolated test configuration
TEST_CONFIG_DIR = Path(__file__).parent.parent.parent / "fixtures" / "e2e-config"

@pytest_lsp.fixture(
    config=ClientServerConfig(
        server_command=["sh", "-c", f"cd {TEST_CONFIG_DIR} && mxcp lsp"],
    ),
)
async def client(lsp_client: LanguageClient):
    # Setup
    params = InitializeParams(capabilities=ClientCapabilities())
    await lsp_client.initialize_session(params)

    yield

    # Teardown
    await lsp_client.shutdown_session()
