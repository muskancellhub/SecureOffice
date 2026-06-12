"""Per-SKU managed-service pricing for network designs (product-backed).

Phase 7: the per-device managed-service price is the product's optional
MANAGED_SERVICE component, priced per tenant by ComponentPricingService
(markup applies on top of the admin-set cost — D4). BOM line ``item_id``s may
be product ids or pre-unification catalog ids; both resolve via the WS1
legacy mapping.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.network_design import NetworkDesign
from app.models.product import ComponentType, Product
from app.services.audit_logger import audit
from app.services.catalog_unification import map_products_for_identifiers
from app.services.component_pricing_service import ComponentPricingService
from app.services.catalog_service import (
    CATEGORY_TO_MS_GROUP,
    MANAGED_SERVICE_CATEGORIES,
    MANAGED_SERVICE_GROUP_LABELS,
)

MONEY_QUANT = Decimal('0.01')


class ManagedServicePricingService:
    def __init__(self, db: Session):
        self.db = db
        self.pricing = ComponentPricingService(db)

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _product_category(product: Product) -> str | None:
        return (product.attributes or {}).get('category')

    @staticmethod
    def _is_device(product: Product) -> bool:
        if any(c.component_type == ComponentType.DEVICE for c in product.components):
            return True
        return str((product.attributes or {}).get('item_type') or '').upper() != 'SERVICE'

    def _ms_prices_for(self, products: list[Product], tenant_id) -> dict[str, Decimal | None]:
        """{product_id: per-tenant MANAGED_SERVICE monthly price or None}."""
        priced = self.pricing.price_catalog_entries(products, tenant_id=tenant_id)
        out: dict[str, Decimal | None] = {}
        for product in products:
            entry = priced.get(str(product.id), {})
            ms = entry.get('managed_service_monthly')
            out[str(product.id)] = Decimal(str(ms)) if ms is not None else None
        return out

    # ── core calculation ────────────────────────────────────────

    def get_category_summary(
        self,
        bom_lines: list[dict[str, Any]],
        products_by_ref: dict[str, Product],
        config: dict[str, Any],
        *,
        tenant_id=None,
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

        ms_prices = self._ms_prices_for(list({id(p): p for p in products_by_ref.values()}.values()), tenant_id)

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

            product = products_by_ref.get(str(item_id))
            if not product or not self._is_device(product):
                continue

            category = self._product_category(product)
            ms_group = CATEGORY_TO_MS_GROUP.get(category or '')
            if not ms_group:
                continue

            ms_price = ms_prices.get(str(product.id))
            if ms_price is None:
                continue

            g = groups[ms_group]
            g['device_count'] += qty

            # Exclusions may reference the legacy id or the product id.
            is_excluded = bool({str(item_id), str(product.id)} & excluded_ids)
            device_entry = {
                'item_id': str(product.id),
                'name': product.name,
                'sku': product.sku,
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

    def _products_for_bom(self, bom_lines: list[dict[str, Any]]) -> dict[str, Product]:
        item_ids = [line.get('item_id') for line in bom_lines if line.get('item_id')]
        return map_products_for_identifiers(self.db, item_ids)

    def calculate_for_design(self, design_id: str) -> dict[str, Any]:
        """Full computation for a network design's managed services."""
        design = self.db.get(NetworkDesign, design_id)
        if not design:
            raise NotFoundError('Network design not found')

        bom = design.bom_json or {}
        bom_lines = bom.get('line_items', [])
        config = design.managed_services_json or {}

        products_by_ref = self._products_for_bom(bom_lines)
        categories = self.get_category_summary(
            bom_lines, products_by_ref, config, tenant_id=design.tenant_id
        )
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
        audit.log(
            'design_managed_services_updated',
            design_id=design_id,
            enabled_categories=config['enabled_categories'],
            excluded_item_count=len(config['excluded_item_ids']),
        )

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

        products_by_ref = self._products_for_bom(bom_lines)
        if not products_by_ref:
            return []
        ms_prices = self._ms_prices_for(
            list({id(p): p for p in products_by_ref.values()}.values()), design.tenant_id
        )

        lines = []
        for bom_line in bom_lines:
            item_id = bom_line.get('item_id')
            qty = int(bom_line.get('quantity', 0))
            if not item_id or qty <= 0:
                continue

            product = products_by_ref.get(str(item_id))
            if not product or not self._is_device(product):
                continue

            category = self._product_category(product)
            ms_group = CATEGORY_TO_MS_GROUP.get(category or '')
            if not ms_group or ms_group not in enabled:
                continue

            if {str(item_id), str(product.id)} & excluded_ids:
                continue

            ms_price = ms_prices.get(str(product.id))
            if ms_price is None or ms_price <= 0:
                continue

            lines.append({
                'name': f'Managed Service – {product.name}',
                'sku': f'MS-{product.sku}',
                'vendor': 'Secure Office',
                'qty': qty,
                'unit_price': float(ms_price),
                'billing_type': 'RECURRING',
                'interval': 'MONTH',
                'metadata': {
                    'source': 'managed_service_per_sku',
                    'source_device_id': str(product.id),
                    'source_device_sku': product.sku,
                    'ms_group': ms_group,
                    'category': category,
                },
            })

        return lines
