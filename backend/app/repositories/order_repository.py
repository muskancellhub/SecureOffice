import uuid
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload
from app.models.order import Order, OrderLine


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Order:
        order = Order(**kwargs)
        self.db.add(order)
        self.db.flush()
        return order

    def add_line(self, **kwargs) -> OrderLine:
        line = OrderLine(**kwargs)
        self.db.add(line)
        self.db.flush()
        return line

    def get_by_id(self, order_id: str) -> Order | None:
        try:
            stmt = select(Order).where(Order.id == uuid.UUID(order_id)).options(selectinload(Order.lines), selectinload(Order.quote))
            return self.db.scalar(stmt)
        except (TypeError, ValueError):
            return None

    def list_for_user(self, user_id: str) -> list[Order]:
        stmt = (
            select(Order)
            .where(Order.created_by == uuid.UUID(user_id))
            .options(selectinload(Order.lines), selectinload(Order.quote))
            .order_by(desc(Order.created_at))
        )
        return list(self.db.scalars(stmt).all())

    def list_for_tenant(self, tenant_id: str) -> list[Order]:
        stmt = (
            select(Order)
            .where(Order.tenant_id == uuid.UUID(tenant_id))
            .options(selectinload(Order.lines), selectinload(Order.quote))
            .order_by(desc(Order.created_at))
        )
        return list(self.db.scalars(stmt).all())
