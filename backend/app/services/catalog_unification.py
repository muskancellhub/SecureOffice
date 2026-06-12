"""Phase 7 WS1 — unify on the component model (one catalog).

Every legacy ``catalog_items`` row becomes a ``product`` with one primary priced
component (DEVICE for hardware, MANAGED_SERVICE for legacy service tiers) and,
when the item carried a ``managed_service_price``, an optional MANAGED_SERVICE
add-on component. The legacy row id is kept at
``product.attributes['legacy_catalog_item_id']`` so historical BOM / design /
quote references can be repointed.

Importers (CDW, PAPI, Excel, seeds) call :func:`upsert_product_from_catalog_row`
directly; startup calls :func:`migrate_catalog_items_to_products` once to
backfill anything written before the cutover, then
:func:`drop_legacy_catalog_tables` retires ``catalog_items`` (WS7 — not in
production, dropped outright per the locked decision).
"""
from __future__ import annotations

import logging
import uuid as uuid_mod
from decimal import Decimal

from sqlalchemy import select, text

from app.models.product import ComponentType, ComponentUom, FinancialModel, Product, ProductComponent

logger = logging.getLogger(__name__)

# Legacy device managed-service add-ons are seeded at this default when the
# legacy row had no price (Phase 7 D7).
DEFAULT_MANAGED_SERVICE_PRICE = Decimal('15.50')


def _billing_from_cycle(billing_cycle: str | None) -> tuple[str, str | None]:
    cycle = str(billing_cycle or 'ONE_TIME').upper()
    if cycle == 'MONTHLY':
        return 'RECURRING', 'MONTH'
    if cycle == 'YEARLY':
        return 'RECURRING', 'YEAR'
    return 'ONE_TIME', None


def _technology_from_attributes(attributes: dict, item_type: str) -> str:
    category = str((attributes or {}).get('category') or (attributes or {}).get('product_type') or '').strip()
    if category:
        return category.replace('_', ' ').title()
    return 'Managed Service' if item_type == 'SERVICE' else 'General'


def _is_papi(sku: str, vendor: str | None, attributes: dict) -> bool:
    if str((attributes or {}).get('source_type') or '').lower() == 'paapi':
        return True
    return str(vendor or '').strip().upper() == 'PAPI' or str(sku or '').startswith('PAPI-')


def _msrp_for(price, attributes: dict, *, papi: bool) -> Decimal | None:
    """Retail reference for the admin grid. Real value when the source carries
    one; PAPI resells at its own retail so MSRP = price; otherwise a dummy
    1.5× retail placeholder (the grid should not show dashes)."""
    explicit = (attributes or {}).get('msrp')
    if explicit is not None:
        try:
            return Decimal(str(explicit))
        except Exception:
            pass
    cost = Decimal(str(price or 0))
    if cost <= 0:
        return None
    if papi:
        return cost
    return (cost * Decimal('1.5')).quantize(Decimal('0.01'))


def _upsert_component(
    db, product: Product, *, component_type: ComponentType, vendor_component_sku: str,
    label: str, vendor_cost, uom: ComponentUom, billing: str, interval: str | None,
    is_required: bool, is_active: bool, attributes: dict, msrp=None,
) -> ProductComponent:
    comp = db.scalar(
        select(ProductComponent).where(
            ProductComponent.product_id == product.id,
            ProductComponent.component_type == component_type,
            ProductComponent.vendor_component_sku == vendor_component_sku,
        )
    )
    if comp is None:
        comp = ProductComponent(
            product_id=product.id, component_type=component_type,
            vendor_component_sku=vendor_component_sku,
        )
        db.add(comp)
    comp.label = label
    comp.vendor_cost = Decimal(str(vendor_cost or 0))
    if msrp is not None:
        comp.msrp = msrp
    comp.uom = uom
    comp.billing = billing
    comp.interval = interval
    comp.financial_model = FinancialModel.BOTH
    comp.is_required = is_required
    comp.is_active = is_active
    comp.attributes = attributes or {}
    db.flush()
    return comp


def upsert_product_from_catalog_row(db, row: dict) -> Product:
    """Idempotently upsert one product (+ components) from a legacy-shaped
    catalog row. ``row`` keys mirror the old ``catalog_items`` columns:
    sku, name, item_type ('DEVICE'|'SERVICE'), vendor, vendor_sku, description,
    price, currency, billing_cycle, availability, attributes,
    managed_service_price, is_active, legacy_catalog_item_id (optional).
    Caller commits."""
    sku = str(row['sku']).strip()
    item_type = str(row.get('item_type') or 'DEVICE').upper()
    attributes = dict(row.get('attributes') or {})

    product = db.scalar(select(Product).where(Product.sku == sku))
    if product is None:
        product = Product(sku=sku)
        db.add(product)

    product.vendor = str(row.get('vendor') or 'CDW').strip() or 'CDW'
    product.technology = _technology_from_attributes(attributes, item_type)
    product.vendor_sku = row.get('vendor_sku') or sku
    product.name = row['name']
    product.description = row.get('description')
    product.default_financial_model = FinancialModel.BOTH
    # D2: no pinned SKU margin — per-tenant rules (override → tenant default →
    # 25% global) resolve it. PAPI is forced to zero in the engine (D8).
    product.margin_pct = None
    product.is_active = bool(row.get('is_active', True))

    attributes.setdefault('category', attributes.get('product_type'))
    attributes['availability'] = row.get('availability')
    attributes['currency'] = str(row.get('currency') or 'USD').upper()
    attributes['item_type'] = item_type
    if _is_papi(sku, product.vendor, attributes):
        attributes['source_type'] = 'paapi'
    legacy_id = row.get('legacy_catalog_item_id')
    if legacy_id:
        attributes['legacy_catalog_item_id'] = str(legacy_id)
    product.attributes = attributes
    db.flush()

    billing, interval = _billing_from_cycle(row.get('billing_cycle'))
    primary_type = ComponentType.MANAGED_SERVICE if item_type == 'SERVICE' else ComponentType.DEVICE
    papi = _is_papi(sku, product.vendor, attributes)
    _upsert_component(
        db, product,
        component_type=primary_type,
        vendor_component_sku=str(row.get('vendor_sku') or sku),
        label=row['name'],
        vendor_cost=row.get('price') or 0,
        uom=ComponentUom.PER_DEVICE,
        billing=billing,
        interval=interval,
        is_required=True,
        is_active=bool(row.get('is_active', True)),
        attributes={'legacy_primary': True},
        msrp=_msrp_for(row.get('price'), attributes, papi=papi),
    )

    # Optional per-device managed-service add-on (D4). PAPI devices do not
    # carry one (resolved in §6 of the phase-7 plan).
    ms_price = row.get('managed_service_price')
    if ms_price is not None and item_type == 'DEVICE' and not _is_papi(sku, product.vendor, attributes):
        _upsert_component(
            db, product,
            component_type=ComponentType.MANAGED_SERVICE,
            vendor_component_sku=f'{sku}-MS',
            label='Managed Service',
            vendor_cost=ms_price,
            uom=ComponentUom.PER_DEVICE,
            billing='RECURRING',
            interval='MONTH',
            is_required=False,
            is_active=True,
            attributes={'legacy_managed_service': True},
        )
    return product


def deactivate_products_for_source(db, *, source_type: str, source_name: str, active_skus: set[str]) -> int:
    """Source-of-truth imports (the network-vendor Excel) deactivate stale rows
    they previously created. Mirrors the legacy catalog_items behaviour."""
    stale = db.scalars(
        select(Product).where(
            Product.attributes['source_type'].astext == source_type,
            Product.attributes['source_name'].astext == source_name,
        )
    ).all()
    deactivated = 0
    for product in stale:
        if product.sku not in active_skus and product.is_active:
            product.is_active = False
            for comp in product.components:
                comp.is_active = False
            deactivated += 1
    return deactivated


def find_product_by_id_or_legacy(db, identifier) -> Product | None:
    """Resolve a product by its own id, its sku, or a legacy catalog_item id
    (pre-unification BOMs / designs / drafts still hold those)."""
    if identifier is None:
        return None
    raw = str(identifier).strip()
    if not raw:
        return None
    try:
        pid = uuid_mod.UUID(raw)
    except (TypeError, ValueError):
        return db.scalar(select(Product).where(Product.sku == raw))
    product = db.get(Product, pid)
    if product is not None:
        return product
    return db.scalar(
        select(Product).where(Product.attributes['legacy_catalog_item_id'].astext == raw)
    )


def map_products_for_identifiers(db, identifiers) -> dict[str, Product]:
    """Batch form of :func:`find_product_by_id_or_legacy` — returns a mapping
    keyed by the ORIGINAL identifier string (product id, legacy catalog id, or
    sku). Used by BOM / design flows whose stored item_ids may predate the
    unification."""
    from sqlalchemy.orm import selectinload

    wanted = [str(i).strip() for i in identifiers if i]
    if not wanted:
        return {}
    uuid_keys: list[uuid_mod.UUID] = []
    sku_keys: list[str] = []
    for raw in wanted:
        try:
            uuid_keys.append(uuid_mod.UUID(raw))
        except (TypeError, ValueError):
            sku_keys.append(raw)

    mapping: dict[str, Product] = {}
    if uuid_keys:
        for product in db.scalars(
            select(Product).where(Product.id.in_(uuid_keys)).options(selectinload(Product.components))
        ):
            mapping[str(product.id)] = product
        unresolved = [str(k) for k in uuid_keys if str(k) not in mapping]
        if unresolved:
            for product in db.scalars(
                select(Product)
                .where(Product.attributes['legacy_catalog_item_id'].astext.in_(unresolved))
                .options(selectinload(Product.components))
            ):
                legacy = (product.attributes or {}).get('legacy_catalog_item_id')
                if legacy:
                    mapping[str(legacy)] = product
    if sku_keys:
        for product in db.scalars(
            select(Product).where(Product.sku.in_(sku_keys)).options(selectinload(Product.components))
        ):
            mapping[product.sku] = product
    return mapping


def migrate_catalog_items_to_products(db) -> dict:
    """One-shot, re-runnable backfill: every legacy catalog_items row → product.

    Reads via raw SQL because the ORM model was retired with the table. No-op
    when the table is already gone (fresh installs / post-WS7 boots).
    """
    exists = db.execute(text("SELECT to_regclass('public.catalog_items')")).scalar()
    if not exists:
        return {'migrated': 0, 'skipped': True}

    rows = db.execute(text(
        """
        SELECT id, type, name, sku, vendor, vendor_sku, description, price,
               currency, billing_cycle, is_active, availability, attributes,
               managed_service_price
        FROM catalog_items
        """
    )).mappings().all()

    migrated = 0
    for r in rows:
        upsert_product_from_catalog_row(db, {
            'sku': r['sku'],
            'name': r['name'],
            'item_type': str(r['type']),
            'vendor': r['vendor'],
            'vendor_sku': r['vendor_sku'],
            'description': r['description'],
            'price': r['price'],
            'currency': r['currency'],
            'billing_cycle': str(r['billing_cycle']),
            'availability': r['availability'],
            'attributes': r['attributes'] or {},
            'managed_service_price': r['managed_service_price'],
            'is_active': r['is_active'],
            'legacy_catalog_item_id': r['id'],
        })
        migrated += 1
    db.commit()
    logger.info('Catalog unification backfill: %d catalog_items rows migrated to products', migrated)
    return {'migrated': migrated, 'skipped': False}


def drop_legacy_catalog_tables() -> None:
    """WS7 — retire the legacy tables once the backfill has run. CASCADE drops
    the dangling FK constraints on cart/quote/order/asset/subscription lines;
    their (nullable) catalog_item_id snapshot columns stay for history."""
    from app.core.database import engine

    with engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS list_prices'))
        conn.execute(text('DROP TABLE IF EXISTS catalog_items CASCADE'))
        conn.execute(text('DROP TYPE IF EXISTS catalog_item_type'))
        conn.execute(text('DROP TYPE IF EXISTS billing_cycle'))
