"""Phase 7 WS1/WS3/WS7 — catalog unification (DB integration, skips without Postgres).

  * the one-shot backfill turns every legacy catalog_items row into a product
    (DEVICE component + optional MANAGED_SERVICE component, PAPI flagged,
    legacy id mapped) and is re-runnable;
  * importers write products directly;
  * the product-backed catalog reprices per tenant; PAPI entries are fixed and
    not price-editable;
  * drop_legacy_catalog_tables retires catalog_items / list_prices and the app
    keeps serving the catalog afterwards.
"""
import uuid
from decimal import Decimal

import pytest

PFX = 'UNIFY-'


@pytest.fixture(scope='module')
def db_setup():
    from sqlalchemy import text
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')
    import app.models  # noqa: F401
    from app.core.runtime_migrations import apply_runtime_migrations
    Base.metadata.create_all(bind=engine)
    apply_runtime_migrations()
    yield SessionLocal

    with SessionLocal() as db:
        db.execute(text("DELETE FROM customer_pricing WHERE tenant_id IN (SELECT id FROM tenants WHERE name LIKE :p)"), {'p': f'{PFX}%'})
        db.execute(text("DELETE FROM tenants WHERE name LIKE :p"), {'p': f'{PFX}%'})
        db.execute(text(
            "DELETE FROM product_components WHERE product_id IN (SELECT id FROM products WHERE sku LIKE :p)"
        ), {'p': f'{PFX}%'})
        db.execute(text("DELETE FROM products WHERE sku LIKE :p"), {'p': f'{PFX}%'})
        db.commit()


def test_backfill_migrates_legacy_rows_and_is_rerunnable(db_setup):
    from sqlalchemy import select, text
    from app.models.product import ComponentType, Product
    from app.services.catalog_unification import (
        drop_legacy_catalog_tables,
        migrate_catalog_items_to_products,
    )

    SessionLocal = db_setup
    legacy_device = uuid.uuid4()
    legacy_papi = uuid.uuid4()
    with SessionLocal() as db:
        # Recreate a minimal legacy table the way a pre-Phase-7 deploy left it.
        db.execute(text('DROP TABLE IF EXISTS catalog_items CASCADE'))
        db.execute(text(
            """
            CREATE TABLE catalog_items (
                id UUID PRIMARY KEY,
                type VARCHAR(16) NOT NULL,
                name VARCHAR(255) NOT NULL,
                sku VARCHAR(255) NOT NULL UNIQUE,
                vendor VARCHAR(128),
                vendor_sku VARCHAR(255),
                description VARCHAR(1024),
                price NUMERIC(12,2) NOT NULL,
                currency VARCHAR(8) NOT NULL DEFAULT 'USD',
                billing_cycle VARCHAR(16) NOT NULL DEFAULT 'ONE_TIME',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                availability VARCHAR(64),
                attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
                managed_service_price NUMERIC(12,2)
            )
            """
        ))
        db.execute(text(
            """
            INSERT INTO catalog_items (id, type, name, sku, vendor, vendor_sku, price,
                                       billing_cycle, availability, attributes, managed_service_price)
            VALUES
            (:d, 'DEVICE', 'Meraki MR46', :dsku, 'Meraki', 'MR46', 1013.00,
             'ONE_TIME', 'in_stock', '{"category": "wifi_ap", "source_type": "excel"}'::jsonb, 10.00),
            (:p, 'DEVICE', 'PAPI UltraBook', :psku, 'PAPI', 'ULTRA', 1299.00,
             'ONE_TIME', 'in_stock', '{"category": "laptop"}'::jsonb, NULL)
            """
        ), {'d': str(legacy_device), 'dsku': f'{PFX}MR46', 'p': str(legacy_papi), 'psku': f'{PFX}PAPI-UB'})
        db.commit()

    with SessionLocal() as db:
        first = migrate_catalog_items_to_products(db)
        assert first['skipped'] is False and first['migrated'] == 2
        second = migrate_catalog_items_to_products(db)  # re-runnable, no dupes
        assert second['migrated'] == 2

    with SessionLocal() as db:
        meraki = db.scalar(select(Product).where(Product.sku == f'{PFX}MR46'))
        assert meraki is not None
        assert meraki.margin_pct is None  # D2: inherit per-tenant markup
        assert meraki.attributes['legacy_catalog_item_id'] == str(legacy_device)
        by_type = {c.component_type: c for c in meraki.components}
        device_comp = by_type[ComponentType.DEVICE]
        assert Decimal(device_comp.vendor_cost) == Decimal('1013.00')
        assert device_comp.billing == 'ONE_TIME' and device_comp.is_required
        ms_comp = by_type[ComponentType.MANAGED_SERVICE]
        assert Decimal(ms_comp.vendor_cost) == Decimal('10.00') and not ms_comp.is_required

        papi = db.scalar(select(Product).where(Product.sku == f'{PFX}PAPI-UB'))
        assert papi.attributes['source_type'] == 'paapi'  # D8 flag
        # PAPI devices carry no managed service (§6).
        assert all(c.component_type != ComponentType.MANAGED_SERVICE for c in papi.components)

        # Legacy-id resolution works for historical BOM/design references.
        from app.services.catalog_unification import find_product_by_id_or_legacy
        assert find_product_by_id_or_legacy(db, str(legacy_device)).id == meraki.id

    # WS7: retire the legacy tables; reads keep working.
    drop_legacy_catalog_tables()
    with SessionLocal() as db:
        from sqlalchemy import text as _text
        assert db.execute(_text("SELECT to_regclass('public.catalog_items')")).scalar() is None
        assert db.execute(_text("SELECT to_regclass('public.list_prices')")).scalar() is None
        third = migrate_catalog_items_to_products(db)  # no-op once dropped
        assert third['skipped'] is True


def test_cdw_importer_writes_products(db_setup):
    from sqlalchemy import select
    from app.models.product import ComponentType, Product
    from app.services.catalog_service import CatalogService

    SessionLocal = db_setup
    with SessionLocal() as db:
        result = CatalogService(db).upsert_router_items([{
            'sku': f'{PFX}CDW-RTR', 'name': 'CDW Router X', 'vendor': 'CDW',
            'price': 499.0, 'brand': 'Cisco', 'model': 'X',
        }])
        assert result['synced_count'] == 1 and not result['errors']

    with SessionLocal() as db:
        product = db.scalar(select(Product).where(Product.sku == f'{PFX}CDW-RTR'))
        assert product is not None and product.attributes['source_type'] == 'cdw'
        device = next(c for c in product.components if c.component_type == ComponentType.DEVICE)
        assert Decimal(device.vendor_cost) == Decimal('499.00')


def test_catalog_reprices_per_tenant_and_papi_is_locked(db_setup):
    from app.models.pricing import CustomerPricing
    from app.models.tenant import Tenant
    from app.services.catalog_service import CatalogService
    from app.services.catalog_unification import upsert_product_from_catalog_row

    SessionLocal = db_setup
    with SessionLocal() as db:
        upsert_product_from_catalog_row(db, {
            'sku': f'{PFX}DEV-1', 'name': 'Unify Device', 'item_type': 'DEVICE',
            'vendor': 'Meraki', 'price': 100.0, 'billing_cycle': 'ONE_TIME',
            'attributes': {'category': 'router'}, 'managed_service_price': 15.50,
        })
        upsert_product_from_catalog_row(db, {
            'sku': f'{PFX}PAPI-1', 'name': 'Unify PAPI Phone', 'item_type': 'DEVICE',
            'vendor': 'PAPI', 'price': 799.0, 'billing_cycle': 'ONE_TIME',
            'attributes': {'category': 'phone'},
        })
        t20, t50 = Tenant(name=f'{PFX}T20'), Tenant(name=f'{PFX}T50')
        db.add_all([t20, t50])
        db.flush()
        db.add(CustomerPricing(tenant_id=t20.id, default_margin_pct=Decimal('0.20')))
        db.add(CustomerPricing(tenant_id=t50.id, default_margin_pct=Decimal('0.50')))
        db.commit()
        t20_id, t50_id = str(t20.id), str(t50.id)

    with SessionLocal() as db:
        service = CatalogService(db)

        def _entry(sku, tenant_id):
            entries = service.list_items(item_type=None, category=None, service_kind=None,
                                         search=sku, tenant_id=tenant_id)
            return next(e for e in entries if e.sku == sku)

        # Same SKU, different tenants, different prices (WS3 AC).
        assert _entry(f'{PFX}DEV-1', t20_id).price == 120.00
        assert _entry(f'{PFX}DEV-1', t50_id).price == 150.00
        # No tenant → 25% global default.
        assert _entry(f'{PFX}DEV-1', None).price == 125.00
        # Managed-service feed reprices per tenant too (D4: markup on top).
        assert _entry(f'{PFX}DEV-1', t20_id).managed_service_price == 18.60   # 15.50 × 1.20
        assert _entry(f'{PFX}DEV-1', t50_id).managed_service_price == 23.25   # 15.50 × 1.50

        # PAPI: same price for everyone, not editable (D8).
        for tenant_id in (t20_id, t50_id, None):
            papi = _entry(f'{PFX}PAPI-1', tenant_id)
            assert papi.price == 799.00
            assert papi.price_editable is False
