"""Asymmetric JWT verification against a JWKS. Framework-free; identity only (no roles)."""
import uuid
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from app.core.security.config import JWTConfig
from app.core.security.errors import AuthError
from app.core.security.jwks import JWKSProvider

_MAX_TOKEN_CHARS = 8192
_REQUIRED_CLAIMS = ["exp", "sub", "iss", "aud"]


def _key_matches_alg(key: object, alg: str) -> bool:
    if alg.startswith("ES"):
        return isinstance(key, ec.EllipticCurvePublicKey)
    if alg.startswith("RS"):
        return isinstance(key, rsa.RSAPublicKey)
    return False


@dataclass(frozen=True)
class AuthenticatedUser:
    """Verified identity. Workspace/client roles come from the database (Phase 2), never the JWT."""

    user_id: uuid.UUID
    expires_at: int
    email: str | None = None
    email_verified: bool = False


class JWTVerifier:
    def __init__(self, config: JWTConfig, jwks: JWKSProvider) -> None:
        self._config = config
        self._jwks = jwks

    async def verify(self, token: str) -> AuthenticatedUser:
        if not token or len(token) > _MAX_TOKEN_CHARS:
            raise AuthError("TOKEN_MALFORMED", "Token is malformed.")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise AuthError("TOKEN_MALFORMED", "Token is malformed.") from None
        alg = header.get("alg")
        kid = header.get("kid")
        if not isinstance(alg, str) or alg not in self._config.algorithms:
            raise AuthError("TOKEN_INVALID", "Token algorithm is not accepted.")
        if not isinstance(kid, str) or not kid:
            raise AuthError("TOKEN_INVALID", "Token is missing a key identifier.")

        key = await self._jwks.get_key(kid)
        if not _key_matches_alg(key, alg):
            raise AuthError("TOKEN_INVALID", "Token algorithm does not match the signing key.")
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[alg],  # pinned to the header alg, already allow-listed above
                audience=self._config.audience,
                issuer=self._config.issuer,
                leeway=self._config.leeway_seconds,
                options={"require": _REQUIRED_CLAIMS},
            )
        except jwt.ExpiredSignatureError:
            raise AuthError("TOKEN_EXPIRED", "Token has expired.") from None
        except (jwt.PyJWTError, TypeError, ValueError):
            # Includes library-level type/value errors on exotic keys or claims: never a 500.
            raise AuthError("TOKEN_INVALID", "Token is invalid.") from None

        try:
            user_id = uuid.UUID(str(claims["sub"]))
        except ValueError:
            raise AuthError("TOKEN_INVALID", "Token subject is invalid.") from None

        raw_email = claims.get("email")
        email = str(raw_email).strip().lower() if isinstance(raw_email, str) and raw_email.strip() else None

        # CRITICAL SECURITY (Batch 2A Hardening):
        # Only trust cryptographically signed root claims from the token issuer.
        # NEVER inspect `user_metadata` which is client-editable in Supabase GoTrue
        # and can be forged by an attacker during signup or profile update.
        root_verified = claims.get("email_verified")
        root_confirmed_at = claims.get("email_confirmed_at")

        email_verified: bool = False
        if isinstance(root_verified, bool) and root_verified is True:
            email_verified = True
        elif isinstance(root_confirmed_at, str) and bool(root_confirmed_at.strip()):
            email_verified = True

        return AuthenticatedUser(
            user_id=user_id,
            expires_at=int(claims["exp"]),
            email=email,
            email_verified=email_verified,
        )
