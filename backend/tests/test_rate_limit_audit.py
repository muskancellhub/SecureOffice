"""BUG-AUD-014 — rate_limit_exceeded logs the actual request_count that
tripped the limit, not just the configured limit/window."""

import asyncio
import logging
from types import SimpleNamespace

from app.core.logging_config import SD_ID_AUDIT
from app.middleware import rate_limit as rl
from app.middleware.rate_limit import RateLimitMiddleware


def test_rate_limit_exceeded_logs_request_count(monkeypatch):
    monkeypatch.setattr(rl, '_resolve_client_ip', lambda req, n: '203.0.113.7')
    mw = RateLimitMiddleware(app=None, max_requests=2, window_seconds=60)
    request = SimpleNamespace(url=SimpleNamespace(path='/limited'))

    async def _ok(_req):
        return SimpleNamespace(status_code=200)

    records = []
    handler = logging.Handler()
    handler.emit = records.append
    audit_logger = logging.getLogger('secureoffice.audit')
    audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)
    try:
        async def run():
            await mw.dispatch(request, _ok)   # 1 — allowed
            await mw.dispatch(request, _ok)   # 2 — allowed (bucket now full)
            return await mw.dispatch(request, _ok)  # 3 — blocked
        blocked = asyncio.run(run())
    finally:
        audit_logger.removeHandler(handler)

    assert blocked.status_code == 429
    rec = next(r for r in records if getattr(r, 'msgid', None) == 'rate_limit_exceeded')
    f = rec.sd[SD_ID_AUDIT]
    assert f['request_count'] == 2     # the bucket size at the breach
    assert f['limit'] == 2
