from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.catalog import CatalogItem, CatalogItemType
from app.models.network_design import NetworkDesign
from app.services.catalog_service import (
    CATEGORY_TO_MS_GROUP,
    MANAGED_SERVICE_CATEGORIES,
    MANAGED_SERVICE_GROUP_LABELS,
)

MONEY_QUANT = Decimal('0.01')


class ManagedServicePricingService:
    def __init__(self, db: Session):
        self.db = db

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _item_category(item: CatalogItem) -> str | None:
        return (item.attributes or {}).get('category')

    @staticmethod
    def _ms_price(item: CatalogItem) -> Decimal | None:
        if item.managed_service_price is None:
            return None
        return Decimal(str(item.managed_service_price))

    # ── core calculation ────────────────────────────────────────

    def get_category_summary(
        self,
        bom_lines: list[dict[str, Any]],
        catalog_items_by_id: dict[str, CatalogItem],
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return per-group breakdown given BOM lines and a managed-services config.

        config shape:
            { "enabled_categories": ["network", "security", ...],
              "excluded_item_ids": ["uuid1", ...] }
        """
        # Default: ALL categories enabled unless user explicitly disabled some
        raw_enabled = config.get('enabled_categories')
        if raw_enabled and len(raw_enabled) > 0:
            enabled = set(raw_enabled)
        else:
            enabled = set(MANAGED_SERVICE_CATEGORIES.keys())
        excluded_ids = set(config.get('excluded_item_ids') or [])

        # Accumulate per group
        groups: dict[str, dict] = {}
        for group_key in MANAGED_SERVICE_CATEGORIES:
            groups[group_key] = {
                'group': group_key,
                'group_label': MANAGED_SERVICE_GROUP_LABELS[group_key],
                'enabled': group_key in enabled,
                'device_count': 0,
                'excluded_count': 0,
                'applied_count': 0,
                'monthly_total': Decimal('0'),
                'devices': [],
            }

        for line in bom_lines:
            item_id = line.get('item_id')
            qty = int(line.get('quantity', 0))
            if not item_id or qty <= 0:
                continue

            item = catalog_items_by_id.get(item_id)
            if not item or item.type != CatalogItemType.DEVICE:
                continue

            category = self._item_category(item)
            ms_group = CATEGORY_TO_MS_GROUP.get(category or '')
            if not ms_group:
                continue

            ms_price = self._ms_price(item)
            if ms_price is None:
                continue

            g = groups[ms_group]
            g['device_count'] += qty

            is_excluded = str(item.id) in excluded_ids
            device_entry = {
                'item_id': str(item.id),
                'name': item.name,
                'sku': item.sku,
                'category': category,
                'quantity': qty,
                'managed_service_price': float(ms_price),
                'excluded': is_excluded,
            }
            g['devices'].append(device_entry)

            if is_excluded:
                g['excluded_count'] += qty
            else:
                line_total = (ms_price * qty).quantize(MONEY_QUANT, ROUND_HALF_UP)
                g['applied_count'] += qty
                g['monthly_total'] += line_total

        result = []
        for group_key in MANAGED_SERVICE_CATEGORIES:
            g = groups[group_key]
            g['monthly_total'] = float(g['monthly_total'])
            # Only include non-zero groups or enabled groups
            if g['device_count'] > 0 or g['enabled']:
                result.append(g)
        return result

    def calculate_for_design(self, design_id: str) -> dict[str, Any]:
        """Full computation for a network design's managed services."""
        design = self.db.get(NetworkDesign, design_id)
        if not design:
            raise NotFoundError('Network design not found')

        bom = design.bom_json or {}
        bom_lines = bom.get('line_items', [])
        config = design.managed_services_json or {}

        # Collect all item_ids referenced in BOM
        item_ids = [line.get('item_id') for line in bom_lines if line.get('item_id')]
        catalog_items_by_id = {}
        if item_ids:
            items = self.db.query(CatalogItem).filter(CatalogItem.id.in_(item_ids)).all()
            catalog_items_by_id = {str(i.id): i for i in items}

        categories = self.get_category_summary(bom_lines, catalog_items_by_id, config)
        grand_total = sum(c['monthly_total'] for c in categories if c.get('enabled'))

        return {
            'config': config,
            'categories': categories,
            'grand_total_monthly': round(grand_total, 2),
        }

    def update_design_managed_services(
        self,
        design_id: str,
        enabled_categories: list[str],
        excluded_item_ids: list[str],
    ) -> dict[str, Any]:
        design = self.db.get(NetworkDesign, design_id)
        if not design:
            raise NotFoundError('Network design not found')

        config = {
            'enabled_categories': sorted(set(enabled_categories)),
            'excluded_item_ids': sorted(set(excluded_item_ids)),
        }
        design.managed_services_json = config
        self.db.commit()
        self.db.refresh(design)

        return self.calculate_for_design(design_id)

    def get_managed_service_lines_for_quote(
        self,
        design: NetworkDesign,
    ) -> list[dict[str, Any]]:
        """Generate quote-line dicts for managed services applied on a design."""
        config = design.managed_services_json or {}
        raw_enabled = config.get('enabled_categories')
        if raw_enabled and len(raw_enabled) > 0:
            enabled = set(raw_enabled)
        else:
            enabled = set(MANAGED_SERVICE_CATEGORIES.keys())
        if not enabled:
            return []

        excluded_ids = set(config.get('excluded_item_ids') or [])
        bom = design.bom_json or {}
        bom_lines = bom.get('line_items', [])

        item_ids = [l.get('item_id') for l in bom_lines if l.get('item_id')]
        if not item_ids:
            return []

        items = self.db.query(CatalogItem).filter(CatalogItem.id.in_(item_ids)).all()
        items_by_id = {str(i.id): i for i in items}

        lines = []
        for bom_line in bom_lines:
            item_id = bom_line.get('item_id')
            qty = int(bom_line.get('quantity', 0))
            if not item_id or qty <= 0:
                continue

            item = items_by_id.get(item_id)
            if not item or item.type != CatalogItemType.DEVICE:
                continue

            category = self._item_category(item)
            ms_group = CATEGORY_TO_MS_GROUP.get(category or '')
            if not ms_group or ms_group not in enabled:
                continue

            if str(item.id) in excluded_ids:
                continue

            ms_price = self._ms_price(item)
            if ms_price is None or ms_price <= 0:
                continue

            lines.append({
                'name': f'Managed Service – {item.name}',
                'sku': f'MS-{item.sku}',
                'vendor': 'Secure Office',
                'qty': qty,
                'unit_price': float(ms_price),
                'billing_type': 'RECURRING',
                'interval': 'MONTH',
                'metadata': {
                    'source': 'managed_service_per_sku',
                    'source_device_id': str(item.id),
                    'source_device_sku': item.sku,
                    'ms_group': ms_group,
                    'category': category,
                },
            })

        return lines
