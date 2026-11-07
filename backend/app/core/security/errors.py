"""Authentication errors. Messages are safe to return to clients (no token or key content)."""


class AuthError(Exception):
    """Authentication failed. Maps to HTTP 401 unless a subclass says otherwise."""

    status: int = 401

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class AuthUnavailableError(AuthError):
    """Authentication cannot be evaluated (not configured / key source down). Fail closed: 503."""

    status = 503
