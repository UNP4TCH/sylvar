"""JWT verification configuration: pure, framework-free, fail-fast validation.

Nothing here is project-specific. The Supabase-derived defaults (issuer and JWKS path) are
CONVENTIONS that must be verified against the real project (see LOCAL_SETUP_AND_VERIFICATION.md).
"""
from dataclasses import dataclass
from urllib.parse import urlparse

# Asymmetric algorithms only. HS* (shared secret) and "none" are never acceptable (alg confusion).
ALLOWED_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"})
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class SecurityConfigError(ValueError):
    """Invalid security configuration. Raised at startup so misconfiguration fails fast."""


@dataclass(frozen=True)
class JWTConfig:
    issuer: str
    audience: str
    jwks_url: str
    algorithms: tuple[str, ...]
    leeway_seconds: int = 30
    jwks_cache_ttl_seconds: float = 86400.0  # 24h per SECURITY_ARCHITECTURE; unknown kid still refreshes
    jwks_refresh_cooldown_seconds: float = 30.0
    jwks_fetch_timeout_seconds: float = 5.0


_PLACEHOLDER_MARKERS = ("YOUR-PROJECT", "CHANGE_ME")


def _clean(value: str | None) -> str | None:
    """Blank or template-placeholder values count as 'not set'."""
    if value is None:
        return None
    value = value.strip()
    if not value or any(marker in value for marker in _PLACEHOLDER_MARKERS):
        return None
    return value


def _require_secure_url(name: str, url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme == "https" and host:
        return
    if parsed.scheme == "http" and host in _LOCAL_HOSTS:
        return  # local development stack only
    raise SecurityConfigError(f"{name} must be an https URL (http allowed only for localhost).")


def parse_algorithms(csv: str) -> tuple[str, ...]:
    algs = tuple(a.strip() for a in csv.split(",") if a.strip())
    if not algs:
        raise SecurityConfigError("JWT_ALGORITHMS must list at least one algorithm.")
    bad = [a for a in algs if a not in ALLOWED_ALGORITHMS]
    if bad:
        raise SecurityConfigError(
            f"Unsupported or unsafe JWT algorithm(s) {bad}; allowed: {sorted(ALLOWED_ALGORITHMS)}."
        )
    return algs


def build_jwt_config(
    *,
    supabase_url: str | None,
    jwt_issuer: str | None,
    jwt_audience: str | None,
    jwks_url: str | None,
    algorithms_csv: str,
    leeway_seconds: int = 30,
    jwks_cache_ttl_seconds: float = 86400.0,
    jwks_refresh_cooldown_seconds: float = 30.0,
    jwks_fetch_timeout_seconds: float = 5.0,
) -> JWTConfig | None:
    """Return a config; None only when NO auth setting is provided (requests then fail closed 503).

    A PARTIAL configuration (some auth settings present, required ones missing) raises
    SecurityConfigError at startup rather than silently disabling authentication.
    Audience is mandatory and has no default: we do not guess it. Issuer and JWKS URL may be
    given explicitly or derived from SUPABASE_URL. Blank/placeholder values count as unset.
    """
    supabase_url = _clean(supabase_url)
    jwt_issuer = _clean(jwt_issuer)
    jwt_audience = _clean(jwt_audience)
    jwks_url = _clean(jwks_url)
    if not any((supabase_url, jwt_issuer, jwt_audience, jwks_url)):
        return None
    missing = []
    if not jwt_audience:
        missing.append("JWT_AUDIENCE")
    if not jwt_issuer and not supabase_url:
        missing.append("SUPABASE_URL (or JWT_ISSUER)")
    if missing or jwt_audience is None:
        raise SecurityConfigError(
            "Partial authentication configuration; missing: " + ", ".join(missing) + "."
        )
    issuer = jwt_issuer or f"{(supabase_url or '').rstrip('/')}/auth/v1"  # convention: VERIFY
    jwks = jwks_url or f"{issuer.rstrip('/')}/.well-known/jwks.json"
    _require_secure_url("JWT issuer", issuer)
    _require_secure_url("JWKS URL", jwks)
    if leeway_seconds < 0 or leeway_seconds > 300:
        raise SecurityConfigError("JWT leeway must be between 0 and 300 seconds.")
    if jwks_cache_ttl_seconds <= 0 or jwks_refresh_cooldown_seconds < 0:
        raise SecurityConfigError("JWKS cache TTL must be > 0 and cooldown >= 0.")
    return JWTConfig(
        issuer=issuer,
        audience=jwt_audience,
        jwks_url=jwks,
        algorithms=parse_algorithms(algorithms_csv),
        leeway_seconds=leeway_seconds,
        jwks_cache_ttl_seconds=jwks_cache_ttl_seconds,
        jwks_refresh_cooldown_seconds=jwks_refresh_cooldown_seconds,
        jwks_fetch_timeout_seconds=jwks_fetch_timeout_seconds,
    )
