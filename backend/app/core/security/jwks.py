"""JWKS key provider: cached, kid-addressed, with bounded refresh. Fetching is injected."""
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import jwt

from app.core.security.errors import AuthError, AuthUnavailableError

logger = logging.getLogger("sylvar.auth")

JWKSFetcher = Callable[[], Awaitable[dict[str, Any]]]
_SUPPORTED_KTY = frozenset({"RSA", "EC"})
_PRIVATE_MEMBERS = ("d", "p", "q", "dp", "dq", "qi")


def _parse_keys(document: object) -> dict[str, Any]:
    if not isinstance(document, dict) or not isinstance(document.get("keys"), list):
        raise AuthUnavailableError("JWKS_INVALID", "Signing key set is invalid.")
    keys: dict[str, Any] = {}
    for jwk in document["keys"]:
        if not isinstance(jwk, dict):
            continue
        kid = jwk.get("kid")
        if not isinstance(kid, str) or not kid or kid in keys:
            continue
        if jwk.get("kty") not in _SUPPORTED_KTY or jwk.get("use", "sig") != "sig":
            continue
        if any(m in jwk for m in _PRIVATE_MEMBERS):
            logger.warning("Ignoring JWKS entry containing private key material (kid=%s)", kid)
            continue
        try:
            keys[kid] = jwt.PyJWK(jwk).key
        except jwt.PyJWTError:
            logger.warning("Ignoring unparseable JWKS entry (kid=%s)", kid)
    if not keys:
        raise AuthUnavailableError("JWKS_INVALID", "Signing key set contains no usable keys.")
    return keys


class JWKSProvider:
    def __init__(
        self,
        fetcher: JWKSFetcher,
        *,
        cache_ttl_seconds: float,
        refresh_cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetcher = fetcher
        self._ttl = cache_ttl_seconds
        self._cooldown = refresh_cooldown_seconds
        self._clock = clock
        self._lock = asyncio.Lock()
        self._keys: dict[str, Any] | None = None
        self._fetched_at: float | None = None
        self._last_attempt: float | None = None

    def _fresh(self, now: float) -> bool:
        return (
            self._keys is not None
            and self._fetched_at is not None
            and now - self._fetched_at < self._ttl
        )

    async def get_key(self, kid: str) -> Any:
        now = self._clock()
        if self._fresh(now) and self._keys is not None and kid in self._keys:
            return self._keys[kid]
        async with self._lock:
            now = self._clock()
            if self._fresh(now) and self._keys is not None and kid in self._keys:
                return self._keys[kid]  # refreshed by another request while we waited
            in_cooldown = (
                self._last_attempt is not None and now - self._last_attempt < self._cooldown
            )
            if in_cooldown:
                if self._fresh(now):
                    raise AuthError("TOKEN_INVALID", "Token signing key is not recognized.")
                raise AuthUnavailableError("JWKS_UNAVAILABLE", "Signing keys are unavailable.")
            await self._refresh(now)
            assert self._keys is not None
            key = self._keys.get(kid)
            if key is None:
                raise AuthError("TOKEN_INVALID", "Token signing key is not recognized.")
            return key

    async def _refresh(self, now: float) -> None:
        self._last_attempt = now
        try:
            document = await self._fetcher()
        except Exception as exc:  # noqa: BLE001 - logged and converted to a fail-closed 503
            logger.warning("JWKS fetch failed: %s", type(exc).__name__)
            raise AuthUnavailableError("JWKS_UNAVAILABLE", "Signing keys are unavailable.") from None
        self._keys = _parse_keys(document)  # keeps previous keys if this raises
        self._fetched_at = now
