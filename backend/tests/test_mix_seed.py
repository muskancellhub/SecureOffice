"""Phase 1 tests — MIX seed data + schema/seed integration.

Two layers:
  * Data validation (always runs, no DB): the seed constants reproduce the MIX
    agreement's numbers — the inputs the §3 worked example is built on.
  * DB integration (skips if no reachable Postgres): migrations + create_all +
    seed succeed and are idempotent.

Source verified against MIX Networks Reseller Master Services Agreement.docx,
2026-06-04.
"""
from decimal import Decimal

import pytest

from app.services import mix_seed
from app.models.product import ComponentType, ComponentUom


# ── Data validation (no DB required) ──────────────────────────────────────────

def _device(sku):
    return next(d for d in mix_seed.DEVICE_PRODUCTS if d['sku'] == sku)


def _shared(vendor_sku):
    return next(c for c in mix_seed.SHARED_COMPONENTS if c[2] == vendor_sku)


def test_device_costs_match_agreement():
    x1 = _device('90X1')
    assert x1['vendor_sku'] == 'PROD7901'
    assert x1['device_cost'] == '550.00' and x1['device_msrp'] == '675.00'
    assert (x1['maint_cost'], x1['maint_sku']) == ('7.75', 'SERV2158')

    x2 = _device('90X2')
    assert x2['vendor_sku'] == 'PROD2279'
    assert x2['device_cost'] == '280.00' and x2['device_msrp'] == '365.00'
    assert (x2['maint_cost'], x2['maint_sku']) == ('5.75', 'SERV2290')

    nfr = _device('90X2-NFR')
    assert nfr['device_cost'] == '240.00' and nfr['device_msrp'] is None
    assert nfr['sellable'] is False


def test_capacity_metadata():
    assert _device('90X1')['capacity'] == {'fxs_port': 8, 'lan_port': 2, 'wan_port': 1, 'max_sims': 2}
    assert _device('90X2')['capacity'] == {'fxs_port': 8, 'lan_port': 4, 'wan_port': 1, 'max_sims': 2}


def test_line_charge_costs_and_uom():
    voice = _shared('SERV1970')
    assert voice[0] == ComponentType.LINE_CHARGE and voice[3] == '11.50' and voice[4] == ComponentUom.PER_LINE
    assert voice[9]['consumes'] == {'fxs_port': 1}

    specialty = _shared('SERV1969')
    assert specialty[3] == '15.50' and specialty[4] == ComponentUom.PER_LINE

    seat = _shared('SERV075')
    assert seat[3] == '5.50' and seat[4] == ComponentUom.PER_SEAT


def test_sim_is_flat_forty_one_time_no_margin():
    sim = _shared('PAPI-SIM')
    assert sim[0] == ComponentType.SIM and sim[3] == '40.00'
    assert sim[5] == 'ONE_TIME' and sim[6] is None  # one-time, not monthly (2026-06-04)
    assert sim[9]['flat_price'] is True and sim[9]['source'] == 'PAPI'
    assert sim[9]['consumes'] == {'max_sims': 1}


def test_default_margin_and_leasing():
    assert mix_seed.DEFAULT_MARGIN == Decimal('0.20')
    assert mix_seed.DEFAULT_LEASING == Decimal('0.05')


def test_vendor_terms_are_notes_not_quote_math():
    terms = mix_seed.MIX_VENDOR_TERMS
    assert terms['min_activated_lines_after_ramp'] == 100  # account-level, not per-assembly
    assert terms['platform_branding_fee'] == 1500.00
    assert terms['e911_unregistered_did_penalty_per_call'] == 150.00
    tiers = terms['wholesale_revenue_share']
    assert [t['pct'] for t in tiers] == [0.080, 0.075, 0.070]


def test_accessory_costs():
    assert _shared('PROD7933')[3] == '30.00'   # power inverter
    assert _shared('PROD7643')[3] == '22.00'   # power supply
    assert _shared('PROD7956')[3] == '106.25'  # battery


# ── DB integration (skips without a reachable Postgres) ───────────────────────

@pytest.fixture(scope='module')
def db_available():
    from sqlalchemy import text
    from app.core.database import engine
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover - env dependent
        pytest.skip(f'No reachable database: {exc}')
    return True


def test_migrations_and_seed_idempotent(db_available):
    from sqlalchemy import select, func
    import app.models  # noqa: F401  (register models)
    from app.core.database import engine, SessionLocal, Base
    from app.core.runtime_migrations import apply_runtime_migrations
    from app.services.catalog_service import CatalogService
    from app.models.product import Product, ProductComponent
    from app.models.financing import FinancingTerms

    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        CatalogService(db).seed_mix_products()
    with SessionLocal() as db:
        CatalogService(db).seed_mix_products()  # second pass must not duplicate

    with SessionLocal() as db:
        mix_products = db.scalar(
            select(func.count()).select_from(Product).where(Product.vendor == 'MIX Networks')
        )
        assert mix_products == 3

        p90x1 = db.scalar(select(Product).where(Product.sku == '90X1'))
        assert p90x1 is not None
        assert Decimal(p90x1.margin_pct) == Decimal('0.20')
        assert Decimal(p90x1.leasing_pct) == Decimal('0.05')
        assert p90x1.attributes['capacity']['fxs_port'] == 8

        comps = db.scalars(
            select(ProductComponent).where(ProductComponent.product_id == p90x1.id)
        ).all()
        by_sku = {c.vendor_component_sku: c for c in comps}
        assert Decimal(by_sku['PROD7901'].vendor_cost) == Decimal('550')
        assert Decimal(by_sku['PROD7901'].msrp) == Decimal('675')
        assert by_sku['PROD7901'].component_type == ComponentType.DEVICE
        assert Decimal(by_sku['SERV2158'].vendor_cost) == Decimal('7.75')
        assert by_sku['SERV2158'].billing == 'RECURRING' and by_sku['SERV2158'].interval == 'MONTH'
        assert Decimal(by_sku['SERV1970'].vendor_cost) == Decimal('11.50')
        assert Decimal(by_sku['PAPI-SIM'].vendor_cost) == Decimal('40')
        assert by_sku['PAPI-SIM'].attributes['flat_price'] is True

        # NFR lab unit carries only DEVICE + MAINTENANCE.
        nfr = db.scalar(select(Product).where(Product.sku == '90X2-NFR'))
        nfr_comps = db.scalars(
            select(ProductComponent).where(ProductComponent.product_id == nfr.id)
        ).all()
        assert {c.component_type for c in nfr_comps} == {ComponentType.DEVICE, ComponentType.MAINTENANCE}

        ft = db.scalar(select(FinancingTerms).where(FinancingTerms.is_default.is_(True)))
        assert ft.term_months == 36 and Decimal(ft.annual_rate_pct) == Decimal('0.05')
