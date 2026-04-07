from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.models.catalog import BillingCycle, CatalogItem, CatalogItemType
from app.models.user import UserRole
from app.repositories.catalog_repository import CatalogRepository
from app.services.network_vendor_catalog_loader import (
    NETWORK_VENDOR_CATALOG_SOURCE_NAME,
    load_network_vendor_catalog,
)


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
        self.repo = CatalogRepository(db)

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
            'vendor': str(item.get('vendor') or 'CDW').strip() or 'CDW',
            'vendor_sku': str(item.get('vendor_sku') or sku).strip() or sku,
            'description': item.get('description'),
            'price': CatalogService._to_float(item.get('price')),
            'currency': str(item.get('currency') or 'USD').upper(),
            'availability': item.get('availability'),
            'attributes': attributes,
        }

    def upsert_router_items(self, items: list[dict]) -> dict:
        normalized = []
        errors: list[str] = []
        for idx, item in enumerate(items):
            try:
                normalized.append(self._normalize_router_item(item))
            except AppError as exc:
                errors.append(f'row {idx}: {exc.message}')

        upserted = []
        created_count = 0
        updated_count = 0
        for row in normalized:
            item, created = self.repo.upsert_item(
                item_type=CatalogItemType.DEVICE,
                sku=row['sku'],
                name=row['name'],
                vendor=row['vendor'],
                vendor_sku=row['vendor_sku'],
                description=row['description'],
                price=row['price'],
                currency=row['currency'],
                billing_cycle=BillingCycle.ONE_TIME,
                availability=row['availability'],
                attributes=row['attributes'],
            )
            upserted.append(item)
            if created:
                created_count += 1
            else:
                updated_count += 1
        self.db.commit()
        return {
            'items': upserted,
            'synced_count': len(upserted),
            'created_count': created_count,
            'updated_count': updated_count,
            'errors': errors,
        }

    def upsert_network_vendor_catalog(self, file_path: str | None = None) -> dict:
        loaded = load_network_vendor_catalog(file_path)
        errors = list(loaded.errors)

        upserted: list[CatalogItem] = []
        created_count = 0
        updated_count = 0
        active_skus: set[str] = set()

        for row in loaded.rows:
            attrs = dict(row['attributes'] or {})
            if row.get('price') is None:
                attrs['price_unavailable'] = True

            item, created = self.repo.upsert_item(
                item_type=CatalogItemType.DEVICE,
                sku=row['sku'],
                name=row['name'],
                vendor=row['vendor'],
                vendor_sku=row['vendor_sku'],
                description=row['description'],
                price=row['price'] if row.get('price') is not None else 0.0,
                currency=row['currency'],
                billing_cycle=BillingCycle.ONE_TIME,
                availability=row['availability'] or 'in_stock',
                attributes=attrs,
            )
            upserted.append(item)
            active_skus.add(row['sku'])
            if created:
                created_count += 1
            else:
                updated_count += 1

        # Spreadsheet is source-of-truth: stale rows from the same source are deactivated.
        stale_items = list(
            self.db.scalars(
                select(CatalogItem).where(
                    CatalogItem.attributes['source_type'].astext == 'excel',
                    CatalogItem.attributes['source_name'].astext == NETWORK_VENDOR_CATALOG_SOURCE_NAME,
                )
            ).all()
        )
        deactivated_count = 0
        for item in stale_items:
            if item.sku not in active_skus and item.is_active:
                item.is_active = False
                deactivated_count += 1

        self.db.commit()

        return {
            'items': upserted,
            'synced_count': len(upserted),
            'created_count': created_count,
            'updated_count': updated_count,
            'deactivated_count': deactivated_count,
            'skipped_count': loaded.skipped_count,
            'errors': errors,
        }

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

        upserted = []
        for row in seed_items:
            item, _ = self.repo.upsert_item(
                item_type=CatalogItemType.SERVICE,
                sku=row['sku'],
                name=row['name'],
                vendor='Secure Office',
                vendor_sku=row['sku'],
                description=f"{row['name']} monthly plan",
                price=row['price'],
                currency='USD',
                billing_cycle=BillingCycle.MONTHLY,
                availability='in_stock',
                attributes=row['attributes'],
            )
            upserted.append(item)
        self.db.commit()
        return upserted

    def seed_partner_devices(self) -> list:
        seed_items = [
            {
                'type': CatalogItemType.DEVICE,
                'sku': 'PAPI-LAPTOP-ULTRA-14',
                'name': 'PAPI UltraBook 14',
                'vendor': 'PAPI',
                'description': 'Business laptop for employee productivity workloads',
                'price': 1299.0,
                'billing_cycle': BillingCycle.ONE_TIME,
                'availability': 'in_stock',
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
                'type': CatalogItemType.DEVICE,
                'sku': 'PAPI-LAPTOP-PRO-15',
                'name': 'PAPI ProBook 15',
                'vendor': 'PAPI',
                'description': 'High-performance laptop for engineering and design users',
                'price': 1599.0,
                'billing_cycle': BillingCycle.ONE_TIME,
                'availability': 'in_stock',
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
                'type': CatalogItemType.DEVICE,
                'sku': 'PAPI-PHONE-BIZ-5G',
                'name': 'PAPI BizPhone 5G',
                'vendor': 'PAPI',
                'description': 'Business smartphone with secure mobile management profile',
                'price': 799.0,
                'billing_cycle': BillingCycle.ONE_TIME,
                'availability': 'in_stock',
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

        upserted = []
        for row in seed_items:
            item, _ = self.repo.upsert_item(
                item_type=row['type'],
                sku=row['sku'],
                name=row['name'],
                vendor=row['vendor'],
                vendor_sku=row['sku'],
                description=row['description'],
                price=row['price'],
                currency='USD',
                billing_cycle=row['billing_cycle'],
                availability=row['availability'],
                attributes=row['attributes'],
            )
            upserted.append(item)
        self.db.commit()
        return upserted

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
                    'vendor': 'PAPI',
                    'vendor_sku': part_number,
                    'description': short_desc,
                    'price': offer_price,
                    'currency': 'USD',
                    'availability': availability,
                    'attributes': attributes,
                }
            )

        return rows

    def upsert_papi_products(self, raw_products: list[dict]) -> dict:
        """Normalize PAPI API products and upsert into catalog."""
        errors: list[str] = []
        all_rows: list[dict] = []
        for idx, product in enumerate(raw_products):
            try:
                rows = self._normalize_papi_product(product)
                all_rows.extend(rows)
            except Exception as exc:
                errors.append(f'product {idx} ({product.get("name", "?")}): {exc}')

        upserted = []
        created_count = 0
        updated_count = 0
        for row in all_rows:
            try:
                item, created = self.repo.upsert_item(
                    item_type=CatalogItemType.DEVICE,
                    sku=row['sku'],
                    name=row['name'],
                    vendor=row['vendor'],
                    vendor_sku=row['vendor_sku'],
                    description=row['description'],
                    price=row['price'],
                    currency=row['currency'],
                    billing_cycle=BillingCycle.ONE_TIME,
                    availability=row['availability'],
                    attributes=row['attributes'],
                )
                upserted.append(item)
                if created:
                    created_count += 1
                else:
                    updated_count += 1
            except Exception as exc:
                errors.append(f'upsert {row["sku"]}: {exc}')

        self.db.commit()
        return {
            'items': upserted,
            'synced_count': len(upserted),
            'created_count': created_count,
            'updated_count': updated_count,
            'errors': errors,
        }

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
            'pricing_basis': attrs.get('pricing_basis'),
            'model': attrs.get('model'),
            'notes': attrs.get('notes'),
            'raw_source': raw_source,
        }

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
    ):
        items = self.repo.list_items(item_type=item_type, category=category, service_kind=service_kind)

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

    def update_managed_service(
        self,
        current_user: dict,
        item_id: str,
        *,
        price: float | None,
        is_active: bool | None,
        features: Iterable[str] | None,
    ):
        if current_user.get('role') not in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}:
            raise ForbiddenError('Only ADMIN or SUPER_ADMIN can update managed services')

        item = self.repo.get_by_id(item_id)
        if not item:
            raise NotFoundError('Managed service not found')
        if item.type != CatalogItemType.SERVICE or (item.attributes or {}).get('service_kind') != 'managed_router':
            raise AppError('Target catalog item is not a managed router service', 400)

        if price is not None:
            item.price = float(price)
        if is_active is not None:
            item.is_active = is_active
        if features is not None:
            attrs = dict(item.attributes or {})
            attrs['features'] = [str(f).strip() for f in features if str(f).strip()]
            item.attributes = attrs

        self.db.commit()
        self.db.refresh(item)
        return item

    def get_item_by_id(self, item_id: str):
        item = self.repo.get_by_id(item_id)
        if not item:
            item = self.repo.get_by_sku(item_id)
        if not item or not item.is_active:
            raise NotFoundError('Catalog item not found')
        return item
