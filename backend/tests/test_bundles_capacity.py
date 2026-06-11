"""Phase 5 tests — capacity validation + bundles.

Pure unit (no DB): the resource-agnostic check_capacity / evaluate_constraints.
DB integration (skips without Postgres): capacity blocks over-subscription in
quote assembly; bundle CRUD + expansion into a multi-product quote.
"""
import uuid
from decimal import Decimal

import pytest

from app.core.exceptions import AppError
from app.services.capacity_service import check_capacity, evaluate_constraints


# ── pure unit ─────────────────────────────────────────────────────────────────

def test_check_capacity_ok_within_limit():
    # 90X1: 8 fxs ports, 8 voice lines consuming 1 each → fits.
    assert check_capacity({'fxs_port': 8}, [({'fxs_port': 1}, 8)]) == []


def test_check_capacity_blocks_oversubscription():
    v = check_capacity({'fxs_port': 8}, [({'fxs_port': 1}, 9)])
    assert v == [{'resource': 'fxs_port', 'used': 9, 'provided': 8}]


def test_check_capacity_missing_key_is_zero():
    # A device that doesn't declare a resource provides 0 of it → any use violates.
    v = check_capacity({'lan_port': 2}, [({'fxs_port': 1}, 1)])
    assert v == [{'resource': 'fxs_port', 'used': 1, 'provided': 0}]


def test_check_capacity_components_without_consumes_pass():
    assert check_capacity({'fxs_port': 8}, [(None, 1), ({}, 3)]) == []


def test_evaluate_constraints_min_max_compat():
    used = {'lines': 0, 'seats': 5}
    cons = [
        {'resource_key': 'lines', 'type': 'MIN', 'value': 1},   # 0 < 1 → violation
        {'resource_key': 'seats', 'type': 'MAX', 'value': 10},  # 5 ≤ 10 → ok
        {'resource_key': 'fit', 'type': 'COMPAT', 'value': False},  # not compatible
    ]
    out = evaluate_constraints(cons, used, {})
    types = {(v['resource'], v['type']) for v in out}
    assert ('lines', 'MIN') in types and ('fit', 'COMPAT') in types
    assert ('seats', 'MAX') not in types


# ── DB integration ────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def setup():
    from sqlalchemy import text, select
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401
    from app.core.runtime_migrations import apply_runtime_migrations
    from app.services.catalog_service import CatalogService
    from app.models.tenant import Tenant
    from app.models.user import User, UserRole
    from app.models.onboarding import TenantOnboarding
    from app.models.pricing import CustomerPricing

    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    tid = uuid.uuid4()
    uid = uuid.uuid4()
    with SessionLocal() as db:
        CatalogService(db).seed_mix_products()
        db.add(Tenant(id=tid, name='PH5 Test Tenant'))
        db.flush()
        db.add(User(id=uid, email=f'ph5-{tid}@test.local', name='PH5', tenant_id=tid,
                    role=UserRole.ADMIN, is_verified=True, password_hash='x'))
        db.add(TenantOnboarding(
            tenant_id=tid, organization_name='PH5', admin_name='A', admin_email='a@test.local',
            tax_id='TAX-PH5', credit_validation_status='VERIFIED', tax_validation_status='VERIFIED',
            company_setup_completed=True, payment_validation_status='VERIFIED',
            operations_address={'line1': '1 Main St', 'city': 'Austin', 'state': 'TX', 'postal_code': '78701'},
            billing_same_as_operations=True))
        db.add(CustomerPricing(tenant_id=tid, opex_eligible=True))
        db.commit()

    cu = {'user_id': str(uid), 'tenant_id': str(tid), 'role': UserRole.ADMIN.value}
    yield SessionLocal, cu, tid

    from app.models.order import Order
    from app.models.quote import Quote
    from app.models.product import Bundle
    with SessionLocal() as db:
        for o in db.scalars(select(Order).where(Order.tenant_id == tid)):
            db.delete(o)
        for q in db.scalars(select(Quote).where(Quote.tenant_id == tid)):
            db.delete(q)
        for b in db.scalars(select(Bundle).where(Bundle.sku.like('PH5-%'))):
            db.delete(b)
        db.commit()
        for tbl in ('customer_pricing', 'tenant_onboarding', 'users'):
            db.execute(text(f'DELETE FROM {tbl} WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(tid)})
        db.commit()


def _x1(db):
    from sqlalchemy import select
    from app.models.product import Product, ProductComponent
    p = db.scalar(select(Product).where(Product.sku == '90X1'))
    comps = {c.vendor_component_sku: c for c in db.scalars(
        select(ProductComponent).where(ProductComponent.product_id == p.id))}
    return p, comps


def test_capacity_blocks_too_many_lines(setup):
    SessionLocal, cu, _ = setup
    from app.services.quote_service import QuoteService
    with SessionLocal() as db:
        p, comps = _x1(db)
        # 90X1 has 8 fxs ports; 9 voice lines must be rejected.
        sel = {str(comps['SERV1970'].id): 9}
        with pytest.raises(AppError) as exc:
            QuoteService(db).create_component_quote(
                cu, {'product_id': str(p.id), 'financial_model': 'CAPEX', 'selections': sel})
        assert 'capacity' in str(exc.value).lower()


def test_capacity_allows_within_limit(setup):
    SessionLocal, cu, _ = setup
    from app.services.quote_service import QuoteService
    with SessionLocal() as db:
        p, comps = _x1(db)
        sel = {str(comps['SERV1970'].id): 8}  # exactly 8 ports
        q = QuoteService(db).create_component_quote(
            cu, {'product_id': str(p.id), 'financial_model': 'CAPEX', 'selections': sel})
        assert q is not None


def test_bundle_crud_and_expansion(setup):
    SessionLocal, cu, _ = setup
    from sqlalchemy import select
    from app.services.product_admin_service import ProductAdminService
    from app.services.quote_service import QuoteService
    from app.models.product import Product
    with SessionLocal() as db:
        x1 = db.scalar(select(Product).where(Product.sku == '90X1'))
        x2 = db.scalar(select(Product).where(Product.sku == '90X2'))
        admin = ProductAdminService(db)
        bundle = admin.create_bundle({'sku': 'PH5-STARTER', 'name': 'POTS Starter Bundle'})
        admin.add_bundle_item(bundle.id, {'product_id': str(x1.id), 'sort_order': 0})
        admin.add_bundle_item(bundle.id, {'product_id': str(x2.id), 'sort_order': 1})

        q = QuoteService(db).create_bundle_quote(
            cu, {'bundle_id': str(bundle.id), 'financial_model': 'CAPEX', 'interval': 'MONTH'})

        device_lines = [l for l in q.lines if l.component_type == 'DEVICE']
        assert len(device_lines) == 2  # one device per product
        # CAPEX one-time = 90X1 660 + 90X2 336; monthly = maint 9.30 + 6.90
        assert q.one_time_total == Decimal('996.00')
        assert q.monthly_total == Decimal('16.20')
