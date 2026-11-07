"""RFC 9457 Problem Details formatting (development/ERROR_HANDLING.md)."""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("sylvar")
PROBLEM_JSON = "application/problem+json"


class ProblemException(Exception):
    """Raise from application code to produce a Problem Details response."""

    def __init__(
        self,
        status: int,
        title: str,
        code: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.title = title
        self.code = code
        self.detail = detail
        self.headers = headers


def _problem(
    request: Request,
    status: int,
    title: str,
    code: str,
    detail: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    body = {
        "type": f"about:blank#{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "code": code,
        "request_id": request_id,
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemException)
    async def problem_exc(request: Request, exc: ProblemException) -> JSONResponse:
        return _problem(request, exc.status, exc.title, exc.code, exc.detail, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(request, exc.status_code, "HTTP error", f"HTTP_{exc.status_code}",
                        str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(request, 422, "Validation failed", "VALIDATION_ERROR",
                        "Request failed validation.")

    try:
        from slowapi.errors import RateLimitExceeded

        @app.exception_handler(RateLimitExceeded)
        async def ratelimit_exc(request: Request, exc: RateLimitExceeded) -> JSONResponse:
            return _problem(
                request,
                429,
                "Too Many Requests",
                "RATE_LIMIT_EXCEEDED",
                f"Rate limit exceeded: {exc.detail}",
                headers={"Retry-After": "60"},
            )
    except ImportError:
        pass

    @app.exception_handler(Exception)
    async def unhandled_exc(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s", request.url.path)
        return _problem(request, 500, "Internal server error", "INTERNAL_ERROR",
                        "An unexpected error occurred.")
