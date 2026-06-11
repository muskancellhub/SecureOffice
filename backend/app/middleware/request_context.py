"""Request-context capture + access log (docs/LOGGING_PLAN.md §4.1).

Registered just inside CORS, outside AuthContextMiddleware: the context is
available to everything downstream (rate limiter, services, exception
handlers), and by the time the access line is emitted on the way out, auth
has populated request.state.user so the line carries user identity.
"""
from __future__ import annotations

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging_config import ACCESS_LOGGER_NAME, SD_ID_REQUEST
from app.core.request_context import (
    RequestContext,
    common_log_fields,
    new_request_id,
    reset_request_context,
    resolve_client_ip,
    set_request_context,
)

_access_logger = logging.getLogger(ACCESS_LOGGER_NAME)


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, trusted_proxy_count: int = 0):
        super().__init__(app)
        self.trusted_proxy_count = trusted_proxy_count

    async def dispatch(self, request: Request, call_next):
        request_id = new_request_id(
            inbound=request.headers.get('x-request-id'),
            # Only honor an inbound id when it can have come from our proxy,
            # not directly from a client (plan §4.1).
            trust_inbound=self.trusted_proxy_count > 0,
        )
        ctx = RequestContext(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=resolve_client_ip(request, self.trusted_proxy_count),
            user_agent=request.headers.get('user-agent', ''),
            request=request,
        )
        token = set_request_context(ctx)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            if ctx.path != '/health':  # excluded from both streams (plan §6)
                self._emit_access_line(response.status_code, start)
            response.headers['X-Request-Id'] = request_id
            return response
        finally:
            reset_request_context(token)

    @staticmethod
    def _emit_access_line(status_code: int, start: float) -> None:
        try:
            fields = dict(common_log_fields())
            fields['status_code'] = status_code
            fields['duration_ms'] = round((time.perf_counter() - start) * 1000, 1)
            _access_logger.info(
                f'{fields["endpoint"]} -> {status_code}',
                extra={'msgid': 'http_request', 'sd': {SD_ID_REQUEST: fields}},
            )
        except Exception:  # the access log must never break a response
            pass
