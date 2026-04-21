import time
from collections import defaultdict, deque
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


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


def _resolve_client_ip(request: Request, trusted_proxy_count: int) -> str:
    """Determine the real client IP.

    Behind a reverse proxy, request.client.host is the proxy's IP — every user
    then shares one rate-limit bucket. When trusted_proxy_count > 0, read the
    real IP from X-Forwarded-For, counting from the right (the rightmost entry
    is the nearest proxy, so we step back `trusted_proxy_count` entries).

    Only do this when trusted_proxy_count is set — otherwise an attacker can
    forge XFF to get per-fake-IP rate buckets and bypass the limit entirely.
    """
    if trusted_proxy_count <= 0:
        return request.client.host if request.client else 'unknown'

    xff = request.headers.get('x-forwarded-for', '')
    if not xff:
        return request.client.host if request.client else 'unknown'

    # XFF is a comma-separated list; rightmost is closest to us.
    # If we trust 1 proxy, the real client is at index -1 (one before our proxy).
    parts = [p.strip() for p in xff.split(',') if p.strip()]
    if not parts:
        return request.client.host if request.client else 'unknown'
    idx = max(0, len(parts) - trusted_proxy_count)
    return parts[idx] if idx < len(parts) else parts[0]


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
            return JSONResponse(
                status_code=429,
                content={'detail': 'Rate limit exceeded'},
                headers={'Retry-After': str(retry_after)},
            )

        q.append(now)
        return await call_next(request)
