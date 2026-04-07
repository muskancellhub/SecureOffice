import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.models.cart import Cart, CartLine, CartStatus


class CartRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_cart(self, user_id: str, tenant_id: str) -> Cart | None:
        stmt = (
            select(Cart)
            .where(
                Cart.user_id == uuid.UUID(user_id),
                Cart.tenant_id == uuid.UUID(tenant_id),
                Cart.status == CartStatus.ACTIVE,
            )
            .options(selectinload(Cart.lines).selectinload(CartLine.catalog_item))
            .options(selectinload(Cart.lines).selectinload(CartLine.applies_to_line))
            .order_by(Cart.created_at.desc())
        )
        return self.db.scalar(stmt)

    def create_active_cart(self, user_id: str, tenant_id: str) -> Cart:
        cart = Cart(user_id=uuid.UUID(user_id), tenant_id=uuid.UUID(tenant_id), status=CartStatus.ACTIVE)
        self.db.add(cart)
        self.db.flush()
        return cart

    def get_or_create_active_cart(self, user_id: str, tenant_id: str) -> Cart:
        cart = self.get_active_cart(user_id, tenant_id)
        if cart:
            return cart
        return self.create_active_cart(user_id, tenant_id)

    def add_line(
        self,
        *,
        cart_id,
        catalog_item_id,
        quantity: int,
        unit_price: float,
        currency: str,
        price_snapshot: dict,
        applies_to_line_id=None,
    ) -> CartLine:
        line = CartLine(
            cart_id=cart_id,
            catalog_item_id=catalog_item_id,
            quantity=quantity,
            unit_price=unit_price,
            currency=currency,
            price_snapshot=price_snapshot,
            applies_to_line_id=applies_to_line_id,
        )
        self.db.add(line)
        self.db.flush()
        return line

    def get_matching_line(self, *, cart_id, catalog_item_id, applies_to_line_id=None) -> CartLine | None:
        stmt = select(CartLine).where(
            CartLine.cart_id == cart_id,
            CartLine.catalog_item_id == catalog_item_id,
        )
        if applies_to_line_id is None:
            stmt = stmt.where(CartLine.applies_to_line_id.is_(None))
        else:
            stmt = stmt.where(CartLine.applies_to_line_id == applies_to_line_id)
        return self.db.scalar(stmt)

    def get_line_by_id(self, line_id: str) -> CartLine | None:
        try:
            return self.db.get(CartLine, uuid.UUID(line_id))
        except (ValueError, TypeError):
            return None

    def delete_line(self, line: CartLine) -> None:
        self.db.delete(line)
        self.db.flush()

    def list_attached_service_lines(self, cart_id, applies_to_line_id) -> list[CartLine]:
        stmt = select(CartLine).where(CartLine.cart_id == cart_id, CartLine.applies_to_line_id == applies_to_line_id)
        return list(self.db.scalars(stmt).all())
