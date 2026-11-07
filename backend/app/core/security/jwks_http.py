"""HTTP transport for JWKS. Separate module so the verifier core has no network dependency."""
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

_MAX_BYTES = 256 * 1024


def make_http_fetcher(
    url: str,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None = None,  # injectable for tests only
) -> Callable[[], Awaitable[dict[str, Any]]]:
    async def fetch() -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, follow_redirects=False, transport=transport
        ) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            if len(response.content) > _MAX_BYTES:
                raise ValueError("JWKS response too large")
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("JWKS response is not an object")  # noqa: TRY004
            return data

    return fetch
