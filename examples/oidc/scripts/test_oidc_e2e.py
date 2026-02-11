#!/usr/bin/env python3
"""End-to-end test for the generic OIDC provider using Keycloak as the IdP.

Prerequisites
=============
- A running Keycloak server with **Direct Access Grants** enabled on the client.
- Environment variables:
    KEYCLOAK_SERVER_URL   (e.g. http://localhost:8080)
    KEYCLOAK_REALM        (e.g. demo)
    KEYCLOAK_CLIENT_ID    (e.g. mxcp)
    KEYCLOAK_CLIENT_SECRET
    OIDC_TEST_USERNAME    (e.g. ben)
    OIDC_TEST_PASSWORD    (e.g. Demo1234=)

The script:
1. Constructs the OIDC discovery URL from the Keycloak env vars.
2. Fetches and validates the OIDC discovery document.
3. Obtains an access token via the Resource Owner Password Credentials grant.
4. Starts an MXCP server subprocess with the OIDC example config.
5. Calls the ``get_user_info`` tool through the server.
6. Asserts the returned identity matches the test user.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

EXAMPLE_DIR = Path(__file__).resolve().parent.parent
MXCP_ROOT = EXAMPLE_DIR.parent.parent


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: environment variable {name} is not set", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> None:
    keycloak_url = require_env("KEYCLOAK_SERVER_URL").rstrip("/")
    realm = require_env("KEYCLOAK_REALM")
    client_id = require_env("KEYCLOAK_CLIENT_ID")
    client_secret = require_env("KEYCLOAK_CLIENT_SECRET")
    username = require_env("OIDC_TEST_USERNAME")
    password = require_env("OIDC_TEST_PASSWORD")

    config_url = f"{keycloak_url}/realms/{realm}/.well-known/openid-configuration"
    print(f"[1/6] Fetching OIDC discovery from {config_url}")

    with httpx.Client(timeout=10) as client:
        resp = client.get(config_url)
        resp.raise_for_status()
        discovery = resp.json()
        assert "authorization_endpoint" in discovery, "Missing authorization_endpoint"
        assert "token_endpoint" in discovery, "Missing token_endpoint"
        print(f"  Issuer: {discovery['issuer']}")

    # ── Step 2: Obtain token via Resource Owner Password Credentials ──
    print(f"[2/6] Obtaining access token for user '{username}' via direct grant")
    token_endpoint = discovery["token_endpoint"]

    with httpx.Client(timeout=10) as client:
        resp = client.post(
            token_endpoint,
            data={
                "grant_type": "password",
                "client_id": client_id,
                "client_secret": client_secret,
                "username": username,
                "password": password,
                "scope": "openid profile email",
            },
        )
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data["access_token"]
        print("  Access token obtained")

    # ── Step 3: Start MXCP server ──
    print("[3/6] Starting MXCP server with OIDC config")
    env = {
        **os.environ,
        "OIDC_CONFIG_URL": config_url,
        "OIDC_CLIENT_ID": client_id,
        "OIDC_CLIENT_SECRET": client_secret,
    }

    server_proc = subprocess.Popen(
        [sys.executable, "-m", "mxcp", "serve", "--debug"],
        cwd=str(EXAMPLE_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # ── Step 4: Wait for server readiness ──
    print("[4/6] Waiting for server readiness")
    base_url = "http://localhost:8000"
    ready = False
    for attempt in range(30):
        try:
            with httpx.Client(timeout=2) as client:
                r = client.get(f"{base_url}/health")
                if r.status_code == 200:
                    ready = True
                    break
        except httpx.ConnectError:
            pass
        time.sleep(1)

    if not ready:
        print("ERROR: Server did not become ready in 30 seconds", file=sys.stderr)
        server_proc.send_signal(signal.SIGTERM)
        server_proc.wait(timeout=5)
        sys.exit(1)

    print("  Server is ready")

    try:
        # ── Step 5: Call get_user_info tool ──
        print("[5/6] Calling get_user_info tool")
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "get_user_info",
                        "arguments": {},
                    },
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            result = resp.json()
            print(f"  Response: {json.dumps(result, indent=2)}")

        # ── Step 6: Assert identity ──
        print("[6/6] Validating response")
        tool_result = result.get("result", {})
        content = tool_result.get("content", [{}])
        if content and isinstance(content[0], dict):
            text = content[0].get("text", "")
            data = json.loads(text) if isinstance(text, str) else text
        else:
            data = {}

        # Handle list-of-dicts response format
        if isinstance(data, list) and len(data) > 0:
            data = data[0]

        assert data.get("provider") == "oidc", f"Expected provider=oidc, got {data.get('provider')}"
        assert data.get("username") == username, (
            f"Expected username={username}, got {data.get('username')}"
        )
        print(f"  Username: {data.get('username')}")
        print(f"  Email: {data.get('email')}")
        print(f"  Provider: {data.get('provider')}")
        print("\nAll checks passed!")

    finally:
        print("\nStopping MXCP server...")
        server_proc.send_signal(signal.SIGTERM)
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait()


if __name__ == "__main__":
    main()
