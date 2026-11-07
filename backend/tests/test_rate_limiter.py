"""Tests for SlowAPI Rate Limiting & RFC 9457 formatting (TASK-035)."""
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.errors import install_error_handlers


def test_rate_limit_exceeded_handler_returns_rfc9457_problem_details():
    limiter = Limiter(key_func=get_remote_address)
    app = FastAPI()
    app.state.limiter = limiter
    install_error_handlers(app)

    @app.get("/limited")
    @limiter.limit("1/minute")
    async def limited_route(request: Request):
        return {"status": "ok"}

    client = TestClient(app, raise_server_exceptions=False)
    # 1st call: OK
    r1 = client.get("/limited")
    assert r1.status_code == 200

    # 2nd call: Rate Limit Exceeded (429 Problem Details)
    r2 = client.get("/limited")
    assert r2.status_code == 429
    assert r2.headers["content-type"].startswith("application/problem+json")
    assert r2.headers["retry-after"] == "60"
    data = r2.json()
    assert data["code"] == "RATE_LIMIT_EXCEEDED"
    assert data["status"] == 429
    assert "1 per 1 minute" in data["detail"]
