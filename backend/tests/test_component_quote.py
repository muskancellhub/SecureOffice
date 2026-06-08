"""Phase 3 tests — component-driven quote assembly, add-on, OPEX gate, convert.

Layers:
  * Pure unit (no DB): the new glue logic on QuoteService (billing mapping,
    requires-a-device validation, line-kwargs snapshot mapping).
  * DB integration (skips without Postgres): create_component_quote,
    add_component_line, the OPEX-eligibility gate, and convert_quote carrying
    the §4.8 snapshots onto order lines. Uses a throwaway tenant cleaned up in
    teardown; lifecycle/notification side-effects are monkeypatched out.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.exceptions import AppError
from app.models.quote import BillingInterval, BillingType, QuoteLineType
from app.services.quote_service import QuoteService


# ── pure unit ─────────────────────────────────────────────────────────────────

def test_billing_mapping():
    assert QuoteService._billing_from_engine_line({'billing': 'RECURRING', 'interval': 'MONTH'}) == (
        BillingType.RECURRING, BillingInterval.MONTH)
    assert QuoteService._billing_from_engine_line({'billing': 'RECURRING', 'interval': 'YEAR'}) == (
        BillingType.RECURRING, BillingInterval.YEAR)
    assert QuoteService._billing_from_engine_line({'billing': 'ONE_TIME', 'interval': None}) == (
        BillingType.ONE_TIME, None)


def test_requires_device_raises_for_orphan_line():
    with pytest.raises(AppError):
        QuoteService._validate_requires_device({'lines': [{'component_type': 'LINE_CHARGE'}]})
    with pytest.raises(AppError):
        QuoteService._validate_requires_device({'lines': [{'component_type': 'SIM'}]})


def test_requires_device_ok_when_device_present():
    # Should not raise.
    QuoteService._validate_requires_device(
        {'lines': [{'component_type': 'DEVICE'}, {'component_type': 'LINE_CHARGE'}]}
    )


def test_component_line_kwargs_maps_snapshots():
    svc = QuoteService(None)  # __init__ only stores db on repos; safe with None
    pid = uuid.uuid4()
    product = SimpleNamespace(id=pid, vendor='MIX Networks', leasing_pct=Decimal('0.05'))
    result = {'annual_rate_pct': Decimal('0.05'), 'term_months': 36}
    line = {
        'component_id': str(uuid.uuid4()), 'component_type': 'DEVICE', 'label': 'POTS device',
        'vendor_component_sku': 'PROD7901', 'qty': 1, 'vendor_cost': Decimal('550'),
        'margin_pct': Decimal('0.20'), 'margin_source': 'product.margin_pct',
        'billing': 'RECURRING', 'interval': 'MONTH', 'financed': True, 'unit_price': Decimal('19.78'),
    }
    kw = svc._component_line_kwargs('qid', product, 'OPEX', result, line, None)
    assert kw['line_type'] == QuoteLineType.DEVICE
    assert kw['billing_type'] == BillingType.RECURRING and kw['interval'] == BillingInterval.MONTH
    assert kw['component_type'] == 'DEVICE' and kw['financial_model'] == 'OPEX'
    assert kw['product_id'] == pid
    assert kw['cost_snapshot'] == Decimal('550') and kw['margin_pct_snapshot'] == Decimal('0.20')
    assert kw['leasing_pct_snapshot'] == Decimal('0.05') and kw['term_months'] == 36
    assert kw['final_unit_price_snapshot'] == 19.78
    assert kw['vendor_snapshot'] == 'MIX Networks'


def test_component_line_kwargs_one_time_has_no_lease_fields():
    svc = QuoteService(None)
    product = SimpleNamespace(id=uuid.uuid4(), vendor='MIX Networks', leasing_pct=Decimal('0.05'))
    line = {
        'component_id': str(uuid.uuid4()), 'component_type': 'SIM', 'label': 'SIM',
        'vendor_component_sku': 'PAPI-SIM', 'qty': 1, 'vendor_cost': Decimal('40'),
        'margin_pct': Decimal('0'), 'margin_source': 'flat_price',
        'billing': 'ONE_TIME', 'interval': None, 'financed': False, 'unit_price': Decimal('40.00'),
    }
    kw = svc._component_line_kwargs('qid', product, 'OPEX', {'annual_rate_pct': Decimal('0.05'), 'term_months': 36}, line, None)
    assert kw['billing_type'] == BillingType.ONE_TIME and kw['interval'] is None
    assert kw['leasing_pct_snapshot'] is None and kw['term_months'] is None


# ── DB integration ────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def setup():
    from sqlalchemy import text, select
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover - env dependent
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
        db.add(Tenant(id=tid, name='PH3 Test Tenant'))
        db.flush()  # tenant must exist before FK-dependent rows
        db.add(User(id=uid, email=f'ph3-{tid}@test.local', name='PH3 Tester',
                    tenant_id=tid, role=UserRole.ADMIN, is_verified=True,
                    password_hash='x'))  # LOCAL provider requires a password hash
        db.add(TenantOnboarding(
            tenant_id=tid, organization_name='PH3 Org', admin_name='Admin',
            admin_email='admin@test.local', tax_id='TAX-PH3',
            credit_validation_status='VERIFIED', tax_validation_status='VERIFIED',
            company_setup_completed=True, payment_validation_status='VERIFIED',
        ))
        db.add(CustomerPricing(tenant_id=tid, opex_eligible=False))
        db.commit()

    current_user = {'user_id': str(uid), 'tenant_id': str(tid), 'role': UserRole.ADMIN.value}
    yield SessionLocal, current_user, tid

    # Teardown — orders/quotes cascade their lines; lifecycle side-effects are
    # monkeypatched off in the convert test so nothing else references the tenant.
    from app.models.order import Order
    from app.models.quote import Quote
    with SessionLocal() as db:
        for o in db.scalars(select(Order).where(Order.tenant_id == tid)):
            db.delete(o)
        for q in db.scalars(select(Quote).where(Quote.tenant_id == tid)):
            db.delete(q)
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


def test_create_capex_quote_persists_snapshots_and_tree(setup):
    SessionLocal, cu, _ = setup
    with SessionLocal() as db:
        p, comps = _x1(db)
        sel = {str(comps['SERV1970'].id): 1, str(comps['PAPI-SIM'].id): 1}
        q = QuoteService(db).create_component_quote(
            cu, {'product_id': str(p.id), 'financial_model': 'CAPEX', 'interval': 'MONTH', 'selections': sel})

        assert q.financial_model == 'CAPEX' and q.subscription_interval == 'MONTH'
        assert q.one_time_total == Decimal('700.00')  # device 660 + SIM 40
        assert q.monthly_total == Decimal('23.10')    # ctrl 9.30 + line 13.80

        device = next(l for l in q.lines if l.component_type == 'DEVICE')
        assert device.product_id == p.id and device.component_id is not None
        assert device.cost_snapshot == Decimal('550') and device.margin_pct_snapshot == Decimal('0.20')
        assert device.financial_model == 'CAPEX'

        # children hang off the device line
        line_charge = next(l for l in q.lines if l.component_type == 'LINE_CHARGE')
        sim = next(l for l in q.lines if l.component_type == 'SIM')
        assert line_charge.parent_line_id == device.id
        assert sim.parent_line_id == device.id
        assert sim.billing_type == BillingType.ONE_TIME


def test_opex_blocked_when_not_eligible(setup):
    from app.core.exceptions import ForbiddenError
    SessionLocal, cu, _ = setup
    with SessionLocal() as db:
        p, comps = _x1(db)
        sel = {str(comps['SERV1970'].id): 1}
        with pytest.raises(ForbiddenError):
            QuoteService(db).create_component_quote(
                cu, {'product_id': str(p.id), 'financial_model': 'OPEX', 'selections': sel})


def test_opex_allowed_after_enabling_flag(setup):
    from app.models.pricing import CustomerPricing
    SessionLocal, cu, tid = setup
    with SessionLocal() as db:
        cp = db.get(CustomerPricing, tid)
        cp.opex_eligible = True
        db.commit()
    with SessionLocal() as db:
        p, comps = _x1(db)
        sel = {str(comps['SERV1970'].id): 1, str(comps['PAPI-SIM'].id): 1}
        q = QuoteService(db).create_component_quote(
            cu, {'product_id': str(p.id), 'financial_model': 'OPEX', 'interval': 'MONTH', 'selections': sel})
        assert q.monthly_total == Decimal('42.88')   # lease 19.78 + 9.30 + 13.80
        assert q.one_time_total == Decimal('40.00')  # SIM
        device = next(l for l in q.lines if l.component_type == 'DEVICE')
        assert device.financial_model == 'OPEX' and device.term_months == 36
        assert device.leasing_pct_snapshot == Decimal('0.05')


def test_add_component_changes_quantity(setup):
    SessionLocal, cu, _ = setup
    with SessionLocal() as db:
        p, comps = _x1(db)
        sel = {str(comps['SERV1970'].id): 1}
        svc = QuoteService(db)
        q = svc.create_component_quote(
            cu, {'product_id': str(p.id), 'financial_model': 'CAPEX', 'interval': 'MONTH', 'selections': sel})
        assert q.monthly_total == Decimal('23.10')  # ctrl 9.30 + 1 line 13.80

        q2 = svc.add_component_line(cu, str(q.id), {'component_id': str(comps['SERV1970'].id), 'qty': 3})
        assert q2.monthly_total == Decimal('50.70')  # ctrl 9.30 + 3 lines 41.40
        voice = next(l for l in q2.lines if l.component_type == 'LINE_CHARGE')
        assert voice.qty == 3


def test_convert_carries_snapshots_to_order(setup, monkeypatch):
    SessionLocal, cu, _ = setup
    # Strip lifecycle + notification side-effects so cleanup stays trivial.
    monkeypatch.setattr('app.services.quote_service.LifecycleService.ensure_order_lifecycle',
                        lambda self, order, user: None)
    monkeypatch.setattr('app.services.quote_service.OrderNotificationService.send_order_captured_notification',
                        lambda self, order_id: True)

    with SessionLocal() as db:
        p, comps = _x1(db)
        sel = {str(comps['SERV1970'].id): 1, str(comps['PAPI-SIM'].id): 1}
        svc = QuoteService(db)
        q = svc.create_component_quote(
            cu, {'product_id': str(p.id), 'financial_model': 'CAPEX', 'interval': 'MONTH', 'selections': sel})
        svc.accept_quote(cu, str(q.id))
        _, order = svc.convert_quote(cu, str(q.id))

        assert order.financial_model == 'CAPEX'
        device = next(l for l in order.lines if l.component_type == 'DEVICE')
        assert device.product_id == p.id and device.component_id is not None
        assert device.cost_snapshot == Decimal('550') and device.margin_pct_snapshot == Decimal('0.20')
        # parent/child tree preserved across conversion
        line_charge = next(l for l in order.lines if l.component_type == 'LINE_CHARGE')
        assert line_charge.parent_line_id == device.id
