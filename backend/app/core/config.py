from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.security.config import JWTConfig, build_jwt_config


class Settings(BaseSettings):
    """Backend configuration. Secrets come from env only; none have defaults."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    # Comma-separated list (e.g. "http://localhost:5173,https://app.example.com").
    allowed_origins: str = "http://localhost:5173"

    # Auth / JWT verification. All optional: when unset, protected routes fail closed (503).
    supabase_url: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwks_url: str | None = None
    jwt_algorithms: str = "ES256,RS256"
    jwt_leeway_seconds: int = 30
    jwks_cache_ttl_seconds: float = 86400.0
    jwks_refresh_cooldown_seconds: float = 30.0
    jwks_fetch_timeout_seconds: float = 5.0

    # Database & AI
    database_url: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "VERIFY_BEFORE_SELECTING"

    # Backend-only Admin / Service Role Credentials (never expose to frontend)
    supabase_service_role_key: str | None = None

    # SMTP / Transactional Mailer Configuration
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "noreply@sylvar.local"
    smtp_use_tls: bool = True
    app_frontend_url: str = "http://localhost:5173"

    # Offline Judging Demo Mode (A4) - strictly forbidden in production
    allow_offline_demo: bool = False

    @model_validator(mode="after")
    def _reject_offline_demo_in_production(self) -> "Settings":
        if self.allow_offline_demo and self.app_env.strip().lower() == "production":
            raise ValueError("ALLOW_OFFLINE_DEMO cannot be enabled in production environments.")
        return self

    @field_validator("allowed_origins")
    @classmethod
    def _no_wildcard_origins(cls, value: str) -> str:
        if any(o.strip() == "*" for o in value.split(",")):
            raise ValueError("ALLOWED_ORIGINS must be an explicit whitelist, never '*'.")
        return value

    @property
    def allowed_origins_list(self) -> list[str]:
        origins: list[str] = []
        for o in self.allowed_origins.split(","):
            cleaned = o.strip()
            if not cleaned:
                continue
            normalized = cleaned.rstrip("/")
            if normalized and normalized not in origins:
                origins.append(normalized)
            if cleaned not in origins:
                origins.append(cleaned)
        return origins

    def jwt_config(self) -> JWTConfig | None:
        return build_jwt_config(
            supabase_url=self.supabase_url or None,
            jwt_issuer=self.jwt_issuer or None,
            jwt_audience=self.jwt_audience or None,
            jwks_url=self.jwks_url or None,
            algorithms_csv=self.jwt_algorithms,
            leeway_seconds=self.jwt_leeway_seconds,
            jwks_cache_ttl_seconds=self.jwks_cache_ttl_seconds,
            jwks_refresh_cooldown_seconds=self.jwks_refresh_cooldown_seconds,
            jwks_fetch_timeout_seconds=self.jwks_fetch_timeout_seconds,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
