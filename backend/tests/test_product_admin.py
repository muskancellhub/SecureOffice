"""Phase 4 tests — admin catalog CRUD + commercial config.

DB integration (skips without Postgres). Verifies product/component CRUD,
financing terms, customer commercial config + price overrides, validation, and
that an admin edit flows straight into ComponentPricingService.
"""
import uuid
from decimal import Decimal

import pytest

from app.core.exceptions import AppError


PFX = 'PH4-'


@pytest.fixture(scope='module')
def admin_db():
    from sqlalchemy import text, select
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

    tid = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=tid, name='PH4 Test Tenant'))
        db.commit()

    yield SessionLocal, tid

    from app.models.product import Product
    from app.models.financing import FinancingTerms
    with SessionLocal() as db:
        for p in db.scalars(select(Product).where(Product.sku.like(f'{PFX}%'))):
            db.delete(p)  # cascades components + price overrides
        for f in db.scalars(select(FinancingTerms).where(FinancingTerms.name.like(f'{PFX}%'))):
            db.delete(f)
        db.commit()
        db.execute(text('DELETE FROM customer_price_overrides WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM customer_pricing WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(tid)})
        db.commit()


def _svc(SessionLocal):
    from app.services.product_admin_service import ProductAdminService
    return ProductAdminService, SessionLocal


def test_create_and_get_product(admin_db):
    SessionLocal, _ = admin_db
    from app.services.product_admin_service import ProductAdminService
    with SessionLocal() as db:
        p = ProductAdminService(db).create_product({
            'vendor': 'ACME', 'technology': 'Test', 'sku': f'{PFX}ROUTER', 'name': 'Test Router',
            'margin_pct': 0.25, 'leasing_pct': 0.06,
        })
        assert p.sku == f'{PFX}ROUTER' and float(p.margin_pct) == 0.25
        got = ProductAdminService(db).get_product(p.id)
        assert got.id == p.id


def test_duplicate_sku_rejected(admin_db):
    SessionLocal, _ = admin_db
    from app.services.product_admin_service import ProductAdminService
    with SessionLocal() as db:
        with pytest.raises(AppError):
            ProductAdminService(db).create_product({
                'vendor': 'ACME', 'technology': 'Test', 'sku': f'{PFX}ROUTER', 'name': 'dup'})


def test_update_product(admin_db):
    SessionLocal, _ = admin_db
    from app.services.product_admin_service import ProductAdminService
    with SessionLocal() as db:
        p = ProductAdminService(db).create_product({
            'vendor': 'ACME', 'technology': 'Test', 'sku': f'{PFX}UPD', 'name': 'Before'})
        p2 = ProductAdminService(db).update_product(p.id, {'name': 'After', 'margin_pct': 0.30})
        assert p2.name == 'After' and float(p2.margin_pct) == 0.30


def test_add_and_update_component(admin_db):
    SessionLocal, _ = admin_db
    from app.services.product_admin_service import ProductAdminService
    with SessionLocal() as db:
        svc = ProductAdminService(db)
        p = svc.create_product({'vendor': 'ACME', 'technology': 'Test', 'sku': f'{PFX}COMP', 'name': 'C'})
        c = svc.add_component(p.id, {
            'component_type': 'DEVICE', 'label': 'box', 'vendor_cost': 100, 'billing': 'ONE_TIME'})
        assert float(c.vendor_cost) == 100 and c.component_type.value == 'DEVICE'
        c2 = svc.update_component(c.id, {'vendor_cost': 120, 'is_active': False})
        assert float(c2.vendor_cost) == 120 and c2.is_active is False


def test_invalid_component_type_rejected(admin_db):
    SessionLocal, _ = admin_db
    from app.services.product_admin_service import ProductAdminService
    with SessionLocal() as db:
        svc = ProductAdminService(db)
        p = svc.create_product({'vendor': 'ACME', 'technology': 'Test', 'sku': f'{PFX}BAD', 'name': 'B'})
        with pytest.raises(AppError):
            svc.add_component(p.id, {'component_type': 'WIDGET', 'label': 'x', 'vendor_cost': 1})


def test_list_products_filter(admin_db):
    SessionLocal, _ = admin_db
    from app.services.product_admin_service import ProductAdminService
    with SessionLocal() as db:
        rows = ProductAdminService(db).list_products(vendor='ACME')
        assert all(r.vendor == 'ACME' for r in rows)
        assert any(r.sku == f'{PFX}ROUTER' for r in rows)


def test_admin_edit_feeds_pricing_engine(admin_db):
    """Create a product+component via admin, then price it — proves the loop."""
    SessionLocal, tid = admin_db
    from app.services.product_admin_service import ProductAdminService
    from app.services.component_pricing_service import ComponentPricingService
    with SessionLocal() as db:
        svc = ProductAdminService(db)
        p = svc.create_product({
            'vendor': 'ACME', 'technology': 'Test', 'sku': f'{PFX}ENGINE', 'name': 'Engine Test',
            'margin_pct': 0.25, 'leasing_pct': 0.05})
        svc.add_component(p.id, {'component_type': 'DEVICE', 'label': 'box', 'vendor_cost': 100, 'billing': 'ONE_TIME'})
        result = ComponentPricingService(db).price_product(p.id, financial_model='CAPEX')
        assert result['one_time_total'] == Decimal('125.00')  # 100 * 1.25


def test_financing_terms_default_is_exclusive(admin_db):
    SessionLocal, tid = admin_db
    from app.services.product_admin_service import ProductAdminService
    from app.models.financing import FinancingTerms
    from sqlalchemy import select
    with SessionLocal() as db:
        svc = ProductAdminService(db)
        svc.create_financing_terms(tid, {'name': f'{PFX}24mo', 'term_months': 24, 'annual_rate_pct': 0.04, 'is_default': True})
        svc.create_financing_terms(tid, {'name': f'{PFX}48mo', 'term_months': 48, 'annual_rate_pct': 0.07, 'is_default': True})
        defaults = list(db.scalars(
            select(FinancingTerms).where(FinancingTerms.is_default.is_(True), FinancingTerms.tenant_id == tid)
        ))
        # Only one default per tenant.
        assert len(defaults) == 1 and defaults[0].name == f'{PFX}48mo'


def test_update_customer_commercial(admin_db):
    SessionLocal, tid = admin_db
    from app.services.product_admin_service import ProductAdminService
    with SessionLocal() as db:
        p = ProductAdminService(db).update_customer_commercial(
            tid, {'default_margin_pct': 0.18, 'opex_eligible': True, 'credit_status': 'PASS', 'credit_limit': 50000})
        assert float(p.default_margin_pct) == 0.18 and p.opex_eligible is True
        assert p.credit_status == 'PASS' and float(p.credit_limit) == 50000


def test_upsert_price_override_is_idempotent(admin_db):
    SessionLocal, tid = admin_db
    from app.services.product_admin_service import ProductAdminService
    from sqlalchemy import select, func
    from app.models.product import CustomerPriceOverride as CPO
    with SessionLocal() as db:
        svc = ProductAdminService(db)
        p = svc.create_product({'vendor': 'ACME', 'technology': 'Test', 'sku': f'{PFX}OVR', 'name': 'O'})
        svc.upsert_price_override(tid, {'product_id': str(p.id), 'override_margin_pct': 0.10})
        svc.upsert_price_override(tid, {'product_id': str(p.id), 'override_margin_pct': 0.12})  # update, not insert
        rows = db.scalar(select(func.count()).select_from(CPO).where(CPO.tenant_id == tid, CPO.product_id == p.id))
        assert rows == 1
        row = db.scalar(select(CPO).where(CPO.tenant_id == tid, CPO.product_id == p.id))
        assert float(row.override_margin_pct) == 0.12


def test_price_override_requires_target(admin_db):
    SessionLocal, tid = admin_db
    from app.services.product_admin_service import ProductAdminService
    with SessionLocal() as db:
        with pytest.raises(AppError):
            ProductAdminService(db).upsert_price_override(tid, {'override_margin_pct': 0.10})
