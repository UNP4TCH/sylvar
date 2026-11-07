"""Settings for tests: ignore any real .env and process env for auth/origin values."""
from typing import Any

from app.core.config import Settings


def clean_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "supabase_url": None,
        "jwt_issuer": None,
        "jwt_audience": None,
        "jwks_url": None,
        "allowed_origins": "http://localhost:5173",
        "jwt_algorithms": "ES256,RS256",
        "gemini_api_key": None,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)
