import uuid
from sqlalchemy import delete, select
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
            .options(selectinload(Cart.lines).selectinload(CartLine.product))
            .options(selectinload(Cart.lines).selectinload(CartLine.component))
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
        product_id=None,
        component_id=None,
        quantity: int,
        unit_price: float,
        currency: str,
        price_snapshot: dict,
        applies_to_line_id=None,
    ) -> CartLine:
        line = CartLine(
            cart_id=cart_id,
            product_id=product_id,
            component_id=component_id,
            quantity=quantity,
            unit_price=unit_price,
            currency=currency,
            price_snapshot=price_snapshot,
            applies_to_line_id=applies_to_line_id,
        )
        self.db.add(line)
        self.db.flush()
        return line

    def get_matching_line(self, *, cart_id, component_id, applies_to_line_id=None) -> CartLine | None:
        stmt = select(CartLine).where(
            CartLine.cart_id == cart_id,
            CartLine.component_id == component_id,
        )
        if applies_to_line_id is None:
            stmt = stmt.where(CartLine.applies_to_line_id.is_(None))
        else:
            stmt = stmt.where(CartLine.applies_to_line_id == applies_to_line_id)
        return self.db.scalar(stmt)

    def get_line_by_id(self, line_id) -> CartLine | None:
        # line_id may arrive as a uuid.UUID (Pydantic coerces the
        # applies_to_line_id: UUID request field) or as a plain string (internal
        # callers). Calling uuid.UUID() on an existing UUID raises AttributeError,
        # which slipped past the except below and surfaced as a 500 on every
        # service-attach request. Normalise both forms here.
        try:
            key = line_id if isinstance(line_id, uuid.UUID) else uuid.UUID(line_id)
        except (ValueError, TypeError, AttributeError):
            return None
        return self.db.get(CartLine, key)

    def delete_line(self, line: CartLine) -> None:
        self.db.delete(line)
        self.db.flush()

    def delete_all_lines(self, cart_id) -> int:
        """Remove every line in a cart in one statement (BUG-CART-002). Returns
        the number of rows deleted."""
        result = self.db.execute(delete(CartLine).where(CartLine.cart_id == cart_id))
        self.db.flush()
        return int(result.rowcount or 0)

    def list_attached_service_lines(self, cart_id, applies_to_line_id) -> list[CartLine]:
        stmt = select(CartLine).where(CartLine.cart_id == cart_id, CartLine.applies_to_line_id == applies_to_line_id)
        return list(self.db.scalars(stmt).all())
