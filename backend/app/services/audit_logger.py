"""Single write path for audit events (docs/LOGGING_PLAN.md §4.2).

Usage, from the service layer where old/new values are in scope:

    from app.services.audit_logger import audit

    audit.log('user_role_changed', old_role=old.value, new_role=new.value)
    audit.log('user_login_failed', status='failure', level=logging.WARNING,
              email_attempted=email, reason='bad_password')

Common fields (request_id, tenant_id, user_id, actor_role, ip, ua, endpoint)
are auto-filled from request context; redaction happens in the logging
pipeline, so callers never need to sanitize. A logging failure must never
break the request — this logger swallows everything and falls back to stderr.
"""
from __future__ import annotations

import logging
import sys
from typing import Any, Optional

from app.core.logging_config import AUDIT_LOGGER_NAME, NOTICE, SD_ID_AUDIT
from app.core.request_context import common_log_fields

_logger = logging.getLogger(AUDIT_LOGGER_NAME)


class AuditLogger:
    def log(
        self,
        action: str,
        status: str = 'success',
        level: Optional[int] = None,
        message: Optional[str] = None,
        **fields: Any,
    ) -> None:
        """Emit one audit event. `action` becomes the RFC 5424 MSGID;
        `fields` become structured-data keys. Default severity is notice
        (plan §2.2); pass level=logging.WARNING/ERROR for failures."""
        try:
            sd_fields = dict(common_log_fields())
            sd_fields['status'] = status
            for key, value in fields.items():
                sd_fields[key] = '-' if value is None else value
            _logger.log(
                level if level is not None else NOTICE,
                message or action.replace('_', ' '),
                extra={'msgid': action, 'sd': {SD_ID_AUDIT: sd_fields}},
            )
        except Exception as exc:  # never raise into the request path
            try:
                print(f'audit-logger failure for {action!r}: {exc}', file=sys.stderr)
            except Exception:  # nosec B110 — last-resort fallback of a never-raise logger
                pass


audit = AuditLogger()
