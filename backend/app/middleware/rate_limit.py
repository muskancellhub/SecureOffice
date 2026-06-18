import logging
import math
import time
from collections import defaultdict, deque
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.guardrail_policy import LLM_RATE_LIMITS
from app.core.request_context import resolve_client_ip
from app.services.audit_logger import audit


# Per-path overrides: tighter limits on auth endpoints so brute force is expensive
# even when the global limit would allow more. Values are (max_requests, window_seconds).
#
# These numbers target realistic human use: a person will not submit login 10+
# times in a minute from the same IP, but a bot happily would. Credential stuffers
# need far more than 10 tries per IP/minute to be profitable — this breaks them.
AUTH_PATH_LIMITS: dict[str, tuple[int, int]] = {
    '/auth/login': (10, 60),
    '/auth/verify-otp': (10, 60),
    '/auth/login/otp/verify': (10, 60),
    '/auth/login/otp/request': (5, 60),
    '/auth/signup': (5, 60),
    '/auth/vendor/signup': (5, 60),
    '/auth/refresh': (30, 60),
}

# LLM-backed endpoints (intake/chat, anam/*, chatbot/ask) spend OpenAI/Anam
# tokens billed to our account, so they get tight per-IP limits. The values
# live in the central guardrail policy module so all LLM-surface policy is
# auditable in one place (RAG plan 3.2).
AUTH_PATH_LIMITS.update(LLM_RATE_LIMITS)


# Client-IP resolution lives in app.core.request_context so rate limiting and
# logging use identical logic (docs/LOGGING_PLAN.md §4.1).
_resolve_client_ip = resolve_client_ip


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-(client, path) in-memory rate limiter.

    Known limits of this implementation:
      - In-memory dict is per-worker. With N workers, effective limit is N × configured.
        For stricter limits in multi-worker deploys, swap for a Redis-backed limiter.
      - No global/cross-path budget: a single client can exhaust each path independently.

    What it does well:
      - Respects trusted proxy configuration when resolving client IP.
      - Tight per-endpoint limits on auth paths raise the cost of credential stuffing
        and OTP brute force without needing external infra.
    """

    def __init__(self, app, max_requests: int = 120, window_seconds: int = 60, trusted_proxy_count: int = 0):
        super().__init__(app)
        self.default_max = max_requests
        self.default_window = window_seconds
        self.trusted_proxy_count = trusted_proxy_count
        self.buckets: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        max_requests, window = AUTH_PATH_LIMITS.get(path, (self.default_max, self.default_window))

        client_ip = _resolve_client_ip(request, self.trusted_proxy_count)
        key = f"{client_ip}:{path}"

        now = time.time()
        q = self.buckets[key]

        while q and q[0] <= now - window:
            q.popleft()

        if len(q) >= max_requests:
            retry_after = max(1, int(window - (now - q[0])))
            retry_minutes = max(1, math.ceil(retry_after / 60))
            audit.log(
                'rate_limit_exceeded',
                status='blocked',
                level=logging.WARNING,
                limit=max_requests,
                window_seconds=window,
                # BUG-AUD-014: actual bucket size that tripped the limit.
                request_count=len(q),
                retry_after_seconds=retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={'detail': f'Too many requests. Please try again after {retry_minutes} minute(s).'},
                headers={'Retry-After': str(retry_after)},
            )

        q.append(now)
        return await call_next(request)
