#!/usr/bin/env python3
"""End-to-end verifier-mode test using Keycloak + MXCP HTTP API.

This script:
1) fetches OIDC discovery
2) obtains an access token via password grant
3) starts mxcp serve (streamable-http)
4) calls get_user_info with Authorization header
5) asserts expected user context based on EXPECTED_MODE
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
import asyncio
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
import subprocess
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


@dataclass
class EnvConfig:
    keycloak_server_url: str
    keycloak_realm: str
    keycloak_client_id: str
    keycloak_client_secret: str
    keycloak_username: str
    keycloak_password: str
    mxcp_url: str
    mxcp_project_dir: str
    mxcp_config: str | None
    mxcp_tool_name: str
    expected_mode: str
    expected_email: str | None
    expected_provider: str | None
    ready_timeout_sec: float


def _env(name: str, required: bool = False, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def load_config() -> EnvConfig:
    return EnvConfig(
        keycloak_server_url=_env("KEYCLOAK_SERVER_URL", required=True) or "",
        keycloak_realm=_env("KEYCLOAK_REALM", required=True) or "",
        keycloak_client_id=_env("KEYCLOAK_CLIENT_ID", required=True) or "",
        keycloak_client_secret=_env("KEYCLOAK_CLIENT_SECRET", required=True) or "",
        keycloak_username=_env("KEYCLOAK_USERNAME", required=True) or "",
        keycloak_password=_env("KEYCLOAK_PASSWORD", required=True) or "",
        mxcp_url=_env("MXCP_URL", default="http://localhost:8000") or "http://localhost:8000",
        mxcp_project_dir=_env("MXCP_PROJECT_DIR", default="examples/oidc") or "examples/oidc",
        mxcp_config=_env("MXCP_CONFIG"),
        mxcp_tool_name=_env("MXCP_TOOL_NAME", default="get_user_info") or "get_user_info",
        expected_mode=_env("EXPECTED_MODE", default="verifier") or "verifier",
        expected_email=_env("EXPECTED_EMAIL"),
        expected_provider=_env("EXPECTED_PROVIDER"),
        ready_timeout_sec=float(_env("MXCP_READY_TIMEOUT", default="10") or "10"),
    )


def fetch_discovery(base_url: str, realm: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/realms/{realm}/.well-known/openid-configuration"
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"Discovery fetch failed: {resp.status_code}")
        return resp.json()


def fetch_token(token_url: str, config: EnvConfig) -> str:
    payload = {
        "grant_type": "password",
        "client_id": config.keycloak_client_id,
        "client_secret": config.keycloak_client_secret,
        "username": config.keycloak_username,
        "password": config.keycloak_password,
        "scope": "openid profile email",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(token_url, data=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Token request failed: {resp.status_code}")
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError("Token response missing access_token")
        return token


def _parse_port(mxcp_url: str) -> int:
    parsed = urlparse(mxcp_url)
    if parsed.port:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    return 80


def _stream_output(pipe, out, buffer: deque[str], label: str) -> None:
    for line in iter(pipe.readline, ""):
        out.write(line)
        out.flush()
        buffer.append(f"{label}{line}")


def start_mxcp(config: EnvConfig, log_buffer: deque[str]) -> subprocess.Popen[str]:
    port = _parse_port(config.mxcp_url)
    env = os.environ.copy()
    if not env.get("MXCP_CONFIG"):
        # Prefer explicit env, else default to config.yml in project dir
        env["MXCP_CONFIG"] = config.mxcp_config or "config.yml"
    cmd = [
        "mxcp",
        "serve",
        "--transport",
        "streamable-http",
        "--port",
        str(port),
        "--debug",
    ]
    proc = subprocess.Popen(
        cmd,
        env=env,
        cwd=config.mxcp_project_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None
    threading.Thread(
        target=_stream_output,
        args=(proc.stdout, sys.stdout, log_buffer, ""),
        daemon=True,
    ).start()
    threading.Thread(
        target=_stream_output,
        args=(proc.stderr, sys.stderr, log_buffer, ""),
        daemon=True,
    ).start()
    return proc


def _extract_tool_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "structuredContent") and result.structuredContent is not None:
        structured = result.structuredContent
        if isinstance(structured, dict) and "result" in structured:
            return structured["result"]
        if isinstance(structured, dict):
            return structured

    if hasattr(result, "content") and isinstance(result.content, list) and result.content:
        content = result.content[0]
        if hasattr(content, "type") and content.type == "text" and hasattr(content, "text"):
            try:
                return json.loads(content.text)
            except Exception:
                return {"result": content.text}

    if hasattr(result, "isError") and result.isError:
        return {"result": f"Error executing tool: {result}"}

    return {"result": str(result)}


async def call_tool_via_mcp(mxcp_url: str, tool_name: str, token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{mxcp_url.rstrip('/')}/mcp/"
    async with streamablehttp_client(url, headers=headers) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, {})
            return _extract_tool_result(result)


async def wait_for_mcp_and_call(
    mxcp_url: str,
    tool_name: str,
    token: str,
    timeout_sec: float,
    proc: subprocess.Popen[str] | None,
    log_buffer: deque[str],
) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last_error: Exception | None = None
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            tail = "".join(list(log_buffer)[-200:])
            raise RuntimeError(
                f"MXCP exited early (code {proc.returncode}). Recent output:\n{tail}"
            )
        try:
            return await call_tool_via_mcp(mxcp_url, tool_name, token)
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.5)
    raise RuntimeError(f"MXCP did not become ready in {timeout_sec}s (last error: {last_error})")


def assert_result(result: dict[str, Any], config: EnvConfig) -> None:
    username = result.get("username")
    email = result.get("email")
    provider = result.get("provider")

    if config.expected_mode == "none":
        if any(value is not None for value in (username, email, provider)):
            raise RuntimeError(
                f"Expected null user info, got username={username}, email={email}, provider={provider}"
            )
        return

    if not username:
        raise RuntimeError("Expected non-null username")
    if not email:
        raise RuntimeError("Expected non-null email")
    if config.expected_provider is not None and provider != config.expected_provider:
        raise RuntimeError(f"Expected provider {config.expected_provider}, got {provider}")
    if config.expected_email is not None and email != config.expected_email:
        raise RuntimeError(f"Expected email {config.expected_email}, got {email}")


def main() -> int:
    config = load_config()

    discovery = fetch_discovery(config.keycloak_server_url, config.keycloak_realm)
    token_url = discovery.get("token_endpoint")
    if not token_url:
        raise RuntimeError("Discovery response missing token_endpoint")

    token = fetch_token(token_url, config)

    proc: subprocess.Popen[str] | None = None
    log_buffer: deque[str] = deque(maxlen=400)
    try:
        proc = start_mxcp(config, log_buffer)
        result = asyncio.run(
            wait_for_mcp_and_call(
                config.mxcp_url,
                config.mxcp_tool_name,
                token,
                config.ready_timeout_sec,
                proc,
                log_buffer,
            )
        )
        assert_result(result, config)
        print("OK: verifier e2e")
        return 0
    finally:
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=10)
            except Exception:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
