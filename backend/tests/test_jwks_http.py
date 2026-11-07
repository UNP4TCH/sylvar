"""JWKS HTTP transport tests using httpx.MockTransport (no network). Needs httpx installed."""
import asyncio

import httpx

from app.core.security.jwks_http import make_http_fetcher

URL = "https://example-project.invalid/auth/v1/.well-known/jwks.json"


def _fetch(handler):  # type: ignore[no-untyped-def]
    fetcher = make_http_fetcher(URL, 1.0, transport=httpx.MockTransport(handler))
    return asyncio.run(fetcher())


def _raises(handler) -> bool:  # type: ignore[no-untyped-def]
    try:
        _fetch(handler)
    except Exception:  # noqa: BLE001 - any failure is acceptable here; the provider fails closed
        return True
    return False


def test_returns_parsed_json_object_and_requests_the_configured_url() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"keys": []})

    assert _fetch(handler) == {"keys": []}
    assert seen == [URL]


def test_http_error_status_raises() -> None:
    assert _raises(lambda r: httpx.Response(500))
    assert _raises(lambda r: httpx.Response(404))


def test_redirects_are_not_followed() -> None:
    assert _raises(lambda r: httpx.Response(302, headers={"location": "https://evil.invalid/"}))


def test_non_object_json_raises() -> None:
    assert _raises(lambda r: httpx.Response(200, json=["not", "an", "object"]))


def test_oversized_response_raises() -> None:
    big = {"keys": [], "pad": "x" * (300 * 1024)}
    assert _raises(lambda r: httpx.Response(200, json=big))


def test_invalid_json_raises() -> None:
    assert _raises(lambda r: httpx.Response(200, content=b"<html>nope</html>"))
