"""Multi-tenant Phase 4 — Row-Level Security.

DB integration (skips without Postgres). Toggles ENABLE_RLS on for the module,
enables the policies via the migration, and verifies:
- the per-transaction GUC plumbing (set_config survives commits),
- tenant isolation on reads (a session pinned to tenant A can't see B),
- the GUC-unset "system path" sees all rows,
- WITH CHECK blocks writing another tenant's row.

Enforcement assertions are skipped if the DB role is a SUPERUSER (superusers
bypass RLS regardless of FORCE). Teardown disables RLS again — the flag is a
kill switch — so later test modules and the app are unaffected.
"""
import uuid

import pytest
from sqlalchemy import select, text


def _make_term(tenant_id, name):
    from app.models.financing import FinancingTerms
    return FinancingTerms(
        tenant_id=tenant_id, name=name, term_months=36, annual_rate_pct='0.0500',
        subscription_interval='MONTH', is_default=False, is_active=True,
    )


@pytest.fixture(scope='module')
def rls_db():
    import app.core.database as database
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401
    from app.core.runtime_migrations import apply_runtime_migrations
    from app.models.tenant import Tenant

    is_super = False
    with engine.connect() as conn:
        row = conn.execute(text('SELECT rolsuper FROM pg_roles WHERE rolname = current_user')).first()
        is_super = bool(row and row[0])

    # Turn RLS on for the duration of this module (single shared settings object).
    database.settings.enable_rls = True
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    a, b = uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:  # no tenant on session.info -> GUC unset -> allowed
        db.add(Tenant(id=a, name='RLS-A'))
        db.add(Tenant(id=b, name='RLS-B'))
        db.commit()
        db.add(_make_term(a, 'RLS-A-term'))
        db.add(_make_term(b, 'RLS-B-term'))
        db.commit()

    try:
        yield SessionLocal, a, b, is_super
    finally:
        # Kill switch: revert RLS so other modules/app are unaffected.
        database.settings.enable_rls = False
        apply_runtime_migrations()
        with SessionLocal() as db:
            for t in (a, b):
                db.execute(text('DELETE FROM financing_terms WHERE tenant_id = :t'), {'t': str(t)})
                db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(t)})
            db.commit()


def test_guc_is_applied_and_survives_commits(rls_db):
    SessionLocal, a, _b, _is_super = rls_db
    with SessionLocal() as db:
        db.info['tenant_id'] = str(a)
        got = db.execute(text("SELECT current_setting('app.current_tenant_id', true)")).scalar()
        assert got == str(a)
        db.commit()  # ends the transaction; the next one must re-apply the GUC
        got2 = db.execute(text("SELECT current_setting('app.current_tenant_id', true)")).scalar()
        assert got2 == str(a), 'GUC must be re-applied after a mid-request commit'


def test_unset_guc_sees_all_rows(rls_db):
    SessionLocal, a, b, _is_super = rls_db
    from app.models.financing import FinancingTerms
    with SessionLocal() as db:  # system path: no tenant on the session
        names = {t.name for t in db.scalars(
            select(FinancingTerms).where(FinancingTerms.name.like('RLS-%'))
        )}
        assert {'RLS-A-term', 'RLS-B-term'} <= names


def test_read_isolation(rls_db):
    SessionLocal, a, b, is_super = rls_db
    if is_super:
        pytest.skip('DB role is SUPERUSER — bypasses RLS; enforcement not observable')
    from app.models.financing import FinancingTerms
    with SessionLocal() as db:
        db.info['tenant_id'] = str(a)
        names = {t.name for t in db.scalars(
            select(FinancingTerms).where(FinancingTerms.name.like('RLS-%'))
        )}
        assert names == {'RLS-A-term'}, f'tenant A must not see B; saw {names}'


def test_with_check_blocks_foreign_tenant_write(rls_db):
    SessionLocal, a, b, is_super = rls_db
    if is_super:
        pytest.skip('DB role is SUPERUSER — bypasses RLS; WITH CHECK not observable')
    from sqlalchemy.exc import ProgrammingError, IntegrityError
    with SessionLocal() as db:
        db.info['tenant_id'] = str(a)
        db.add(_make_term(b, 'RLS-should-fail'))  # row for B while pinned to A
        with pytest.raises((ProgrammingError, IntegrityError)):
            db.commit()
        db.rollback()
