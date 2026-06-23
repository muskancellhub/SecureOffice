"""BUG-VENDOR-006 — serial-PK sequences left behind max(id) by a SQL dump import
cause IntegrityError on the next INSERT (breaks signup + login). The boot-time
migration must bump a behind sequence up to max(id). DB integration: skips
without Postgres.
"""

import pytest
from sqlalchemy import text


def test_runtime_migration_resyncs_behind_sequence():
    from app.core.database import Base, engine

    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401
    from app.core.runtime_migrations import apply_runtime_migrations

    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        mx = conn.execute(text('SELECT COALESCE(MAX(id), 0) FROM refresh_sessions')).scalar()
        # Simulate a dump import: drop the sequence behind max(id).
        behind = max(0, mx - 5)
        conn.execute(text('SELECT setval(:s, :v, true)'), {'s': 'refresh_sessions_id_seq', 'v': max(1, behind)})

    apply_runtime_migrations()

    with engine.connect() as conn:
        cur = conn.execute(text('SELECT last_value FROM refresh_sessions_id_seq')).scalar()
        mx = conn.execute(text('SELECT COALESCE(MAX(id), 0) FROM refresh_sessions')).scalar()
        assert cur >= mx, f'sequence {cur} still behind max(id) {mx}'
