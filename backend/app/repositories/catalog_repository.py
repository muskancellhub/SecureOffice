from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.catalog import BillingCycle, CatalogItem, CatalogItemType


class CatalogRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_sku(self, sku: str) -> CatalogItem | None:
        return self.db.scalar(select(CatalogItem).where(CatalogItem.sku == sku))

    def get_by_id(self, item_id: str) -> CatalogItem | None:
        try:
            import uuid

            return self.db.get(CatalogItem, uuid.UUID(item_id))
        except (TypeError, ValueError):
            return None

    def upsert_item(
        self,
        *,
        item_type: CatalogItemType,
        sku: str,
        name: str,
        vendor: str | None,
        vendor_sku: str | None,
        description: str | None,
        price: float,
        currency: str,
        billing_cycle: BillingCycle,
        availability: str | None,
        attributes: dict,
        is_active: bool = True,
    ) -> tuple[CatalogItem, bool]:
        item = self.get_by_sku(sku)
        if item:
            item.type = item_type
            item.name = name
            item.vendor = vendor
            item.vendor_sku = vendor_sku
            item.description = description
            item.price = price
            item.currency = currency
            item.billing_cycle = billing_cycle
            item.availability = availability
            item.attributes = attributes
            item.is_active = is_active
            self.db.flush()
            return item, False

        item = CatalogItem(
            type=item_type,
            sku=sku,
            name=name,
            vendor=vendor,
            vendor_sku=vendor_sku,
            description=description,
            price=price,
            currency=currency,
            billing_cycle=billing_cycle,
            availability=availability,
            attributes=attributes,
            is_active=is_active,
        )
        self.db.add(item)
        self.db.flush()
        return item, True

    def list_items(
        self,
        *,
        item_type: CatalogItemType | None = None,
        category: str | None = None,
        service_kind: str | None = None,
        active_only: bool = True,
    ) -> list[CatalogItem]:
        stmt = select(CatalogItem)
        if active_only:
            stmt = stmt.where(CatalogItem.is_active.is_(True))
        if item_type:
            stmt = stmt.where(CatalogItem.type == item_type)
        if category:
            stmt = stmt.where(CatalogItem.attributes['category'].astext == category)
        if service_kind:
            stmt = stmt.where(CatalogItem.attributes['service_kind'].astext == service_kind)
        stmt = stmt.order_by(CatalogItem.created_at.desc())
        return list(self.db.scalars(stmt).all())
