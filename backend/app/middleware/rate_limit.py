import time
from collections import defaultdict, deque
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 120, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        key = f"{request.client.host}:{request.url.path}" if request.client else request.url.path
        now = time.time()
        q = self.requests[key]

        while q and q[0] <= now - self.window_seconds:
            q.popleft()

        if len(q) >= self.max_requests:
            return JSONResponse(status_code=429, content={'detail': 'Rate limit exceeded'})

        q.append(now)
        return await call_next(request)
