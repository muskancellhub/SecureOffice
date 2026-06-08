"""Multi-tenant Phase 1 — financing per-tenant + clone-on-onboard.

DB integration (skips without Postgres). Verifies:
- financing_terms is tenant-scoped (two tenants don't see each other's terms),
- TenantProvisioningService clones the master tenant's financing into a new tenant
  and seeds a customer_pricing row,
- the per-tenant default index allows the same default in two tenants,
- _default_financing falls back to the master tenant for a tenant with none.
"""
import uuid

import pytest

PFX = 'PH1MT-'


@pytest.fixture(scope='module')
def mt_db():
    from sqlalchemy import text
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401
    from app.core.runtime_migrations import apply_runtime_migrations
    from app.core.tenancy import CELLHUB_MASTER_TENANT_ID
    from app.models.financing import FinancingTerms
    from app.models.tenant import Tenant
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    a, b = uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=a, name=f'{PFX}A'))
        db.add(Tenant(id=b, name=f'{PFX}B'))
        # Seed a master-tenant term so clone-on-onboard has something to copy.
        # is_default=False so we never collide with the master's real default
        # (mix_seed may have already set one — the per-tenant index allows one).
        db.add(FinancingTerms(
            tenant_id=uuid.UUID(CELLHUB_MASTER_TENANT_ID), name=f'{PFX}MasterTerm',
            term_months=36, annual_rate_pct='0.0500', subscription_interval='MONTH',
            is_default=False, is_active=True,
        ))
        db.commit()

    yield SessionLocal, a, b

    with SessionLocal() as db:
        for t in (a, b):
            db.execute(text('DELETE FROM financing_terms WHERE tenant_id = :t'), {'t': str(t)})
            db.execute(text('DELETE FROM customer_pricing WHERE tenant_id = :t'), {'t': str(t)})
            db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(t)})
        db.execute(text('DELETE FROM financing_terms WHERE name = :n'), {'n': f'{PFX}MasterTerm'})
        db.commit()


def test_financing_is_tenant_scoped(mt_db):
    SessionLocal, a, b = mt_db
    from app.services.product_admin_service import ProductAdminService
    with SessionLocal() as db:
        svc = ProductAdminService(db)
        svc.create_financing_terms(a, {'name': f'{PFX}24mo', 'term_months': 24, 'is_default': True})
        svc.create_financing_terms(b, {'name': f'{PFX}48mo', 'term_months': 48, 'is_default': True})

        a_names = {t.name for t in svc.list_financing_terms(a)}
        b_names = {t.name for t in svc.list_financing_terms(b)}
        assert f'{PFX}24mo' in a_names and f'{PFX}48mo' not in a_names
        assert f'{PFX}48mo' in b_names and f'{PFX}24mo' not in b_names
        # Same is_default in two tenants is allowed by the per-tenant partial index.


def test_provision_clones_master_financing_and_pricing(mt_db):
    SessionLocal, a, _ = mt_db
    from app.models.financing import FinancingTerms
    from app.models.pricing import CustomerPricing
    from app.services.tenant_provisioning_service import TenantProvisioningService
    from sqlalchemy import select
    with SessionLocal() as db:
        TenantProvisioningService(db).provision(a)
        db.commit()

        cloned = db.scalars(
            select(FinancingTerms).where(
                FinancingTerms.tenant_id == a, FinancingTerms.name == f'{PFX}MasterTerm'
            )
        ).all()
        assert len(cloned) == 1, 'master term should be cloned into tenant A'

        pricing = db.get(CustomerPricing, a)
        assert pricing is not None, 'provision should seed a customer_pricing row'

        # Idempotent: second provision does not duplicate the cloned term.
        TenantProvisioningService(db).provision(a)
        db.commit()
        again = db.scalars(
            select(FinancingTerms).where(
                FinancingTerms.tenant_id == a, FinancingTerms.name == f'{PFX}MasterTerm'
            )
        ).all()
        assert len(again) == 1


def test_default_financing_falls_back_to_master(mt_db):
    SessionLocal, _, _ = mt_db
    from app.core.tenancy import CELLHUB_MASTER_TENANT_ID
    from app.models.financing import FinancingTerms
    from app.services.component_pricing_service import ComponentPricingService
    from sqlalchemy import select
    with SessionLocal() as db:
        # Ensure the master tenant has a default (promote our seeded term if it has
        # none — isolation-safe whether or not mix_seed ran first).
        master = uuid.UUID(CELLHUB_MASTER_TENANT_ID)
        master_default = db.scalar(
            select(FinancingTerms).where(
                FinancingTerms.tenant_id == master, FinancingTerms.is_default.is_(True)
            )
        )
        if master_default is None:
            master_default = db.scalar(
                select(FinancingTerms).where(
                    FinancingTerms.tenant_id == master, FinancingTerms.name == f'{PFX}MasterTerm'
                )
            )
            master_default.is_default = True
            db.commit()

        # A brand-new tenant with no financing falls back to the master default.
        fresh = uuid.uuid4()
        fin = ComponentPricingService(db)._default_financing(fresh)
        assert fin is not None and fin.id == master_default.id
