import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.limiter import limiter
from app.core.security.jwks import JWKSProvider
from app.core.security.jwks_http import make_http_fetcher
from app.core.security.jwt_verifier import JWTVerifier
from app.db.session import validate_database_configuration
from app.modules.audits.router import router as audits_router
from app.modules.auth.user_router import router as user_router
from app.modules.clients.router import router as clients_router
from app.modules.documents.router import router as documents_router
from app.modules.health.router import router as health_router
from app.modules.memory.router import router as memory_router
from app.modules.reviews.router import router as reviews_router
from app.modules.workspaces.router import router as workspaces_router

startup_logger = logging.getLogger("sylvar.startup")


def build_verifier(settings: Settings) -> JWTVerifier | None:
    config = settings.jwt_config()  # raises on invalid/partial config: fail fast at startup
    if config is None:
        startup_logger.warning(
            "JWT authentication is NOT configured; protected routes will return 503 "
            "AUTH_NOT_CONFIGURED. JWKS reachability is not checked at startup."
        )
        return None
    startup_logger.info(
        "JWT authentication configured (issuer=%s, algorithms=%s). JWKS is fetched lazily.",
        config.issuer, ",".join(config.algorithms),
    )
    provider = JWKSProvider(
        make_http_fetcher(config.jwks_url, config.jwks_fetch_timeout_seconds),
        cache_ttl_seconds=config.jwks_cache_ttl_seconds,
        refresh_cooldown_seconds=config.jwks_refresh_cooldown_seconds,
    )
    return JWTVerifier(config, provider)


def create_app(
    settings: Settings | None = None, jwt_verifier: JWTVerifier | None = None
) -> FastAPI:
    settings = settings or get_settings()
    validate_database_configuration(settings)
    app = FastAPI(title="SYLVAR API", version="0.1.0")

    # M-05: Attach global SlowAPI rate limiter
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    # M-05: Enforce request body size limits (25 MB)
    @app.middleware("http")
    async def limit_request_size(request: Request, call_next):  # type: ignore[no-untyped-def]
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > 25 * 1024 * 1024:
                    return JSONResponse(
                        status_code=413,
                        media_type="application/problem+json",
                        content={
                            "type": "about:blank",
                            "title": "Payload Too Large",
                            "status": 413,
                            "code": "REQUEST_BODY_TOO_LARGE",
                            "detail": "Request body exceeds maximum allowed limit of 25 MB.",
                        },
                    )
            except ValueError:
                pass
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,  # explicit whitelist, never "*"
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    install_error_handlers(app)
    app.state.jwt_verifier = jwt_verifier or build_verifier(settings)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(user_router, prefix="/api/v1")
    app.include_router(workspaces_router, prefix="/api/v1")
    app.include_router(clients_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(memory_router, prefix="/api/v1")
    app.include_router(audits_router, prefix="/api/v1")
    app.include_router(reviews_router, prefix="/api/v1")
    return app


app = create_app()
