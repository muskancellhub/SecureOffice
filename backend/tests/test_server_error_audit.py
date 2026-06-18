"""BUG-AUD-015 — a 500 server_error event carries correlation context
(request_id/endpoint/ip) and error_code, even though the handler runs in the
outer ServerErrorMiddleware after the context var was reset."""

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging_config import SD_ID_AUDIT
from app.middleware.request_context import RequestContextMiddleware


def _build_app():
    from app.main import unhandled_error_handler

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.get('/boom')
    def boom():
        raise RuntimeError('kaboom')

    return app


def test_server_error_has_context_and_error_code():
    # Build the app first: importing app.main triggers configure_logging(), which
    # resets the audit logger's handlers. Attach the capture handler afterwards
    # so it survives.
    app = _build_app()
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    audit_logger = logging.getLogger('secureoffice.audit')
    audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/boom')
    finally:
        audit_logger.removeHandler(handler)

    assert resp.status_code == 500
    rec = next(r for r in records if getattr(r, 'msgid', None) == 'server_error')
    f = rec.sd[SD_ID_AUDIT]
    assert f['error_code'] == 500
    assert f['error_type'] == 'RuntimeError'
    # Previously these were the RFC 5424 nil '-' because the context was reset.
    assert f['endpoint'] == 'GET /boom'
    assert f['request_id'] != '-'
