"""Legacy catalog enums (Phase 7 — the catalog_items TABLE is retired).

The flat ``catalog_items`` table was migrated into ``products`` /
``product_components`` (docs/plans/phase-7) and dropped. These enums survive
because the product-backed catalog API still speaks the same vocabulary
(DEVICE/SERVICE entries, ONE_TIME/MONTHLY/YEARLY headline billing).
"""
import enum


class CatalogItemType(str, enum.Enum):
    DEVICE = 'DEVICE'
    SERVICE = 'SERVICE'


class BillingCycle(str, enum.Enum):
    ONE_TIME = 'ONE_TIME'
    MONTHLY = 'MONTHLY'
    YEARLY = 'YEARLY'
