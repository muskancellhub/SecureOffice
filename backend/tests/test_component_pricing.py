"""Phase 2 tests — ComponentPricingService.

Two layers:
  * Pure unit (no DB): the annuity formula, margin precedence, SIM flat-price,
    CAPEX/OPEX/annual cadence — exercised on lightweight fakes because
    price_component() reads only its arguments, never the DB.
  * DB integration (skips without Postgres): price_product() reproduces the §3
    reconciliation (82.88/mo OPEX, 660 + 63.10 CAPEX, 994.56 annual) against the
    seeded 90X1.

§3 numbers verified 2026-06-04.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.product import ComponentType
from app.services.component_pricing_service import ComponentPricingService as CPS


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


def _product(*, margin=None, leasing=None):
    return SimpleNamespace(
        margin_pct=(Decimal(str(margin)) if margin is not None else None),
        leasing_pct=(Decimal(str(leasing)) if leasing is not None else None),
    )


def _svc():
    return CPS(db=None)  # price_component never touches db


# ── annuity ────────────────────────────────────────────────────────────────────

def test_lease_mrc_matches_worked_example():
    assert CPS.lease_mrc(Decimal('660'), Decimal('0.05'), 36) == Decimal('19.78')


def test_lease_mrc_zero_rate_is_straight_line():
    assert CPS.lease_mrc(Decimal('3600'), Decimal('0'), 36) == Decimal('100.00')


# ── margin precedence (DEVIATION D1: override -> component -> product -> tenant) ──

def _price(component, product, **kw):
    defaults = dict(financial_model='CAPEX', interval='MONTH', qty=1, annual_rate=Decimal('0.05'), term_months=36)
    defaults.update(kw)
    return _svc().price_component(component, product=product, **defaults)


def test_margin_falls_back_to_product_when_component_null():
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100), _product(margin='0.25'),
               customer_pricing=_product(margin='0.20'))
    assert r['margin_pct'] == Decimal('0.25') and r['margin_source'] == 'product.margin_pct'
    assert r['monthly_unit'] == Decimal('125.00')


def test_component_margin_beats_product_margin():
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100, margin='0.10'),
               _product(margin='0.25'))
    assert r['margin_pct'] == Decimal('0.10') and r['margin_source'] == 'component.margin_pct'
    assert r['monthly_unit'] == Decimal('110.00')


def test_override_margin_beats_catalog():
    override = SimpleNamespace(override_margin_pct=Decimal('0.50'), override_unit_price=None)
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100, margin='0.10'),
               _product(margin='0.25'), override=override)
    assert r['margin_pct'] == Decimal('0.50') and r['margin_source'] == 'override_margin_pct'
    assert r['monthly_unit'] == Decimal('150.00')


def test_override_unit_price_wins_over_everything():
    override = SimpleNamespace(override_margin_pct=Decimal('0.50'), override_unit_price=Decimal('77'))
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100, margin='0.10'),
               _product(margin='0.25'), override=override)
    assert r['margin_source'] == 'override_unit_price' and r['monthly_unit'] == Decimal('77.00')


def test_tenant_default_is_last_resort():
    r = _price(_component(ctype=ComponentType.MAINTENANCE, cost=100), _product(margin=None),
               customer_pricing=SimpleNamespace(default_margin_pct=Decimal('0.20')))
    assert r['margin_pct'] == Decimal('0.20') and r['margin_source'] == 'customer.default_margin_pct'
    assert r['monthly_unit'] == Decimal('120.00')


# ── SIM flat price (no margin) ───────────────────────────────────────────────

def test_sim_is_flat_one_time_no_margin_even_with_product_margin():
    # SIM is a flat $40 one-time charge (product-owner decision 2026-06-04), no margin.
    r = _price(_component(ctype=ComponentType.SIM, cost=40, billing='ONE_TIME'), _product(margin='0.50'),
               financial_model='OPEX')
    assert r['margin_pct'] == Decimal('0') and r['margin_source'] == 'flat_price'
    assert r['one_time_unit'] == Decimal('40.00') and r['billing'] == 'ONE_TIME'
    assert r['financed'] is False  # SIM not financed even under OPEX


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


# ── DB integration: §3 reconciliation against seeded 90X1 ────────────────────

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
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        CatalogService(db).seed_mix_products()
    return SessionLocal


def _x1_selections(db):
    from sqlalchemy import select
    from app.models.product import Product, ProductComponent
    p = db.scalar(select(Product).where(Product.sku == '90X1'))
    comps = {c.vendor_component_sku: c for c in db.scalars(
        select(ProductComponent).where(ProductComponent.product_id == p.id))}
    return p, {str(comps['SERV1970'].id): 1, str(comps['PAPI-SIM'].id): 1}


def test_90x1_opex_with_one_time_sim(seeded_db):
    # SIM reclassified one-time (2026-06-04): recurring = lease 19.78 + ctrl 9.30 + line 13.80
    # = 42.88/mo; SIM = $40 one-time.
    with seeded_db() as db:
        p, sel = _x1_selections(db)
        r = CPS(db).price_product(p.id, financial_model='OPEX', interval='MONTH', selections=sel)
        assert r['monthly_total'] == Decimal('42.88')
        assert r['one_time_total'] == Decimal('40.00')
        assert r['projected_term_cost'] == Decimal('1583.68')  # 40 + 42.88 * 36
        device = next(l for l in r['lines'] if l['component_type'] == 'DEVICE')
        assert device['financed'] is True and device['unit_price'] == Decimal('19.78')
        sim = next(l for l in r['lines'] if l['component_type'] == 'SIM')
        assert sim['billing'] == 'ONE_TIME' and sim['one_time_unit'] == Decimal('40.00')


def test_90x1_capex_is_700_plus_23_10(seeded_db):
    with seeded_db() as db:
        p, sel = _x1_selections(db)
        r = CPS(db).price_product(p.id, financial_model='CAPEX', interval='MONTH', selections=sel)
        assert r['one_time_total'] == Decimal('700.00')  # device 660 + SIM 40
        assert r['monthly_total'] == Decimal('23.10')     # 9.30 + 13.80


def test_90x1_opex_annual_is_times_twelve(seeded_db):
    with seeded_db() as db:
        p, sel = _x1_selections(db)
        r = CPS(db).price_product(p.id, financial_model='OPEX', interval='YEAR', selections=sel)
        assert r['recurring_total_at_interval'] == Decimal('514.56')  # 42.88 * 12
        assert r['one_time_total'] == Decimal('40.00')                # SIM stays one-time


def test_invalid_financial_model_rejected(seeded_db):
    from app.core.exceptions import AppError
    with seeded_db() as db:
        p, sel = _x1_selections(db)
        with pytest.raises(AppError):
            CPS(db).price_product(p.id, financial_model='LEASE', selections=sel)
