"""HTTP-level auth tests (FastAPI TestClient). Requires fastapi/httpx installed locally."""
import time

from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.security.jwt_verifier import AuthenticatedUser
from app.main import create_app
from app.modules.auth.dependencies import get_current_user
from tests.jwt_helpers import USER_ID, FakeJWKS, TestKey, make_verifier
from tests.settings_helpers import clean_settings

KEY = TestKey("kid-1", "EC")


def _client(verifier=None) -> TestClient:  # type: ignore[no-untyped-def]
    app = create_app(clean_settings(), jwt_verifier=verifier)

    @app.get("/api/v1/_test/whoami")
    async def whoami(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, str]:
        return {"user_id": str(user.user_id)}

    return TestClient(app, raise_server_exceptions=False)


def test_valid_token_resolves_user_id() -> None:
    c = _client(make_verifier(FakeJWKS(KEY)))
    r = c.get("/api/v1/_test/whoami", headers={"Authorization": f"Bearer {KEY.token()}"})
    assert r.status_code == 200
    assert r.json() == {"user_id": USER_ID}


def test_missing_token_is_401_problem_details() -> None:
    r = _client(make_verifier(FakeJWKS(KEY))).get("/api/v1/_test/whoami")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "TOKEN_MISSING"


def test_expired_token_is_401() -> None:
    token = KEY.token(exp=int(time.time()) - 60)
    r = _client(make_verifier(FakeJWKS(KEY))).get(
        "/api/v1/_test/whoami", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_EXPIRED"


def test_garbage_token_is_401_and_not_echoed() -> None:
    r = _client(make_verifier(FakeJWKS(KEY))).get(
        "/api/v1/_test/whoami", headers={"Authorization": "Bearer garbage.token.value"}
    )
    assert r.status_code == 401
    assert "garbage" not in r.text


def test_non_bearer_scheme_is_401() -> None:
    r = _client(make_verifier(FakeJWKS(KEY))).get(
        "/api/v1/_test/whoami", headers={"Authorization": "Basic abc"}
    )
    assert r.status_code == 401


def test_unconfigured_auth_fails_closed_503() -> None:
    r = _client(None).get(
        "/api/v1/_test/whoami", headers={"Authorization": f"Bearer {KEY.token()}"}
    )
    assert r.status_code == 503 and r.json()["code"] == "AUTH_NOT_CONFIGURED"


def test_jwks_outage_is_503_not_200() -> None:
    src = FakeJWKS(KEY)
    src.fail = True
    r = _client(make_verifier(src)).get(
        "/api/v1/_test/whoami", headers={"Authorization": f"Bearer {KEY.token()}"}
    )
    assert r.status_code == 503 and r.json()["code"] == "JWKS_UNAVAILABLE"


def test_health_stays_public_without_auth_configured() -> None:
    assert _client(None).get("/api/v1/health").json() == {"status": "alive"}
