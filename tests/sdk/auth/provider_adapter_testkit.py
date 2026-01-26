"""Test utilities for ProviderAdapter tests.

This module exists to keep provider adapter tests consistent and reduce copy/paste.
It provides a minimal async HTTP client fake matching the shape used by provider
adapters via `create_mcp_http_client()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FakeResponse:
    status_code: int
    payload: Any
    text: str = ""

    def json(self) -> Any:
        return self.payload


@dataclass(frozen=True)
class FakeResponseJsonError(FakeResponse):
    def json(self) -> Any:  # pragma: no cover
        raise ValueError("invalid json")


class FakeAsyncHttpClient:
    """Minimal async context manager used by provider adapters.

    - `post()` returns `post_response`
    - `get()` routes responses by substring match on URL (first match wins)
    - Tracks simple call counts to help with assertions when needed
    """

    def __init__(
        self,
        *,
        post_response: FakeResponse,
        get_responses: dict[str, FakeResponse] | None = None,
        default_get_response: FakeResponse | None = None,
    ) -> None:
        self._post_response = post_response
        self._get_responses = dict(get_responses or {})
        self._default_get_response = default_get_response or FakeResponse(200, {})
        self.post_calls = 0
        self.get_calls = 0
        self.get_calls_by_route: dict[str, int] = {}

    async def __aenter__(self) -> "FakeAsyncHttpClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool:
        return False

    async def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
        self.post_calls += 1
        return self._post_response

    async def get(self, *args: Any, **kwargs: Any) -> FakeResponse:
        self.get_calls += 1
        url = args[0] if args else ""
        url_str = str(url)
        for route_substring, resp in self._get_responses.items():
            if route_substring in url_str:
                self.get_calls_by_route[route_substring] = (
                    self.get_calls_by_route.get(route_substring, 0) + 1
                )
                return resp
        return self._default_get_response


def patch_http_client(monkeypatch: Any, create_client_path: str, fake_client: Any) -> None:
    """Patch a provider adapter module's `create_mcp_http_client`."""

    monkeypatch.setattr(create_client_path, lambda: fake_client)

