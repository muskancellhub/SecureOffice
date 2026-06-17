"""BUG-AUD-001 — queryable, immutable audit_logs table + dual-write.

The record->row mapping is unit-tested without a DB. The dual-write insert and
the append-only triggers are DB integration tests that skip without Postgres
(same pattern as test_rls.py).
"""

import logging
import uuid

import pytest
from sqlalchemy import text

from app.core.audit_db_handler import DbAuditHandler, build_audit_row
from app.core.logging_config import NOTICE, SD_ID_AUDIT


def _record(msgid, sd_fields):
    rec = logging.LogRecord('secureoffice.audit', NOTICE, __file__, 0, msgid, None, None)
    rec.msgid = msgid
    rec.sd = {SD_ID_AUDIT: dict(sd_fields)}
    return rec


# ── pure mapping (no DB) ─────────────────────────────────────────────────────

def test_build_audit_row_maps_columns_and_metadata():
    row = build_audit_row(_record('user_logout', {
        'user_id': 'u1', 'tenant_id': '-', 'ip': '1.2.3.4',
        'endpoint': '/auth/logout', 'status': 'success',
        'session_id': '5', 'request_id': 'r1',
    }))
    assert row.action == 'user_logout'
    assert row.user_id == 'u1'
    assert row.tenant_id is None          # RFC 5424 nil '-' -> SQL NULL
    assert row.ip == '1.2.3.4'
    assert row.endpoint == '/auth/logout'
    assert row.status == 'success'
    # Non-column fields are preserved as structured metadata.
    assert row.audit_metadata['session_id'] == '5'
    assert row.audit_metadata['request_id'] == 'r1'
    # Column fields and status are not duplicated into metadata.
    assert 'user_id' not in row.audit_metadata
    assert 'status' not in row.audit_metadata


def test_build_audit_row_defaults_status_and_action_from_message():
    row = build_audit_row(_record('design_saved', {}))
    assert row.action == 'design_saved'
    assert row.status == 'success'
    assert row.audit_metadata == {}


# ── DB integration: dual-write + immutability ────────────────────────────────

@pytest.fixture(scope='module')
def audit_db():
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401  (register models)
    from app.core.runtime_migrations import apply_runtime_migrations

    Base.metadata.create_all(bind=engine)   # table first, so the trigger attaches
    apply_runtime_migrations()              # append-only triggers
    yield SessionLocal


def test_dual_write_inserts_row(audit_db):
    from app.models.audit_log import AuditLog

    action = f'test_event_{uuid.uuid4().hex[:8]}'
    DbAuditHandler().emit(_record(action, {'user_id': 'u-dual', 'status': 'success', 'note': 'x'}))

    with audit_db() as db:
        row = db.query(AuditLog).filter(AuditLog.action == action).one()
        assert row.user_id == 'u-dual'
        assert row.audit_metadata.get('note') == 'x'
        # No cleanup: the table is append-only by design (see immutability test).


def test_audit_rows_are_immutable(audit_db):
    from app.models.audit_log import AuditLog

    action = f'test_immutable_{uuid.uuid4().hex[:8]}'
    with audit_db() as db:
        db.add(AuditLog(action=action, status='success', audit_metadata={}))
        db.commit()

    with audit_db() as db:
        with pytest.raises(Exception):
            db.execute(text('UPDATE audit_logs SET status = :s WHERE action = :a'),
                       {'s': 'tampered', 'a': action})
            db.commit()
    with audit_db() as db:
        with pytest.raises(Exception):
            db.execute(text('DELETE FROM audit_logs WHERE action = :a'), {'a': action})
            db.commit()
