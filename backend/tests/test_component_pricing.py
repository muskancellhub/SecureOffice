"""Phase 2/7 tests — ComponentPricingService.

Two layers:
  * Pure unit (no DB): the annuity formula, the D2 markup precedence, the SIM
    flat price, the PAPI zero-margin lock, CAPEX/OPEX/annual cadence —
    exercised on lightweight fakes because price_component() reads only its
    arguments, never the DB.
  * DB integration (skips without Postgres): the pinned Phase 7 example — a
    tenant at 20% markup reproduces $42.88/mo + $30 one-time for the seeded
    90X1 (lease 19.78 + controller 9.30 + line 13.80, SIM one-time 30).

D2 precedence (locked): override → customer_pricing.default_margin_pct →
products.margin_pct → component margin → 25% global.
"""
import uuid as uuid_mod
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.product import ComponentType
from app.services.component_pricing_service import (
    GLOBAL_DEFAULT_MARGIN,
    ComponentPricingService as CPS,
    is_papi_product,
)


# ── fakes ─────────────────────────────────────────────────────────────────────

def _component(*, ctype, cost, billing='RECURRING', margin=None, attributes=None,
               vsku='X', default_qty=1, required=True):
    return SimpleNamespace(
        id='00000000-0000-0000-0000-000000000001',
        component_type=ctype,
        vendor_cost=Decimal(str(cost)),
        billing=billing,
        margin_pct=(Decimal(str(margin)) if margin is not None else None),
        attributes=attributes or {},
        label='fake',
        vendor_component_sku=vsku,
        default_qty=default_qty,
        is_required=required,
    )


def _product(*, margin=None, leasing=None, vendor='MIX Networks', attributes=None):
    return SimpleNamespace(
        margin_pct=(Decimal(str(margin)) if margin is not None else None),
        leasing_pct=(Decimal(str(leasing)) if leasing is not None else None),
        vendor=vendor,
        attributes=attributes or {},
    )


def _svc():
    return CPS(db=None)  # price_component never touches db


# ── annuity ────────────────────────────────────────────────────────────────────

def test_lease_mrc_matches_worked_example():
    assert CPS.lease_mrc(Decimal('660'), Decimal('0.05'), 36) == Decimal('19.78')


def test_lease_mrc_zero_rate_is_straight_line():
    assert CPS.lease_mrc(Decimal('3600'), Decimal('0'), 36) == Decimal('100.00')


# ── D2 markup precedence ──────────────────────────────────────────────────────

def _price(component, product, **kw):
    defaults = dict(financial_model='CAPEX', interval='MONTH', qty=1, annual_rate=Decimal('0.05'), term_months=36)
    defaults.update(kw)
    return _svc().price_component(component, product=product, **defaults)


def test_global_default_is_25_pct_when_nothing_is_set():
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100), _product())
    assert r['margin_pct'] == GLOBAL_DEFAULT_MARGIN == Decimal('0.25')
    assert r['margin_source'] == 'global_default'
    assert r['monthly_unit'] == Decimal('125.00')


def test_tenant_default_beats_product_and_component():
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100, margin='0.10'),
               _product(margin='0.30'),
               customer_pricing=SimpleNamespace(default_margin_pct=Decimal('0.20')))
    assert r['margin_pct'] == Decimal('0.20') and r['margin_source'] == 'customer.default_margin_pct'
    assert r['monthly_unit'] == Decimal('120.00')


def test_null_tenant_default_inherits_down_the_chain():
    # NULL = "not customized" (Phase 7) — falls through to the SKU default.
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100), _product(margin='0.30'),
               customer_pricing=SimpleNamespace(default_margin_pct=None))
    assert r['margin_pct'] == Decimal('0.30') and r['margin_source'] == 'product.margin_pct'


def test_product_margin_beats_component_margin():
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100, margin='0.10'),
               _product(margin='0.30'))
    assert r['margin_pct'] == Decimal('0.30') and r['margin_source'] == 'product.margin_pct'
    assert r['monthly_unit'] == Decimal('130.00')


def test_component_margin_is_last_before_global():
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100, margin='0.10'), _product())
    assert r['margin_pct'] == Decimal('0.10') and r['margin_source'] == 'component.margin_pct'
    assert r['monthly_unit'] == Decimal('110.00')


def test_override_margin_beats_everything_else():
    override = SimpleNamespace(override_margin_pct=Decimal('0.50'), override_unit_price=None)
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100, margin='0.10'),
               _product(margin='0.25'), override=override,
               customer_pricing=SimpleNamespace(default_margin_pct=Decimal('0.20')))
    assert r['margin_pct'] == Decimal('0.50') and r['margin_source'] == 'override_margin_pct'
    assert r['monthly_unit'] == Decimal('150.00')


def test_override_unit_price_wins_over_everything():
    override = SimpleNamespace(override_margin_pct=Decimal('0.50'), override_unit_price=Decimal('77'))
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100, margin='0.10'),
               _product(margin='0.25'), override=override)
    assert r['margin_source'] == 'override_unit_price' and r['monthly_unit'] == Decimal('77.00')


# ── PAPI zero-margin lock (D8) ───────────────────────────────────────────────

def _papi_product():
    return _product(vendor='PAPI', attributes={'source_type': 'paapi'})


def test_papi_product_detection():
    assert is_papi_product(_papi_product())
    assert is_papi_product(_product(vendor='PAPI'))
    assert not is_papi_product(_product(vendor='MIX Networks'))


def test_papi_resells_at_exact_cost_no_markup():
    r = _price(_component(ctype=ComponentType.DEVICE, cost=1299, billing='ONE_TIME'),
               _papi_product(),
               customer_pricing=SimpleNamespace(default_margin_pct=Decimal('0.40')))
    assert r['margin_pct'] == Decimal('0') and r['margin_source'] == 'papi_fixed'
    assert r['one_time_unit'] == Decimal('1299.00')
    assert r['price_editable'] is False


def test_papi_ignores_overrides():
    override = SimpleNamespace(override_margin_pct=Decimal('0.50'), override_unit_price=Decimal('999'))
    r = _price(_component(ctype=ComponentType.DEVICE, cost=1299, billing='ONE_TIME'),
               _papi_product(), override=override)
    assert r['margin_source'] == 'papi_fixed' and r['one_time_unit'] == Decimal('1299.00')
    assert r['price_editable'] is False


def test_non_papi_lines_are_price_editable():
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100), _product())
    assert r['price_editable'] is True


# ── SIM flat price (D6: one-time $30, no margin; per-tenant via override) ────

def test_sim_is_flat_thirty_one_time_no_margin_even_with_product_margin():
    r = _price(_component(ctype=ComponentType.SIM, cost=30, billing='ONE_TIME'), _product(margin='0.50'),
               financial_model='OPEX')
    assert r['margin_pct'] == Decimal('0') and r['margin_source'] == 'flat_price'
    assert r['one_time_unit'] == Decimal('30.00') and r['billing'] == 'ONE_TIME'
    assert r['financed'] is False  # SIM not financed even under OPEX


def test_sim_override_unit_price_beats_flat_price():
    # D6: a tenant-specific SIM price goes through override_unit_price.
    override = SimpleNamespace(override_margin_pct=None, override_unit_price=Decimal('25'))
    r = _price(_component(ctype=ComponentType.SIM, cost=30, billing='ONE_TIME'), _product(),
               override=override)
    assert r['margin_source'] == 'override_unit_price' and r['one_time_unit'] == Decimal('25.00')


# ── CAPEX / OPEX / annual cadence ────────────────────────────────────────────

def test_device_capex_is_one_time_sell():
    r = _price(_component(ctype=ComponentType.DEVICE, cost=550, billing='ONE_TIME'),
               _product(margin='0.20', leasing='0.05'), financial_model='CAPEX')
    assert r['billing'] == 'ONE_TIME' and r['one_time_unit'] == Decimal('660.00')
    assert r['monthly_unit'] == Decimal('0')


def test_device_opex_is_financed_lease():
    r = _price(_component(ctype=ComponentType.DEVICE, cost=550, billing='ONE_TIME'),
               _product(margin='0.20', leasing='0.05'), financial_model='OPEX', term_months=36)
    assert r['financed'] is True and r['billing'] == 'RECURRING'
    assert r['monthly_unit'] == Decimal('19.78')


def test_installation_one_time_not_financed_under_opex():
    # Professional services stay one-time even under OPEX (only hardware is financed).
    r = _price(_component(ctype=ComponentType.INSTALLATION, cost=40, billing='ONE_TIME'),
               _product(margin='0.20'), financial_model='OPEX')
    assert r['financed'] is False and r['billing'] == 'ONE_TIME'
    assert r['one_time_unit'] == Decimal('48.00')


def test_annual_is_monthly_times_twelve():
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100), _product(margin='0.20'),
               interval='YEAR')
    assert r['monthly_unit'] == Decimal('120.00')          # underlying MRC unchanged
    assert r['unit_price'] == Decimal('1440.00')           # displayed at annual cadence
    assert r['interval'] == 'YEAR'


# ── DB integration: pinned Phase 7 example against seeded 90X1 ────────────────

@pytest.fixture(scope='module')
def seeded_db():
    from sqlalchemy import text
    from app.core.database import engine
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover - env dependent
        pytest.skip(f'No reachable database: {exc}')
    import app.models  # noqa: F401
    from app.core.database import SessionLocal, Base
    from app.core.runtime_migrations import apply_runtime_migrations
    from app.services.catalog_service import CatalogService
    Base.metadata.create_all(bind=engine)
    apply_runtime_migrations()
    with SessionLocal() as db:
        CatalogService(db).seed_mix_products()
    return SessionLocal


@pytest.fixture(scope='module')
def tenant_at_20(seeded_db):
    """A tenant whose tenant-wide markup is explicitly 20% (the pinned example)."""
    from app.models.pricing import CustomerPricing
    from app.models.tenant import Tenant
    with seeded_db() as db:
        tenant = Tenant(name=f'pricing-test-{uuid_mod.uuid4().hex[:8]}')
        db.add(tenant)
        db.flush()
        db.add(CustomerPricing(
            tenant_id=tenant.id,
            default_discount_pct=Decimal('0.30'),
            default_margin_pct=Decimal('0.20'),
        ))
        db.commit()
        return str(tenant.id)


def _x1_selections(db):
    from sqlalchemy import select
    from app.models.product import Product, ProductComponent
    p = db.scalar(select(Product).where(Product.sku == '90X1'))
    comps = {c.vendor_component_sku: c for c in db.scalars(
        select(ProductComponent).where(ProductComponent.product_id == p.id))}
    return p, {str(comps['SERV1970'].id): 1, str(comps['PAPI-SIM'].id): 1}


def test_90x1_opex_pinned_example_42_88_plus_30(seeded_db, tenant_at_20):
    # Phase 7 D6: a 20% tenant → lease 19.78 + ctrl 9.30 + line 13.80 = 42.88/mo
    # plus the $30 one-time SIM.
    with seeded_db() as db:
        p, sel = _x1_selections(db)
        r = CPS(db).price_product(p.id, financial_model='OPEX', interval='MONTH',
                                  selections=sel, tenant_id=tenant_at_20)
        assert r['monthly_total'] == Decimal('42.88')
        assert r['one_time_total'] == Decimal('30.00')
        assert r['projected_term_cost'] == Decimal('1573.68')  # 30 + 42.88 * 36
        device = next(l for l in r['lines'] if l['component_type'] == 'DEVICE')
        assert device['financed'] is True and device['unit_price'] == Decimal('19.78')
        sim = next(l for l in r['lines'] if l['component_type'] == 'SIM')
        assert sim['billing'] == 'ONE_TIME' and sim['one_time_unit'] == Decimal('30.00')


def test_90x1_capex_at_20_pct_is_690_plus_23_10(seeded_db, tenant_at_20):
    with seeded_db() as db:
        p, sel = _x1_selections(db)
        r = CPS(db).price_product(p.id, financial_model='CAPEX', interval='MONTH',
                                  selections=sel, tenant_id=tenant_at_20)
        assert r['one_time_total'] == Decimal('690.00')  # device 660 + SIM 30
        assert r['monthly_total'] == Decimal('23.10')     # 9.30 + 13.80


def test_90x1_opex_annual_is_times_twelve(seeded_db, tenant_at_20):
    with seeded_db() as db:
        p, sel = _x1_selections(db)
        r = CPS(db).price_product(p.id, financial_model='OPEX', interval='YEAR',
                                  selections=sel, tenant_id=tenant_at_20)
        assert r['recurring_total_at_interval'] == Decimal('514.56')  # 42.88 * 12
        assert r['one_time_total'] == Decimal('30.00')                # SIM stays one-time


def test_90x1_without_tenant_uses_global_25_default(seeded_db):
    # No tenant context → every margined line resolves to the 25% global default.
    with seeded_db() as db:
        p, sel = _x1_selections(db)
        r = CPS(db).price_product(p.id, financial_model='CAPEX', interval='MONTH', selections=sel)
        device = next(l for l in r['lines'] if l['component_type'] == 'DEVICE')
        assert device['margin_source'] == 'global_default'
        assert device['one_time_unit'] == Decimal('687.50')  # 550 × 1.25


def test_tenant_margins_reprice_per_tenant(seeded_db, tenant_at_20):
    # Same SKU, two tenants, two prices (D2: per-tenant markup).
    with seeded_db() as db:
        p, sel = _x1_selections(db)
        at_20 = CPS(db).price_product(p.id, financial_model='CAPEX', selections=sel, tenant_id=tenant_at_20)
        default = CPS(db).price_product(p.id, financial_model='CAPEX', selections=sel)
        d20 = next(l for l in at_20['lines'] if l['component_type'] == 'DEVICE')
        d25 = next(l for l in default['lines'] if l['component_type'] == 'DEVICE')
        assert d20['one_time_unit'] == Decimal('660.00')
        assert d25['one_time_unit'] == Decimal('687.50')


def test_invalid_financial_model_rejected(seeded_db):
    from app.core.exceptions import AppError
    with seeded_db() as db:
        p, sel = _x1_selections(db)
        with pytest.raises(AppError):
            CPS(db).price_product(p.id, financial_model='LEASE', selections=sel)
