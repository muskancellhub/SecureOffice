"""Product-backed catalog service (Phase 7 — one catalog).

Every importer (CDW, PAPI, Excel, seeds) writes ``products`` /
``product_components`` via :mod:`app.services.catalog_unification`; every read
returns :class:`ProductCatalogEntry` objects priced for the requesting tenant by
:class:`ComponentPricingService`. Entries deliberately quack like the retired
``catalog_items`` rows (id/sku/name/price/attributes/managed_service_price/…)
so the BOM, design and chatbot surfaces keep working unchanged.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.models.catalog import BillingCycle, CatalogItemType
from app.models.product import ComponentType, Product, ProductComponent
from app.models.user import UserRole
from app.services.audit_logger import audit
from app.services.catalog_unification import (
    deactivate_products_for_source,
    find_product_by_id_or_legacy,
    upsert_product_from_catalog_row,
)
from app.services.component_pricing_service import ComponentPricingService, is_papi_product
from app.services.network_vendor_catalog_loader import (
    NETWORK_VENDOR_CATALOG_SOURCE_NAME,
    load_network_vendor_catalog,
)


MANAGED_SERVICE_CATEGORIES: dict[str, set[str]] = {
    'network': {'router', 'wifi_ap', 'switch', 'firewall', 'cellular_gateway'},
    'security': {'security_appliance', 'camera', 'sensor'},
    'end_user_devices': {'laptop', 'phone', 'tablet', 'hotspot'},
}

MANAGED_SERVICE_GROUP_LABELS: dict[str, str] = {
    'network': 'Network',
    'security': 'Security',
    'end_user_devices': 'End User Devices',
}

CATEGORY_TO_MS_GROUP: dict[str, str] = {}
for _group, _cats in MANAGED_SERVICE_CATEGORIES.items():
    for _cat in _cats:
        CATEGORY_TO_MS_GROUP[_cat] = _group


@dataclass
class ProductCatalogEntry:
    """A product priced for one tenant, shaped like a legacy catalog item."""

    id: str
    product_id: str
    type: CatalogItemType
    name: str
    sku: str
    vendor: str | None
    vendor_sku: str | None
    description: str | None
    price: float
    currency: str
    billing_cycle: BillingCycle
    is_active: bool
    availability: str | None
    attributes: dict
    managed_service_price: float | None
    created_at: datetime
    one_time_price: float = 0.0
    monthly_price: float = 0.0
    price_editable: bool = True
    components: list[dict] | None = None


class CatalogService:
    NETWORK_CATEGORIES = {
        'wifi_ap',
        'switch',
        'firewall',
        'router',
        'cellular_gateway',
        'security_appliance',
        'camera',
        'sensor',
        'antenna',
        'accessory',
        'managed_service_candidate',
    }

    def __init__(self, db):
        self.db = db
        self.pricing = ComponentPricingService(db)

    @staticmethod
    def _to_float(value, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _extract_port_count(item) -> int:
        attrs = item.attributes or {}
        ports_value = attrs.get('ports')
        family_type = str(attrs.get('family_type') or '')

        if isinstance(ports_value, int):
            return ports_value
        if isinstance(ports_value, float):
            return int(ports_value)
        if isinstance(ports_value, str):
            digits = ''.join(ch for ch in ports_value if ch.isdigit())
            return int(digits) if digits else 0
        if isinstance(ports_value, dict):
            total = 0
            for value in ports_value.values():
                if isinstance(value, (int, float)):
                    total += int(value)
                elif isinstance(value, str):
                    digits = ''.join(ch for ch in value if ch.isdigit())
                    if digits:
                        total += int(digits)
            if total > 0:
                return total

        import re

        match = re.search(r'(\d{1,3})\s*[- ]?port', family_type.lower())
        if match:
            return int(match.group(1))
        return 0

    # ── entry construction ───────────────────────────────────────────────────
    @staticmethod
    def _entry_type(product: Product) -> CatalogItemType:
        for comp in product.components:
            if comp.component_type == ComponentType.DEVICE:
                return CatalogItemType.DEVICE
        item_type = str((product.attributes or {}).get('item_type') or '').upper()
        if item_type == 'SERVICE':
            return CatalogItemType.SERVICE
        return CatalogItemType.DEVICE

    @staticmethod
    def _entry_billing(one_time_price: float, monthly_price: float, product: Product) -> BillingCycle:
        if one_time_price > 0:
            return BillingCycle.ONE_TIME
        for comp in product.components:
            if comp.is_required and comp.billing == 'RECURRING':
                return BillingCycle.YEARLY if comp.interval == 'YEAR' else BillingCycle.MONTHLY
        return BillingCycle.MONTHLY if monthly_price > 0 else BillingCycle.ONE_TIME

    def _entry_from_product(self, product: Product, pricing: dict) -> ProductCatalogEntry:
        one_time = float(pricing.get('one_time_price') or 0)
        monthly = float(pricing.get('monthly_price') or 0)
        ms_monthly = pricing.get('managed_service_monthly')
        attrs = dict(product.attributes or {})
        return ProductCatalogEntry(
            id=str(product.id),
            product_id=str(product.id),
            type=self._entry_type(product),
            name=product.name,
            sku=product.sku,
            vendor=product.vendor,
            vendor_sku=product.vendor_sku,
            description=product.description,
            price=one_time if one_time > 0 else monthly,
            currency=str(attrs.get('currency') or 'USD'),
            billing_cycle=self._entry_billing(one_time, monthly, product),
            is_active=product.is_active,
            availability=attrs.get('availability'),
            attributes=attrs,
            managed_service_price=float(ms_monthly) if ms_monthly is not None else None,
            created_at=product.created_at,
            one_time_price=one_time,
            monthly_price=monthly,
            price_editable=bool(pricing.get('price_editable', True)),
        )

    def _entries_for_products(self, products: list[Product], *, tenant_id=None) -> list[ProductCatalogEntry]:
        pricing = self.pricing.price_catalog_entries(products, tenant_id=tenant_id)
        return [self._entry_from_product(p, pricing.get(str(p.id), {})) for p in products]

    def _component_listing(self, product: Product, *, tenant_id=None) -> list[dict]:
        """All active components priced individually (configurator rows, D9)."""
        rows: list[dict] = []
        for comp in sorted(product.components, key=lambda c: (not c.is_required, c.component_type.value)):
            if not comp.is_active:
                continue
            priced = self.pricing.price_standalone_component(
                comp.id, qty=max(1, comp.default_qty), financial_model='CAPEX',
                interval='MONTH', tenant_id=tenant_id,
            )
            line = priced['lines'][0]
            rows.append({
                'id': str(comp.id),
                'component_type': comp.component_type.value,
                'label': comp.label,
                'vendor_component_sku': comp.vendor_component_sku,
                'uom': comp.uom.value,
                'billing': comp.billing,
                'interval': comp.interval,
                'is_required': comp.is_required,
                'default_qty': comp.default_qty,
                'financial_model': comp.financial_model.value
                if hasattr(comp.financial_model, 'value') else str(comp.financial_model),
                'unit_price': float(line['unit_price']),
                'monthly_unit': float(line['monthly_unit']),
                'one_time_unit': float(line['one_time_unit']),
                'price_editable': bool(line['price_editable']),
                'attributes': comp.attributes or {},
            })
        return rows

    # ── importers (all write products — Phase 7 WS1) ─────────────────────────
    @staticmethod
    def _normalize_router_item(item: dict) -> dict:
        sku = str(item.get('sku') or '').strip()
        name = str(item.get('name') or '').strip()
        if not sku or not name:
            raise AppError('Router item is missing required sku or name', 400)

        attributes = {
            'category': 'router',
            'product_type': 'router',
            'brand': item.get('brand'),
            'model': item.get('model'),
            'sku': sku,
            'ports': item.get('ports'),
            'wifi_standard': item.get('wifi_standard'),
            'throughput': item.get('throughput'),
            'specs': item.get('specs') or {},
            'source_type': 'cdw',
            'source_name': 'cdw_router_sync',
        }

        return {
            'sku': sku,
            'name': name,
            'item_type': 'DEVICE',
            'vendor': str(item.get('vendor') or 'CDW').strip() or 'CDW',
            'vendor_sku': str(item.get('vendor_sku') or sku).strip() or sku,
            'description': item.get('description'),
            'price': CatalogService._to_float(item.get('price')),
            'currency': str(item.get('currency') or 'USD').upper(),
            'billing_cycle': 'ONE_TIME',
            'availability': item.get('availability'),
            'attributes': attributes,
        }

    def _upsert_rows(self, rows: list[dict]) -> tuple[list[Product], int, int]:
        products: list[Product] = []
        created = 0
        updated = 0
        for row in rows:
            existed = self.db.scalar(select(Product.id).where(Product.sku == row['sku'])) is not None
            products.append(upsert_product_from_catalog_row(self.db, row))
            if existed:
                updated += 1
            else:
                created += 1
        return products, created, updated

    def _sync_result(self, products: list[Product], created: int, updated: int, errors: list[str], **extra) -> dict:
        # Re-load with components so the response entries can derive type/billing.
        ids = [p.id for p in products]
        loaded = []
        if ids:
            loaded = list(self.db.scalars(
                select(Product).where(Product.id.in_(ids)).options(selectinload(Product.components))
            ).all())
            loaded.sort(key=lambda p: ids.index(p.id))
        return {
            'items': self._entries_for_products(loaded),
            'synced_count': len(products),
            'created_count': created,
            'updated_count': updated,
            'errors': errors,
            **extra,
        }

    def upsert_router_items(self, items: list[dict]) -> dict:
        normalized = []
        errors: list[str] = []
        for idx, item in enumerate(items):
            try:
                normalized.append(self._normalize_router_item(item))
            except AppError as exc:
                errors.append(f'row {idx}: {exc.message}')

        products, created, updated = self._upsert_rows(normalized)
        self.db.commit()
        return self._sync_result(products, created, updated, errors)

    def upsert_network_vendor_catalog(self, file_path: str | None = None) -> dict:
        loaded = load_network_vendor_catalog(file_path)
        errors = list(loaded.errors)

        rows: list[dict] = []
        active_skus: set[str] = set()
        for row in loaded.rows:
            attrs = dict(row['attributes'] or {})
            if row.get('price') is None:
                attrs['price_unavailable'] = True
            rows.append({
                'sku': row['sku'],
                'name': row['name'],
                'item_type': 'DEVICE',
                'vendor': row['vendor'],
                'vendor_sku': row['vendor_sku'],
                'description': row['description'],
                'price': row['price'] if row.get('price') is not None else 0.0,
                'currency': row['currency'],
                'billing_cycle': 'ONE_TIME',
                'availability': row['availability'] or 'in_stock',
                'attributes': attrs,
            })
            active_skus.add(row['sku'])

        products, created, updated = self._upsert_rows(rows)
        # Spreadsheet is source-of-truth: stale rows from the same source are deactivated.
        deactivated_count = deactivate_products_for_source(
            self.db, source_type='excel', source_name=NETWORK_VENDOR_CATALOG_SOURCE_NAME,
            active_skus=active_skus,
        )
        self.db.commit()
        return self._sync_result(
            products, created, updated, errors,
            deactivated_count=deactivated_count, skipped_count=loaded.skipped_count,
        )

    def seed_managed_services(self) -> list:
        seed_items = [
            {
                'sku': 'MRS-BRONZE',
                'name': 'Managed Router - Bronze',
                'price': 29.0,
                'attributes': {
                    'category': 'managed_service',
                    'product_type': 'managed_service',
                    'tier': 'bronze',
                    'service_kind': 'managed_router',
                    'applies_to_categories': ['router', 'laptop', 'phone', 'hotspot'],
                    'tiers': ['bronze', 'silver', 'gold'],
                    'pricing_basis': 'PER_DEVICE',
                    'features': ['Email support', 'Monthly health check', 'Configuration backup'],
                    'source_type': 'seed',
                    'source_name': 'managed_service_seed',
                },
            },
            {
                'sku': 'MRS-SILVER',
                'name': 'Managed Router - Silver',
                'price': 59.0,
                'attributes': {
                    'category': 'managed_service',
                    'product_type': 'managed_service',
                    'tier': 'silver',
                    'service_kind': 'managed_router',
                    'applies_to_categories': ['router', 'laptop', 'phone', 'hotspot'],
                    'tiers': ['bronze', 'silver', 'gold'],
                    'pricing_basis': 'PER_DEVICE',
                    'features': ['Priority support', 'Weekly monitoring', 'Firmware management'],
                    'source_type': 'seed',
                    'source_name': 'managed_service_seed',
                },
            },
            {
                'sku': 'MRS-GOLD',
                'name': 'Managed Router - Gold',
                'price': 99.0,
                'attributes': {
                    'category': 'managed_service',
                    'product_type': 'managed_service',
                    'tier': 'gold',
                    'service_kind': 'managed_router',
                    'applies_to_categories': ['router', 'laptop', 'phone', 'hotspot'],
                    'tiers': ['bronze', 'silver', 'gold'],
                    'pricing_basis': 'PER_DEVICE',
                    'features': ['24/7 support', 'Proactive remediation', 'Dedicated success engineer'],
                    'source_type': 'seed',
                    'source_name': 'managed_service_seed',
                },
            },
        ]

        rows = [
            {
                'sku': row['sku'],
                'name': row['name'],
                'item_type': 'SERVICE',
                'vendor': 'Secure Office',
                'vendor_sku': row['sku'],
                'description': f"{row['name']} monthly plan",
                'price': row['price'],
                'currency': 'USD',
                'billing_cycle': 'MONTHLY',
                'availability': 'in_stock',
                'attributes': row['attributes'],
            }
            for row in seed_items
        ]
        products, _, _ = self._upsert_rows(rows)
        self.db.commit()
        return products

    def seed_partner_devices(self) -> list:
        seed_items = [
            {
                'sku': 'PAPI-LAPTOP-ULTRA-14',
                'name': 'PAPI UltraBook 14',
                'description': 'Business laptop for employee productivity workloads',
                'price': 1299.0,
                'attributes': {
                    'category': 'laptop',
                    'product_type': 'laptop',
                    'brand': 'PAPI',
                    'model': 'UltraBook 14',
                    'cpu': 'Intel Core i7',
                    'ram': '16GB',
                    'storage': '512GB SSD',
                    'source_type': 'paapi',
                    'source_name': 'papi_seed',
                },
            },
            {
                'sku': 'PAPI-LAPTOP-PRO-15',
                'name': 'PAPI ProBook 15',
                'description': 'High-performance laptop for engineering and design users',
                'price': 1599.0,
                'attributes': {
                    'category': 'laptop',
                    'product_type': 'laptop',
                    'brand': 'PAPI',
                    'model': 'ProBook 15',
                    'cpu': 'Intel Core i9',
                    'ram': '32GB',
                    'storage': '1TB SSD',
                    'source_type': 'paapi',
                    'source_name': 'papi_seed',
                },
            },
            {
                'sku': 'PAPI-PHONE-BIZ-5G',
                'name': 'PAPI BizPhone 5G',
                'description': 'Business smartphone with secure mobile management profile',
                'price': 799.0,
                'attributes': {
                    'category': 'phone',
                    'product_type': 'phone',
                    'brand': 'PAPI',
                    'model': 'BizPhone 5G',
                    'os': 'Android',
                    'storage': '256GB',
                    'source_type': 'paapi',
                    'source_name': 'papi_seed',
                },
            },
        ]

        rows = [
            {
                'sku': row['sku'],
                'name': row['name'],
                'item_type': 'DEVICE',
                'vendor': 'PAPI',
                'vendor_sku': row['sku'],
                'description': row['description'],
                'price': row['price'],
                'currency': 'USD',
                'billing_cycle': 'ONE_TIME',
                'availability': 'in_stock',
                'attributes': row['attributes'],
            }
            for row in seed_items
        ]
        products, _, _ = self._upsert_rows(rows)
        self.db.commit()
        return products

    def seed_mix_products(self) -> dict:
        """Idempotently seed the MIX Networks component catalog (Phase 1).

        Delegates to app.services.mix_seed; returns a
        {'products','components','financing_terms'} summary. Safe to call on
        every startup.
        """
        from app.services.mix_seed import seed_mix_products as _seed
        return _seed(self.db)

    def seed_discounted_items(self) -> dict:
        """Idempotently seed the featured/discounted catalog family (POTS-in-a-Box,
        Multiline, managed services, phone, SIM). Delegates to
        app.services.discounted_seed."""
        from app.services.discounted_seed import seed_discounted_items as _seed
        return _seed(self.db)

    PAPI_PRODUCT_TYPE_CATEGORY = {
        'phones': 'phone',
        'phone': 'phone',
        'tablets': 'tablet',
        'tablet': 'tablet',
        'internet devices': 'other',
        'internet device': 'other',
        'hotspot': 'cellular_gateway',
        'sim': 'sim',
    }

    @classmethod
    def _infer_papi_category(cls, device_type: str, product_name: str, variant_name: str) -> str:
        device_type_l = str(device_type or '').strip().lower()
        mapped = cls.PAPI_PRODUCT_TYPE_CATEGORY.get(device_type_l)
        blob = f'{product_name} {variant_name}'.lower()

        if mapped and mapped != 'other':
            return mapped

        if any(token in blob for token in ['tablet', 'ipad', 'tab ']):
            return 'tablet'
        if any(token in blob for token in ['gateway', 'router', 'hotspot', 'mifi', 'modem', 'cpe', '5g internet']):
            return 'cellular_gateway'
        if any(token in blob for token in ['laptop', 'notebook', 'chromebook', 'ultrabook']):
            return 'laptop'
        if any(token in blob for token in ['phone', 'iphone', 'galaxy', 'pixel', 'smartphone']):
            return 'phone'
        return 'other'

    @staticmethod
    def _papi_availability(item_variant: dict) -> str:
        is_available = str(item_variant.get('isAvailable', 'N')).upper() == 'Y'
        esd_from_raw = (item_variant.get('inventoryDateRange') or [{}])[0].get('ESDFrom') if item_variant.get('inventoryDateRange') else None
        start_date_raw = item_variant.get('deviceStartDate')

        def parse_date(val: str | None) -> datetime | None:
            if not val:
                return None
            for fmt in ('%m-%d-%Y %H:%M:%S', '%m-%d-%Y'):
                try:
                    return datetime.strptime(val.strip(), fmt)
                except ValueError:
                    continue
            return None

        now = datetime.now()
        esd_from = parse_date(esd_from_raw)
        start_date = parse_date(start_date_raw)

        if is_available and esd_from and esd_from <= now:
            return 'in_stock'
        if not is_available and esd_from and esd_from > now and start_date and start_date <= now:
            return 'backorder'
        if esd_from and esd_from > now and start_date and start_date > now:
            return 'preorder'
        if is_available:
            return 'in_stock'
        return 'out_of_stock'

    def _normalize_papi_product(self, product: dict) -> list[dict]:
        """Convert a PAPI product with item variants into catalog row dicts (one per variant)."""
        product_name = str(product.get('name') or '').strip()
        device_type = str(product.get('deviceType') or '').strip()
        manufacturer = ''
        filters = product.get('filter') or []
        if filters:
            manufacturer = str(filters[0].get('manufacturer') or '').strip()

        features = [f.get('name', '') for f in (product.get('features') or [])]
        specifications = {
            s.get('name', ''): s.get('description', '')
            for s in (product.get('specifications') or [])
        }

        image_base = 'https://www.t-mobile.com'

        rows: list[dict] = []
        for variant in (product.get('items') or []):
            part_number = str(variant.get('partNumber') or '').strip()
            if not part_number:
                continue

            variant_name = str(variant.get('name') or product_name).strip()
            category = self._infer_papi_category(device_type, product_name, variant_name)
            sku = f'PAPI-{part_number}'
            color = str(variant.get('color') or '').strip()
            memory = str(variant.get('memory') or variant.get('RAM') or '').strip()
            price_list = variant.get('price') or []
            offer_price = self._to_float(price_list[0].get('offerPrice')) if price_list else self._to_float(product.get('displayPrice'))
            cost_price = self._to_float(variant.get('costPrice'))

            full_image = variant.get('fullImage') or ''
            thumbnail = variant.get('thumbnail') or ''
            extra_images = [img.get('fullImageUrl', '') for img in (variant.get('images') or [])]

            availability = self._papi_availability(variant)

            attributes = {
                'category': category,
                'product_type': category,
                'brand': manufacturer,
                'model': str(product.get('deviceName') or '').strip(),
                'color': color,
                'color_hex': variant.get('colorHexCode', ''),
                'memory': memory,
                'device_type': device_type,
                'os': specifications.get('operating_system', ''),
                'os_group': specifications.get('operatingSystemGroup', ''),
                'features': features,
                'network_speed': specifications.get('networkSpeed', ''),
                'dimensions': specifications.get('Dimension', ''),
                'weight': specifications.get('Weight', ''),
                'battery': specifications.get('Battery Talk Time', ''),
                'image_url': f'{image_base}{full_image}' if full_image else '',
                'thumbnail_url': f'{image_base}{thumbnail}' if thumbnail else '',
                'extra_images': [f'{image_base}{u}' for u in extra_images if u],
                'papi_unique_id': str(variant.get('uniqueID') or ''),
                'papi_product_unique_id': str(product.get('uniqueID') or ''),
                'part_number': part_number,
                'cost_price': cost_price,
                'cost_basis': self._to_float(variant.get('costBasis')),
                'is_subsidy': str(variant.get('isSubsidyDevice', '')).lower() == 'true',
                'esim_slots': product.get('esimSlotCount', '0'),
                'psim_slots': product.get('psimSlotCount', '0'),
                'seo_name': product.get('deviceSeoName', ''),
                'prop65': str(variant.get('prop65Message', 'N')).upper() == 'Y',
                'source_type': 'paapi',
                'source_name': 'papi_catalog',
            }

            long_desc = str(product.get('longDescription') or '').strip()
            short_desc = variant_name
            if long_desc:
                import re

                short_desc = re.sub(r'<[^>]+>', ' ', long_desc)[:500].strip()

            rows.append(
                {
                    'sku': sku,
                    'name': variant_name,
                    'item_type': 'DEVICE',
                    'vendor': 'PAPI',
                    'vendor_sku': part_number,
                    'description': short_desc,
                    'price': offer_price,
                    'currency': 'USD',
                    'billing_cycle': 'ONE_TIME',
                    'availability': availability,
                    'attributes': attributes,
                }
            )

        return rows

    def upsert_papi_products(self, raw_products: list[dict]) -> dict:
        """Normalize PAPI API products and upsert into the product catalog.

        PAPI products are flagged ``source_type='paapi'`` so the engine resells
        them at PAPI's exact price (zero margin, read-only — D8)."""
        errors: list[str] = []
        all_rows: list[dict] = []
        for idx, product in enumerate(raw_products):
            try:
                rows = self._normalize_papi_product(product)
                all_rows.extend(rows)
            except Exception as exc:
                errors.append(f'product {idx} ({product.get("name", "?")}): {exc}')

        products: list[Product] = []
        created = 0
        updated = 0
        for row in all_rows:
            try:
                existed = self.db.scalar(select(Product.id).where(Product.sku == row['sku'])) is not None
                products.append(upsert_product_from_catalog_row(self.db, row))
                if existed:
                    updated += 1
                else:
                    created += 1
            except Exception as exc:
                errors.append(f'upsert {row["sku"]}: {exc}')

        self.db.commit()
        return self._sync_result(products, created, updated, errors)

    # ── source inference (operates on entries / products alike) ──────────────
    def _infer_source_type(self, item) -> str:
        attrs = item.attributes or {}
        source_type = str(attrs.get('source_type') or '').strip().lower()
        if source_type:
            return source_type

        if str(item.sku or '').startswith('PAPI-') or str(item.vendor or '').strip().upper() == 'PAPI':
            return 'paapi'
        if str(item.sku or '').startswith('EXCEL-'):
            return 'excel'
        return 'catalog'

    def _infer_source_name(self, item, source_type: str) -> str:
        attrs = item.attributes or {}
        source_name = str(attrs.get('source_name') or '').strip()
        if source_name:
            return source_name

        if source_type == 'paapi':
            return 'papi_catalog'
        if source_type == 'excel':
            return NETWORK_VENDOR_CATALOG_SOURCE_NAME
        return 'catalog'

    def to_catalog_response_dict(self, item) -> dict[str, Any]:
        attrs = item.attributes or {}
        source_type = self._infer_source_type(item)
        source_name = self._infer_source_name(item, source_type)

        category = str(attrs.get('category') or '').strip() or None
        product_type = str(attrs.get('product_type') or attrs.get('category') or '').strip() or None

        raw_source = {
            'official_catalog_source': attrs.get('official_catalog_source'),
            'public_price_source': attrs.get('public_price_source'),
            'raw_category': attrs.get('raw_category'),
            'raw_row_number': attrs.get('raw_row_number'),
        }
        if not any(raw_source.values()):
            raw_source = None

        return {
            'id': str(item.id),
            'product_id': getattr(item, 'product_id', str(item.id)),
            'type': item.type,
            'name': item.name,
            'sku': item.sku,
            'vendor': item.vendor,
            'vendor_sku': item.vendor_sku,
            'description': item.description,
            'price': float(item.price),
            'currency': item.currency,
            'billing_cycle': item.billing_cycle,
            'is_active': item.is_active,
            'availability': item.availability,
            'attributes': attrs,
            'created_at': item.created_at,
            'category': category,
            'product_type': product_type,
            'source_type': source_type,
            'source_name': source_name,
            'managed_service_price': float(item.managed_service_price) if item.managed_service_price is not None else None,
            'pricing_basis': attrs.get('pricing_basis'),
            'model': attrs.get('model'),
            'notes': attrs.get('notes'),
            'raw_source': raw_source,
            'one_time_price': getattr(item, 'one_time_price', float(item.price)),
            'monthly_price': getattr(item, 'monthly_price', 0.0),
            'price_editable': getattr(item, 'price_editable', True),
            'components': getattr(item, 'components', None),
        }

    # ── reads (per-tenant priced — Phase 7 WS3) ──────────────────────────────
    def _load_products(self) -> list[Product]:
        return list(self.db.scalars(
            select(Product)
            .where(Product.is_active.is_(True))
            .options(selectinload(Product.components))
            .order_by(Product.created_at.desc())
        ).all())

    def _fetch_entries(self, *, tenant_id=None, include_unsellable: bool = False) -> list[ProductCatalogEntry]:
        """Load + price the full catalog. Seam for tests (override to inject
        fake entries without a database)."""
        products = self._load_products()
        if not include_unsellable:
            products = [p for p in products if (p.attributes or {}).get('sellable') is not False]
        return self._entries_for_products(products, tenant_id=tenant_id)

    def list_items(
        self,
        *,
        item_type: CatalogItemType | None,
        category: str | None,
        service_kind: str | None,
        search: str | None = None,
        brand: str | None = None,
        vendor: str | None = None,
        product_type: str | None = None,
        source_type: str | None = None,
        source_name: str | None = None,
        wifi_standard: str | None = None,
        availability: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_ports: int | None = None,
        sort: str | None = None,
        page: int = 1,
        page_size: int | None = None,
        tenant_id=None,
        include_unsellable: bool = False,
    ):
        items = [
            item for item in self._fetch_entries(tenant_id=tenant_id, include_unsellable=include_unsellable)
            if item.is_active
        ]

        if item_type:
            items = [item for item in items if item.type == item_type]

        if category:
            items = [
                item for item in items
                if str((item.attributes or {}).get('category') or '').lower() == category.lower()
            ]

        if service_kind:
            items = [
                item for item in items
                if str((item.attributes or {}).get('service_kind') or '').lower() == service_kind.lower()
            ]

        search_l = (search or '').strip().lower()
        if search_l:
            items = [
                item
                for item in items
                if search_l in (item.name or '').lower()
                or search_l in (item.sku or '').lower()
                or search_l in (item.vendor_sku or '').lower()
                or search_l in str((item.attributes or {}).get('brand') or '').lower()
                or search_l in str((item.attributes or {}).get('model') or '').lower()
            ]

        if brand:
            items = [item for item in items if str((item.attributes or {}).get('brand') or '').lower() == brand.lower()]

        if vendor:
            items = [item for item in items if str(item.vendor or '').lower() == vendor.lower()]

        if product_type:
            items = [
                item
                for item in items
                if str((item.attributes or {}).get('product_type') or (item.attributes or {}).get('category') or '').lower()
                == product_type.lower()
            ]

        if source_type:
            source_type_l = source_type.lower()
            items = [item for item in items if self._infer_source_type(item) == source_type_l]

        if source_name:
            source_name_l = source_name.lower()
            items = [
                item
                for item in items
                if self._infer_source_name(item, self._infer_source_type(item)).lower() == source_name_l
            ]

        if wifi_standard:
            items = [
                item
                for item in items
                if str((item.attributes or {}).get('wifi_standard') or '').lower() == wifi_standard.lower()
            ]

        if availability:
            items = [item for item in items if str(item.availability or '').lower() == availability.lower()]

        if min_price is not None:
            items = [item for item in items if float(item.price) >= float(min_price)]

        if max_price is not None:
            items = [item for item in items if float(item.price) <= float(max_price)]

        if min_ports is not None:
            items = [item for item in items if self._extract_port_count(item) >= min_ports]

        sort_value = (sort or 'recommended').lower()
        if sort_value == 'price_low':
            items.sort(key=lambda x: float(x.price))
        elif sort_value == 'price_high':
            items.sort(key=lambda x: float(x.price), reverse=True)
        elif sort_value == 'availability':

            def availability_rank(val: str | None) -> int:
                label = (val or '').lower()
                if label in {'in stock', 'in_stock', 'available'}:
                    return 0
                if label in {'backorder', 'back_order'}:
                    return 1
                return 2

            items.sort(key=lambda x: (availability_rank(x.availability), float(x.price)))
        else:
            # recommended
            def recommended_rank(item) -> tuple:
                availability_label = (item.availability or '').lower()
                in_stock = availability_label in {'in stock', 'in_stock', 'available'}
                return (0 if in_stock else 1, float(item.price))

            items.sort(key=recommended_rank)

        # Featured ("discounted") items are pinned to the top regardless of the
        # chosen sort. Python's sort is stable, so the in-group order picked
        # above is preserved within the featured and non-featured partitions.
        items.sort(key=lambda x: 0 if (x.attributes or {}).get('featured') else 1)

        if item_type == CatalogItemType.DEVICE:
            effective_page = max(1, int(page or 1))
            # Device listings are capped at 25 per page.
            effective_page_size = max(1, min(int(page_size or 25), 25))
            start = (effective_page - 1) * effective_page_size
            end = start + effective_page_size
            return items[start:end]

        if page_size is not None:
            effective_page = max(1, int(page or 1))
            effective_page_size = max(1, int(page_size))
            start = (effective_page - 1) * effective_page_size
            end = start + effective_page_size
            return items[start:end]

        return items

    def get_item_by_id(self, item_id: str, *, tenant_id=None, include_components: bool = False,
                       include_inactive: bool = False):
        product = find_product_by_id_or_legacy(self.db, item_id)
        # include_inactive lets admin write paths build a response for an item they
        # just deactivated (BUG-MS-001); public reads keep rejecting inactive items.
        if not product or (not product.is_active and not include_inactive):
            raise NotFoundError('Catalog item not found')
        # Touch the relationship so entry type/billing derivation has components.
        _ = product.components
        entry = self._entries_for_products([product], tenant_id=tenant_id)[0]
        if include_components:
            entry.components = self._component_listing(product, tenant_id=tenant_id)
        return entry

    # ── managed-service admin (per-SKU MS component — D4) ────────────────────
    @staticmethod
    def _require_ms_admin(current_user: dict) -> None:
        if current_user.get('role') not in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}:
            raise ForbiddenError('Only ADMIN or SUPER_ADMIN can update managed services')

    def _ms_component_for(self, product: Product) -> ProductComponent | None:
        """The product's managed-service add-on component (not the primary
        charge of a standalone SERVICE product)."""
        candidates = [
            c for c in product.components
            if c.component_type == ComponentType.MANAGED_SERVICE and not c.is_required
        ]
        return candidates[0] if candidates else None

    def update_managed_service(
        self,
        current_user: dict,
        item_id: str,
        *,
        price: float | None,
        is_active: bool | None,
        features: Iterable[str] | None,
    ):
        self._require_ms_admin(current_user)

        product = find_product_by_id_or_legacy(self.db, item_id)
        if not product:
            raise NotFoundError('Managed service not found')
        if (product.attributes or {}).get('service_kind') != 'managed_router':
            raise AppError('Target catalog item is not a managed router service', 400)

        primary = next(
            (c for c in product.components if c.component_type == ComponentType.MANAGED_SERVICE and c.is_required),
            None,
        )
        if price is not None:
            # Defense-in-depth: the schema enforces ge=0 at the API boundary, but
            # this is also reachable from internal callers that bypass it.
            if float(price) < 0:
                raise AppError('Price must be zero or greater', 400)
            if primary is not None:
                primary.vendor_cost = Decimal(str(price))
        if is_active is not None:
            product.is_active = is_active
            for comp in product.components:
                comp.is_active = is_active
        if features is not None:
            attrs = dict(product.attributes or {})
            attrs['features'] = [str(f).strip() for f in features if str(f).strip()]
            product.attributes = attrs

        self.db.commit()
        self.db.refresh(product)
        # include_inactive: the admin must get a 200 with the updated object even
        # when the update just set is_active=False (BUG-MS-001).
        return self.get_item_by_id(str(product.id), include_inactive=True)

    def _set_device_ms_price(self, product: Product, managed_service_price: float | None) -> float | None:
        """Upsert / deactivate the optional MANAGED_SERVICE component (D4)."""
        component = self._ms_component_for(product)
        old_price = float(component.vendor_cost) if component is not None and component.is_active else None
        if managed_service_price is None:
            if component is not None:
                component.is_active = False
            return old_price
        if component is None:
            component = ProductComponent(
                product_id=product.id,
                component_type=ComponentType.MANAGED_SERVICE,
                vendor_component_sku=f'{product.sku}-MS',
                label='Managed Service',
                uom='PER_DEVICE',
                billing='RECURRING',
                interval='MONTH',
                is_required=False,
                default_qty=1,
                attributes={'legacy_managed_service': True},
            )
            self.db.add(component)
        component.vendor_cost = Decimal(str(managed_service_price))
        component.is_active = True
        return old_price

    def update_device_managed_service_price(
        self,
        current_user: dict,
        item_id: str,
        managed_service_price: float | None,
    ):
        self._require_ms_admin(current_user)

        product = find_product_by_id_or_legacy(self.db, item_id)
        if not product:
            raise NotFoundError('Catalog item not found')
        if is_papi_product(product):
            raise AppError('PAPI devices do not carry a managed service (D8)', 400)
        if managed_service_price is not None and float(managed_service_price) < 0:
            raise AppError('Price must be zero or greater', 400)

        old_price = self._set_device_ms_price(product, managed_service_price)
        self.db.commit()
        audit.log('service_price_updated', catalog_item_id=str(product.id), item_sku=product.sku,
                  old_price=old_price, new_price=managed_service_price)
        return self.get_item_by_id(str(product.id))

    def bulk_update_managed_service_prices(
        self,
        current_user: dict,
        updates: list[dict],
    ) -> int:
        self._require_ms_admin(current_user)

        count = 0
        for entry in updates:
            item_id = entry.get('item_id')
            price = entry.get('managed_service_price')
            product = find_product_by_id_or_legacy(self.db, item_id)
            if not product or is_papi_product(product):
                continue
            self._set_device_ms_price(product, float(price) if price is not None else None)
            count += 1
        self.db.commit()
        audit.log('bulk_price_update', requested_count=len(updates), applied_count=count)
        return count
