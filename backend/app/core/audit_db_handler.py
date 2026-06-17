"""Dual-write audit events into the audit_logs table (BUG-AUD-001).

A logging.Handler attached to the audit logger so every existing audit.log()
call also lands in the queryable, immutable DB table — with zero changes to the
~30 call sites and the RFC 5424 file/syslog pipeline left intact. A DB failure
must never break the request, so emit() swallows everything via handleError.
"""

import logging
from typing import Any

from app.core.logging_config import SD_ID_AUDIT

# Fields that map to dedicated columns; everything else lands in metadata JSONB.
_COLUMN_FIELDS = ('user_id', 'tenant_id', 'ip', 'ua', 'endpoint')


def _clean(value: Any) -> str | None:
    """Map the RFC 5424 nil '-' (and None) to SQL NULL; stringify the rest."""
    if value is None or value == '-':
        return None
    return str(value)


def build_audit_row(record: logging.LogRecord):
    """Pure mapping from a log record to an AuditLog row (no DB I/O).

    Kept separate from emit() so the field mapping is unit-testable without a
    database.
    """
    from app.models.audit_log import AuditLog

    sd = getattr(record, 'sd', None) or {}
    fields = dict(sd.get(SD_ID_AUDIT, {}))

    action = getattr(record, 'msgid', None) or record.getMessage()
    status = fields.pop('status', None) or 'success'
    columns = {name: _clean(fields.pop(name, None)) for name in _COLUMN_FIELDS}
    # Whatever remains (request_id, actor_role, and per-event extras like
    # reason / session_id / intents) is preserved as structured metadata.
    metadata = {k: v for k, v in fields.items() if v not in (None, '-')}

    return AuditLog(
        action=str(action),
        status=str(status),
        audit_metadata=metadata,
        **columns,
    )


class DbAuditHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            from app.core.database import SessionLocal

            row = build_audit_row(record)
            with SessionLocal() as db:
                db.add(row)
                db.commit()
        except Exception:  # never raise into the request/logging path
            self.handleError(record)
