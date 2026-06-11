"""Per-request context shared by logging, audit, and rate limiting.

Captured once per request by RequestContextMiddleware and stored in
contextvars, so anything on the request path (services, exception handlers,
the audit logger) can read it without threading parameters through every
call. See docs/LOGGING_PLAN.md §4.1.
"""
from __future__ import annotations

import contextvars
import re
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Request

# Inbound X-Request-Id values are only honored from trusted proxies, and even
# then must look like an opaque id — anything else becomes a fresh UUID so a
# client can't inject log content through the header.
_REQUEST_ID_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')


@dataclass
class RequestContext:
    request_id: str
    method: str
    path: str
    client_ip: str
    user_agent: str
    # The live request, so user identity (set later by AuthContextMiddleware,
    # which runs inside this middleware) is read lazily at log-emit time.
    request: Any = None


_request_ctx: contextvars.ContextVar[Optional[RequestContext]] = contextvars.ContextVar(
    'request_ctx', default=None
)


def resolve_client_ip(request: Request, trusted_proxy_count: int) -> str:
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


def new_request_id(inbound: str | None = None, trust_inbound: bool = False) -> str:
    if trust_inbound and inbound and _REQUEST_ID_RE.match(inbound):
        return inbound
    return str(uuid.uuid4())


def set_request_context(ctx: RequestContext) -> contextvars.Token:
    return _request_ctx.set(ctx)


def reset_request_context(token: contextvars.Token) -> None:
    _request_ctx.reset(token)


def get_request_context() -> Optional[RequestContext]:
    return _request_ctx.get()


def common_log_fields() -> dict[str, str]:
    """The SD fields every audit/access line carries (LOGGING_PLAN §6).

    Outside a request (startup, cron-triggered code) all fields are the RFC
    5424 nil value so lines still parse.
    """
    ctx = _request_ctx.get()
    fields = {
        'request_id': '-',
        'tenant_id': '-',
        'user_id': '-',
        'actor_role': '-',
        'ip': '-',
        'ua': '-',
        'endpoint': '-',
    }
    if ctx is None:
        return fields

    fields['request_id'] = ctx.request_id
    fields['ip'] = ctx.client_ip or '-'
    fields['ua'] = ctx.user_agent or '-'
    fields['endpoint'] = f'{ctx.method} {ctx.path}'

    user = None
    if ctx.request is not None:
        user = getattr(ctx.request.state, 'user', None)
    if isinstance(user, dict):
        fields['user_id'] = str(user.get('user_id') or '-')
        fields['tenant_id'] = str(user.get('tenant_id') or '-')
        fields['actor_role'] = str(user.get('role') or '-')
    return fields
