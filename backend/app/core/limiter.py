"""In-process SlowAPI rate limiter configuration (TASK-035 / M-05).

Operational note on multi-instance scaling:
SlowAPI's in-process memory storage (memory://) tracks request quotas locally within the
running Python process. In a horizontally scaled cluster with multiple backend instances,
quotas are enforced per-instance unless backed by an external distributed store like Redis.
For the MVP stage, in-process rate limiting satisfies DoS prevention without external infrastructure.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    storage_uri="memory://",
)

