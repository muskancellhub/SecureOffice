"""Security response headers.

These are the defense-in-depth headers a DAST tool will look for on every
response. None of them block specific attacks on their own — they close
exploitation paths that depend on browser behavior (framing, MIME-sniffing,
downgrade, mixed content).

Notes:
  - HSTS is only meaningful on HTTPS. We still emit it in production so that
    once TLS is in front, browsers lock in HTTPS-only.
  - CSP is intentionally narrow: this backend serves JSON only. The frontend
    sets its own CSP. If you start returning HTML from this API, revisit.
  - No X-Powered-By / Server overrides here — Uvicorn already writes a minimal
    `Server: uvicorn` value, which is acceptable.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, app_env: str = 'development'):
        super().__init__(app)
        self.app_env = app_env

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent MIME-sniffing — browser trusts our declared Content-Type.
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')

        # Clickjacking protection. Backend returns JSON only; never frame it.
        response.headers.setdefault('X-Frame-Options', 'DENY')

        # Referrer: don't leak our API URLs to third parties if a redirect happens.
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')

        # No browser-level feature access. We're an API, not a page.
        response.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')

        # Restrictive CSP — this backend never serves rendered HTML to users.
        # The frontend (separate origin, set in its own deployment) has its own CSP.
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'none'; frame-ancestors 'none'",
        )

        # HSTS only in production; local HTTP dev would break under it.
        if self.app_env == 'production':
            response.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains',
            )

        return response
