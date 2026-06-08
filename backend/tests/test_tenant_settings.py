"""Multi-tenant Phase 3 — tenant_settings repository + provisioning.

DB integration (skips without Postgres).
"""
import uuid

import pytest

PFX = 'PH3TS-'


@pytest.fixture(scope='module')
def ts_db():
    from sqlalchemy import text
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401
    from app.core.runtime_migrations import apply_runtime_migrations
    from app.models.tenant import Tenant
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    a, b = uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=a, name=f'{PFX}A'))
        db.add(Tenant(id=b, name=f'{PFX}B'))
        db.commit()

    yield SessionLocal, a, b

    with SessionLocal() as db:
        for t in (a, b):
            db.execute(text('DELETE FROM tenant_settings WHERE tenant_id = :t'), {'t': str(t)})
            db.execute(text('DELETE FROM financing_terms WHERE tenant_id = :t'), {'t': str(t)})
            db.execute(text('DELETE FROM customer_pricing WHERE tenant_id = :t'), {'t': str(t)})
            db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(t)})
        db.commit()


def test_get_or_create_is_idempotent(ts_db):
    SessionLocal, a, _ = ts_db
    from app.repositories.tenant_settings_repository import TenantSettingsRepository
    with SessionLocal() as db:
        row1 = TenantSettingsRepository(db).get_or_create(a)
        db.commit()
        row2 = TenantSettingsRepository(db).get_or_create(a)
        assert row1.tenant_id == row2.tenant_id == a
        assert row1.design_ops == {} and row1.admin_services == {} and row1.feature_flags == {}


def test_update_replaces_only_provided_sections(ts_db):
    SessionLocal, a, _ = ts_db
    from app.repositories.tenant_settings_repository import TenantSettingsRepository
    with SessionLocal() as db:
        repo = TenantSettingsRepository(db)
        repo.update(a, {'design_ops': {'sla_default_days': 7, 'auto_assign': True}})
        db.commit()
        repo.update(a, {'admin_services': {'enabled_categories': {'security': False}}})
        db.commit()
        row = repo.get_by_tenant_id(a)
        # design_ops survived the admin_services-only update.
        assert row.design_ops == {'sla_default_days': 7, 'auto_assign': True}
        assert row.admin_services == {'enabled_categories': {'security': False}}
        assert row.feature_flags == {}


def test_settings_are_tenant_scoped(ts_db):
    SessionLocal, a, b = ts_db
    from app.repositories.tenant_settings_repository import TenantSettingsRepository
    with SessionLocal() as db:
        repo = TenantSettingsRepository(db)
        repo.update(b, {'feature_flags': {'beta_dashboard': True}})
        db.commit()
        assert repo.get_or_create(a).feature_flags == {}
        assert repo.get_by_tenant_id(b).feature_flags == {'beta_dashboard': True}


def test_provision_seeds_tenant_settings(ts_db):
    SessionLocal, _, _ = ts_db
    from sqlalchemy import text
    from app.models.tenant import Tenant
    from app.repositories.tenant_settings_repository import TenantSettingsRepository
    from app.services.tenant_provisioning_service import TenantProvisioningService
    fresh = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=fresh, name=f'{PFX}Fresh'))
        db.flush()
        TenantProvisioningService(db).provision(fresh)
        db.commit()
        assert TenantSettingsRepository(db).get_by_tenant_id(fresh) is not None
        for tbl in ('tenant_settings', 'financing_terms', 'customer_pricing'):
            db.execute(text(f'DELETE FROM {tbl} WHERE tenant_id = :t'), {'t': str(fresh)})
        db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(fresh)})
        db.commit()