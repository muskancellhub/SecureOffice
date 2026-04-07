from __future__ import annotations

from sqlalchemy import select
from app.models.catalog import CatalogItem, CatalogItemType


class DesignXService:
    CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
        'router': ('router', 'wifi', 'network', 'internet', 'office connectivity'),
        'laptop': ('laptop', 'notebook', 'workstation', 'tablet', 'ipad', 'employees', 'employee'),
        'phone': ('phone', 'mobile', 'smartphone', 'iphone', 'android', '5g'),
        'hotspot': ('hotspot', 'mifi', 'portable wifi', 'tethering'),
    }

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _normalize_requirement(requirement: str) -> str:
        return (requirement or '').strip().lower()

    @staticmethod
    def _contains_any(text: str, words: tuple[str, ...]) -> bool:
        return any(word in text for word in words)

    def _requested_categories(self, requirement: str) -> list[str]:
        text = self._normalize_requirement(requirement)
        categories = [
            category
            for category, words in self.CATEGORY_KEYWORDS.items()
            if self._contains_any(text, words)
        ]
        if not categories:
            return ['router']
        return categories

    def _pick_catalog_item(self, *, item_type: CatalogItemType, category: str | None = None):
        stmt = select(CatalogItem).where(CatalogItem.type == item_type, CatalogItem.is_active.is_(True))
        if category:
            stmt = stmt.where(CatalogItem.attributes['category'].astext == category)
        stmt = stmt.order_by(CatalogItem.price.asc(), CatalogItem.created_at.desc())
        return self.db.scalar(stmt)

    @staticmethod
    def _device_quantity(category: str, *, employees: int, sites: int) -> int:
        if category == 'router':
            return max(1, sites)
        if category in {'laptop', 'phone'}:
            return max(1, employees)
        return 1

    def suggest_bom(
        self,
        *,
        requirement: str,
        employee_count: int,
        site_count: int,
        existing_customer: bool,
    ) -> dict:
        categories = self._requested_categories(requirement)
        suggestions: list[dict] = []
        unavailable: list[str] = []

        for category in categories:
            item = self._pick_catalog_item(item_type=CatalogItemType.DEVICE, category=category)
            if not item:
                unavailable.append(category)
                continue

            quantity = self._device_quantity(category, employees=employee_count, sites=site_count)
            confidence = 0.88 if category in {'router', 'laptop', 'phone'} else 0.75
            suggestions.append(
                {
                    'catalog_item_id': str(item.id),
                    'type': item.type,
                    'category': (item.attributes or {}).get('category'),
                    'name': item.name,
                    'sku': item.sku,
                    'vendor': item.vendor,
                    'quantity': quantity,
                    'unit_price': float(item.price),
                    'currency': item.currency,
                    'billing_cycle': item.billing_cycle,
                    'reason': f"Suggested for {category} requirements from DesignX request",
                    'source': 'DESIGNX',
                    'confidence': confidence,
                }
            )

        service_item = self._pick_catalog_item(item_type=CatalogItemType.SERVICE, category='managed_service')
        if service_item:
            attach_base = next((row for row in suggestions if row['type'] == CatalogItemType.DEVICE), None)
            service_qty = attach_base['quantity'] if attach_base else max(1, site_count)
            service_reason = (
                'Managed service suggested for proactive monitoring and support coverage'
                if not existing_customer
                else 'Managed service suggested for addon lifecycle monitoring'
            )
            suggestions.append(
                {
                    'catalog_item_id': str(service_item.id),
                    'type': service_item.type,
                    'category': (service_item.attributes or {}).get('category'),
                    'name': service_item.name,
                    'sku': service_item.sku,
                    'vendor': service_item.vendor,
                    'quantity': service_qty,
                    'unit_price': float(service_item.price),
                    'currency': service_item.currency,
                    'billing_cycle': service_item.billing_cycle,
                    'reason': service_reason,
                    'source': 'DESIGNX',
                    'confidence': 0.79,
                }
            )
        else:
            unavailable.append('managed_service')

        summary = (
            f"DesignX suggested {len(suggestions)} line item(s) for {employee_count} employee(s) "
            f"across {site_count} site(s). Suggestions are editable before checkout."
        )
        return {
            'summary': summary,
            'suggestions': suggestions,
            'unavailable_categories': sorted(set(unavailable)),
        }
