"""BUG-ORD-001 — setting an order to VENDOR_ORDERED must not 500.

The 500 was a stale CHECK constraint on orders.status (created before
VENDOR_ORDERED existed) that runtime_migrations didn't drop because it targeted
the wrong constraint name. DB integration test: skips without Postgres.
"""

import pytest
from sqlalchemy import text


def test_order_status_constraint_allows_vendor_ordered():
    from app.core.database import Base, engine

    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401 — register tables
    from app.core.runtime_migrations import apply_runtime_migrations

    Base.metadata.create_all(bind=engine)
    apply_runtime_migrations()

    with engine.connect() as conn:
        rows = conn.execute(text(
            """
            SELECT conname, pg_get_constraintdef(oid) AS def
            FROM pg_constraint
            WHERE conrelid = 'orders'::regclass
              AND contype = 'c'
              AND pg_get_constraintdef(oid) LIKE '%status%'
            """
        )).all()

    assert rows, 'expected a CHECK constraint gating orders.status'
    for name, defn in rows:
        assert 'VENDOR_ORDERED' in defn, f'{name} still rejects VENDOR_ORDERED: {defn}'
