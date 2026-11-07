"""Test helpers: locally generated keys, JWKS documents and signed tokens. No real secrets."""
import asyncio
import base64
import time
from collections.abc import Awaitable
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import RSAAlgorithm

from app.core.security.config import JWTConfig
from app.core.security.errors import AuthError
from app.core.security.jwks import JWKSProvider
from app.core.security.jwt_verifier import JWTVerifier

ISSUER = "https://example-project.invalid/auth/v1"
AUDIENCE = "test-audience"
USER_ID = "11111111-2222-4333-8444-555555555555"


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def ec_p256_public_jwk(public_key: ec.EllipticCurvePublicKey) -> dict[str, Any]:
    """RFC 7518 s6.2.1: x/y MUST be full-size (32 bytes) octet strings, leading zeros kept.

    Do NOT use PyJWT 2.7.0 ECAlgorithm.to_jwk here: it strips leading zero bytes, producing a JWK
    that PyJWK rejects for ~0.6% of keys. That helper flaw caused the earlier intermittent failures.
    """
    nums = public_key.public_numbers()
    return {
        "kty": "EC", "crv": "P-256",
        "x": _b64u(nums.x.to_bytes(32, "big")),
        "y": _b64u(nums.y.to_bytes(32, "big")),
    }


class TestKey:
    __test__ = False

    def __init__(self, kid: str, kind: str = "EC") -> None:
        self.kid = kid
        self.kind = kind
        if kind == "EC":
            self.private = ec.generate_private_key(ec.SECP256R1())
            self.alg = "ES256"
            self.jwk: dict[str, Any] = ec_p256_public_jwk(self.private.public_key())
        else:
            self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            self.alg = "RS256"
            self.jwk = RSAAlgorithm.to_jwk(self.private.public_key(), as_dict=True)
        self.jwk.update({"kid": kid, "use": "sig", "alg": self.alg})

    def token(self, **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": USER_ID, "iss": ISSUER, "aud": AUDIENCE, "iat": now - 5, "exp": now + 300,
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self.private, algorithm=self.alg, headers={"kid": self.kid})


def make_config(**overrides: Any) -> JWTConfig:
    base: dict[str, Any] = {
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "jwks_url": ISSUER + "/.well-known/jwks.json",
        "algorithms": ("ES256", "RS256"),
        "leeway_seconds": 0,
        "jwks_cache_ttl_seconds": 600.0,
        "jwks_refresh_cooldown_seconds": 30.0,
    }
    base.update(overrides)
    return JWTConfig(**base)


class FakeJWKS:
    """Scriptable JWKS source that counts fetches."""

    def __init__(self, *keys: TestKey) -> None:
        self.keys = list(keys)
        self.calls = 0
        self.fail = False
        self.delay = 0.0

    async def __call__(self) -> dict[str, Any]:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise ConnectionError("simulated network failure")
        return {"keys": [k.jwk for k in self.keys]}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_verifier(
    source: FakeJWKS, clock: FakeClock | None = None, **cfg: Any
) -> JWTVerifier:
    config = make_config(**cfg)
    provider = JWKSProvider(
        source,
        cache_ttl_seconds=config.jwks_cache_ttl_seconds,
        refresh_cooldown_seconds=config.jwks_refresh_cooldown_seconds,
        clock=clock or FakeClock(),
    )
    return JWTVerifier(config, provider)


def run(coro: Awaitable[Any]) -> Any:
    return asyncio.run(coro)  # type: ignore[arg-type]


def expect_auth_error(coro: Awaitable[Any], code: str, status: int = 401) -> None:
    """Assert the awaitable raises AuthError with the given code/status (no pytest dependency)."""
    try:
        asyncio.run(coro)  # type: ignore[arg-type]
    except AuthError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}"
        assert exc.status == status, f"expected status {status}, got {exc.status}"
        return
    raise AssertionError(f"expected AuthError {code}, but no error was raised")
